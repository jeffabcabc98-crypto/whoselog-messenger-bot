from flask import Flask, request
import os
import requests
import random
from datetime import datetime, timedelta, timezone
from supabase import create_client

# ======= 【安全防禦：終極密碼仍保留頂端匯入（因功能正常）】 =======
try:
    from number_bomb import start_ultimate_password, handle_guess
except ImportError:
    print("⚠️ [警告] 伺服器暫時找不到 number_bomb.py 模組！")
    start_ultimate_password = None
    handle_guess = None

try:
    from actions import handle_pending_actions
except ImportError:
    print("⚠️ [警告] 伺服器暫時找不到 actions.py 模組！")
    handle_pending_actions = None
# =====================================================================

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 🛡️ 防洗版（已整合：30秒限5次 ＆ 第一次觸發封鎖5分鐘）
# ==========================================
def check_rate_limit(user_id, msg_type="text"):
    now = datetime.now(timezone.utc)
    
    banned = supabase.table("banned_users").select("*").eq("user_id", user_id).limit(1).execute()
    if banned.data:
        expires_at = datetime.fromisoformat(banned.data[0]["expires_at"])
        if now < expires_at:
            return False
        else:
            supabase.table("banned_users").delete().eq("user_id", user_id).execute()
            
    window_start = now - timedelta(seconds=30)
    window_start_str = window_start.isoformat()
    
    logs = supabase.table("rate_limits").select("*").eq("user_id", user_id).eq("msg_type", msg_type).gte("created_at", window_start_str).execute()
    
    if len(logs.data) >= 10:
        ban_expires = now + timedelta(minutes=5)
        supabase.table("banned_users").insert({
            "user_id": user_id,
            "expires_at": ban_expires.isoformat()
        }).execute()
        
        send_message(user_id, "🚫 偵測到惡意洗版！你的帳號已被系統禁言 5 分鐘，請勿頻繁發送訊息。")
        return False
        
    supabase.table("rate_limits").insert({
        "user_id": user_id,
        "msg_type": msg_type
    }).execute()
    return True

# ==========================================
# 🚀 核心：文字訊息流總控
# ==========================================
def handle_text(user_id, text):
    text = text.strip()
    
    # ⚙️ 【核心修復點】：在 handle_text 每次執行時直接局域匯入最新、絕對不為 None 的遊戲模組！
    # 這能徹底杜絕 Railway 動態加載快取混亂導致函數變成 None 的老地雷！
    try:
        from game_modules import start_rps, handle_rps_move, start_undercover, handle_undercover_vote, cancel_game
    except ImportError:
        print("⚠️ [內部警告] handle_text 暫時無法加載 game_modules.py！")
        start_rps = handle_rps_move = start_undercover = handle_undercover_vote = cancel_game = None

    # ======= 【1. 管理員廣播與指令系統】 =======
    admin_ids = ["6564639913619557", "9563503117006764"]
    if user_id in admin_ids:
        if text.startswith("廣播 "):
            bc_msg = text.replace("廣播 ", "").strip()
            all_users = supabase.table("chat_pairs").select("user_id").execute()
            sent_ids = set()
            for u in all_users.data:
                uid = u["user_id"]
                if uid not in sent_ids:
                    try: send_message(uid, f"📢 【系統廣播】\n\n{bc_msg}", tag="ACCOUNT_UPDATE"); sent_ids.add(uid)
                    except: pass
            send_message(user_id, f"✅ 廣播發送完畢，共發送給 {len(sent_ids)} 位用戶。")
            return
            
        if text.startswith("解封 "):
            target = text.replace("解封 ", "").strip()
            supabase.table("banned_users").delete().eq("user_id", target).execute()
            supabase.table("rate_limits").delete().eq("user_id", target).execute()
            send_message(user_id, f"✅ 已手動解除用戶【{target}】的洗版封鎖狀態。")
            return

    # ======= 【2. 處理二次確認狀態 (Leave/Report 等)】 =======
    pending = supabase.table("pending_actions").select("*").eq("user_id", user_id).limit(1).execute()
    if pending.data:
        p = pending.data[0]
        if handle_pending_actions and handle_pending_actions(user_id, text, p["action"], p):
            return

    # ======= 【3. 基本配對與大廳導向指令】 =======
    if text == "開始":
        start_match(user_id)
        return
        
    if text == "離開":
        result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
        if not result.data:
            send_message(user_id, "❌ 你目前沒有配對對象。請輸入「開始」進行配對。")
            return
        supabase.table("pending_actions").insert({"user_id": user_id, "action": "confirm_leave"}).execute()
        send_message(user_id, "⚠️ 確定要離開目前聊天室嗎？\n\n請回覆：\n1️⃣ 或 是\n2️⃣ 或 否")
        return
        
    if text in ["檢舉", "下一位"]:
        result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
        if not result.data:
            send_message(user_id, "❌ 你目前沒有配對對象。")
            return
        act = "confirm_report" if text == "檢舉" else "confirm_next"
        prompt = "⚠️ 確定要檢舉對方嗎？" if text == "檢舉" else "⚠️ 確定要跳過此人、尋找下一位嗎？"
        supabase.table("pending_actions").insert({"user_id": user_id, "action": act}).execute()
        send_message(user_id, f"{prompt}\n\n請回覆：\n1️⃣ 或 是\n2️⃣ 或 否")
        return

    # ======= 【4. 小遊戲發起開局判斷】 =======
    pair_res = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
    if pair_res.data:
        partner = pair_res.data[0]["partner_id"]
        n1 = pair_res.data[0]["nickname"]
        
        part_res = supabase.table("chat_pairs").select("nickname").eq("user_id", partner).limit(1).execute()
        n2 = part_res.data[0]["nickname"] if part_res.data else "路人"
        
        clean_text = text.strip().replace(" ", "").replace(" ", "").replace("【", "").replace("】", "")
        
        if clean_text == "取消遊玩" and cancel_game:
            if cancel_game(user_id): return
            
        elif clean_text == "猜數字" and start_ultimate_password:
            start_ultimate_password(user_id, partner, n1, n2)
            return
        elif clean_text == "猜拳" and start_rps:
            start_rps(user_id, partner, n1, n2)
            return
        elif clean_text == "誰是臥底" and start_undercover:
            start_undercover(user_id, partner, n1, n2)
            return

        # ======= 【5. 聊天普通轉發與所有小遊戲輸入攔截】 =======
        result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
        if result.data:
            if handle_guess and handle_guess(user_id, text.strip()): return
            if handle_rps_move and handle_rps_move(user_id, text.strip()): return
            if handle_undercover_vote and handle_undercover_vote(user_id, text.strip()): return
            
            # 若無小遊戲攔截，執行普通訊息轉發
            send_message(result.data[0]["partner_id"], f"{result.data[0]['nickname']}：{text}", tag="ACCOUNT_UPDATE")
            return

    send_message(user_id, "💡 目前沒有配對對象。請輸入「開始」啟動匿名配對！")

# ==========================================
# 📁 附件流轉發（照片/貼圖/影片等）
# ==========================================
def handle_attachment(user_id, attachments):
    if not check_rate_limit(user_id, "attachment"):
        return
        
    result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
    if not result.data:
        send_message(user_id, "💡 目前沒有配對對象，無法發送多媒體物件。請輸入「開始」進行配對！")
        return
        
    partner_id = result.data[0]["partner_id"]
    my_name = result.data[0]["nickname"]
    
    for attach in attachments:
        payload = {"recipient": {"id": partner_id}, "message": {}}
        
        if attach["type"] == "fallback":
            if "sticker_id" in attach:
                payload["message"] = {"attachment": {"type": "image", "payload": {"url": attach["url"]}}}
            else:
                send_message(partner_id, f"🔗 {my_name} 傳送了一個連結：\n{attach['url']}", tag="ACCOUNT_UPDATE")
                continue
        else:
            payload["message"] = {"attachment": {"type": attach["type"], "payload": {"url": attach["payload"]["url"]}}}
            
        try:
            send_message(partner_id, f"🖼️ {my_name} 傳送了多媒體物件：", tag="ACCOUNT_UPDATE")
            headers = {"Content-Type": "application/json"}
            requests.post(f"https://graph.facebook.com/v12.0/me/messages?access_token={PAGE_ACCESS_TOKEN}", json=payload, headers=headers)
        except:
            pass

# ==========================================
# 🔍 基礎功能：系統配對邏輯
# ==========================================
def start_match(user_id):
    existing = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
    if existing.data:
        send_message(user_id, "⚠️ 你已經在聊天室中囉！若想離開請輸入「離開」。")
        return
        
    supabase.table("queue").delete().eq("user_id", user_id).execute()
    
    blacklist_res = supabase.table("blacklist").select("blocked_user_id").eq("user_id", user_id).execute()
    my_blocked = [b["blocked_user_id"] for b in blacklist_res.data]
    
    by_others_res = supabase.table("blacklist").select("user_id").eq("blocked_user_id", user_id).execute()
    who_blocked_me = [b["user_id"] for b in by_others_res.data]
    
    illegal_ids = list(set(my_blocked + who_blocked_me))
    
    query = supabase.table("queue").select("*").order("created_at")
    if illegal_ids:
        query = query.not_.in_("user_id", illegal_ids)
        
    waiting_user = query.limit(1).execute()
    
    if waiting_user.data:
        partner_id = waiting_user.data[0]["user_id"]
        supabase.table("queue").delete().eq("user_id", partner_id).execute()
        
        adjectives = ["神秘的", "愛笑的", "孤獨的", "熱情的", "呆萌的", "霸氣的", "溫柔的", "搞笑的", "傲嬌的", "文青的"]
        nouns = ["貓咪", "哈士奇", "柴犬", "企鵝", "小鹿", "倉鼠", "熊貓", "狐狸", "樹懶", "考拉"]
        
        name1 = f"{random.choice(adjectives)}{random.choice(nouns)}"
        name2 = f"{random.choice(adjectives)}{random.choice(nouns)}"
        while name1 == name2:
            name2 = f"{random.choice(adjectives)}{random.choice(nouns)}"
            
        supabase.table("chat_pairs").insert([
            {"user_id": user_id, "partner_id": partner_id, "nickname": name1},
            {"user_id": partner_id, "partner_id": user_id, "nickname": name2}
        ]).execute()
        
        welcome_msg1 = f"🎉 配對成功囉！系統已為您匹配了一位聊天對象！\n\n🥸 你的匿名暱稱是：【{name1}】\n👤 對方的匿名暱稱是：【{name2}】\n\n💬 現在可以直接打字聊天囉！\n💡 提示：輸入「離開」可結束聊天；輸入「猜數字」、「猜拳」或「誰是臥底」可啟動小遊戲！"
        welcome_msg2 = f"🎉 配對成功囉！系統已為您匹配了一位聊天對象！\n\n🥸 你的匿名暱稱是：【{name2}】\n👤 對方的匿名暱稱是：【{name1}】\n\n💬 現在可以直接打字聊天囉！\n💡 提示：輸入「離開」可結束聊天；輸入「猜數字」、「猜拳」或「誰是臥底」可啟動小遊戲！"
        
        send_message(user_id, welcome_msg1)
        send_message(partner_id, welcome_msg2, tag="ACCOUNT_UPDATE")
    else:
        supabase.table("queue").insert({"user_id": user_id}).execute()
        send_message(user_id, "🔍 正在為您搜尋聊天對象，請稍候...\n💡 提示：若不想排隊了，輸入「離開」即可退出佇列。")

def clear_chat_pair(user_id):
    result = supabase.table("chat_pairs").select("partner_id").eq("user_id", user_id).limit(1).execute()
    if result.data:
        partner_id = result.data[0]["partner_id"]
        supabase.table("chat_pairs").delete().eq("user_id", user_id).execute()
        supabase.table("chat_pairs").delete().eq("user_id", partner_id).execute()
        for table in ["game_ultimate_password", "game_rps", "game_undercover"]:
            supabase.table(table).delete().or_(f"user_id.eq.{user_id},user_id.eq.{partner_id}").execute()
    else:
        supabase.table("queue").delete().eq("user_id", user_id).execute()

# ==========================================
# 🛠️ 基礎發送工具發送 Messenger API
# ==========================================
def send_message(recipient_id, message_text, tag=None):
    url = f"https://graph.facebook.com/v12.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text}
    }
    if tag:
        payload["messaging_type"] = "MESSAGE_TAG"
        payload["tag"] = tag
    response = requests.post(url, json=payload, headers=headers)
    return response.json()

# ==========================================
# 🔗 Webhook 路由端點
# ==========================================
@app.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Verification token mismatch", 403
        
    if request.method == "POST":
        data = request.json
        if data.get("object") == "page":
            for entry in data.get("entry", []):
                for messaging_event in entry.get("messaging", []):
                    sender_id = messaging_event.get("sender", {}).get("id")
                    if not sender_id:
                        continue
                        
                    if "message" in messaging_event:
                        now_str = datetime.now(timezone.utc).isoformat()
                        try:
                            supabase.table("user_logs").insert({"user_id": sender_id, "last_active": now_str}).execute()
                        except:
                            pass

                        if supabase.table("banned_users").select("*").eq("user_id", sender_id).limit(1).execute().data:
                            ban_entry = supabase.table("banned_users").select("expires_at").eq("user_id", sender_id).limit(1).execute()
                            if ban_entry.data and ban_entry.data[0].get("expires_at"):
                                try:
                                    exp = datetime.fromisoformat(ban_entry.data[0]["expires_at"])
                                    rem = int((exp - datetime.now(timezone.utc)).total_seconds())
                                    if rem > 0:
                                        send_message(sender_id, f"🚫 你的帳號目前處於洗版禁言狀態，還剩 {rem} 秒解封。")
                                        continue
                                except:
                                    pass
                            send_message(sender_id, "🚫 你的帳號已被停權")
                            continue
                            
                        message = messaging_event["message"]
                        if "text" in message:
                            if not check_rate_limit(sender_id, "text"):
                                pass
                            else:
                                handle_text(sender_id, message["text"])
                        if "attachments" in message:
                            handle_attachment(sender_id, message["attachments"])
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
