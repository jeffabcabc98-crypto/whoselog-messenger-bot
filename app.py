from flask import Flask, request
import os
import requests
import random
from datetime import datetime, timedelta, timezone
from supabase import create_client

# ======= 【安全防禦：動態安全匯入所有外部模組，防止找不到檔案崩潰】 =======
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
# 🛡️ 防洗版（已整合：30秒限5次 ＆ 自動禁言60秒機制）
# ==========================================
def check_rate_limit(user_id, msg_type):
    # 1. 精準修改：文字(text)設定為 30 秒內只能傳 5 次
    limits = {
        "text": (30, 10),      
        "image": (60, 3),
        "gif": (60, 2),
        "video": (60, 1),
        "audio": (60, 3)
    }
    seconds, max_count = limits[msg_type]
    now = datetime.now(timezone.utc)
    since_time = (now - timedelta(seconds=seconds)).isoformat()

    # 2. 撈取該用戶在此區間內傳送的次數
    result = supabase.table("rate_limits").select("*").eq("user_id", user_id).eq("msg_type", msg_type).gte("created_at", since_time).execute()
    
    if len(result.data) >= max_count:
        # 🚨【核心機制觸發】：當文字傳送次數超過限制，發動「自動禁言 60 秒」
        if msg_type == "text":
            unban_time = (now + timedelta(seconds=60)).isoformat() # 計算 60 秒後的解封時間
            try:
                # 將此壞壞用戶塞入你的 banned_users 資料表，並標記解封時間
                supabase.table("banned_users").upsert({
                    "user_id": user_id,
                    "reason": "文字傳送過快，系統自動禁言60秒",
                    "expires_at": unban_time  # 注意：請確認你的 banned_users 表裡有無 expires_at 欄位
                }).execute()
                
                # 發送給被禁言用戶的當頭棒喝通知
                send_message(user_id, "🚨 警告：偵測到你傳送文字速度過快，已被系統自動禁言 60 秒！請稍候再試。")
            except Exception as ban_err:
                print("AUTOMATIC BAN ERROR:", ban_err)
        return False

    # 3. 如果沒超過限制，正常塞入這次的紀錄
    supabase.table("rate_limits").insert({"user_id": user_id, "msg_type": msg_type}).execute()
    return True

# =========================
# 暱稱
# =========================
nickname_1 = ["星","月","白","夜","風","雨","雪","海","雲","光","石","黑","影","安","亮"]
nickname_2 = ["空","辰","羽","夜","風","語","海","夢","森","歌","固","晨","霧","悟","凸"]

def generate_nickname():
    return f"{random.choice(nickname_1)}{random.choice(nickname_2)}"

# =========================
# FB 名稱
# =========================
def get_user_name(user_id):
    try:
        cached = supabase.table("users").select("*").eq("user_id", user_id).limit(1).execute()
        if cached.data:
            fb_name = cached.data[0].get("fb_name")
            if fb_name:
                supabase.table("users").update({"last_seen": datetime.now(timezone.utc).isoformat()}).eq("user_id", user_id).execute()
                return fb_name

        response = requests.get(
            f"https://graph.facebook.com/v19.0/{user_id}",
            params={"fields": "first_name,last_name,name", "access_token": PAGE_ACCESS_TOKEN},
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        name = data.get("name") or (data.get("first_name", "") + " " + data.get("last_name", "")).strip()
        if not name: name = "未知使用者"

        supabase.table("users").upsert({"user_id": user_id, "fb_name": name, "last_seen": datetime.now(timezone.utc).isoformat()}).execute()
        return name
    except Exception as e:
        print("GET USER NAME ERROR:", e)
        try:
            cached = supabase.table("users").select("*").eq("user_id", user_id).limit(1).execute()
            if cached.data: return cached.data[0].get("fb_name", "未知使用者")
        except: pass
        return "未知使用者"

# =========================
# 發送文字
# =========================
def send_message(user_id, text, tag=None):
    try:
        payload = {"recipient": {"id": user_id}, "message": {"text": text}}
        payload["messaging_type"] = "MESSAGE_TAG" if tag else "RESPONSE"
        if tag: payload["tag"] = tag

        response = requests.post(
            "https://graph.facebook.com/v25.0/me/messages",
            headers={"Authorization": f"Bearer {PAGE_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json=payload, timeout=15
        )
        response.raise_for_status()
    except Exception as e:
        print("SEND MESSAGE ERROR:", e)

# =========================
# 功能列表
# =========================
def send_help_menu(user_id):
    send_message(
        user_id,
        "🌌 歡迎使用匿名日誌 Whose log\n\n"
        "📌 功能列表\n\n"
        "💬 聊天功能\n"
        "• 開始 / 0011\n"
        "• 下一位 / 0033\n"
        "• 離開 / 0088\n\n"
        "🚫 安全功能\n"
        "• 封鎖 / 0099\n"
        "• 檢舉 / 0066\n"
        "• 黑名單\n"
        "• 解除封鎖\n\n"
        "🎮 互動小遊戲（配對成功後方可輸入）\n"
        "• 輸入【終極密碼】: 開啟猜數字炸彈遊戲\n"
        "• 輸入【猜拳】: 開啟不留痕跡秘密猜拳\n"
        "• 輸入【誰是臥底】: 開啟雙人詞彙臥底推理\n"
        "• 輸入【取消遊玩】: 隨時終止進行中的小遊戲\n\n"
        "目前還處在開發階段，人可能會比較少，請各位還手下留情，多多幫小編推廣感激!!"
    )

# =========================
# 發送附件與附件處理
# =========================
def send_attachment(user_id, attachment, tag=None):
    try:
        payload = {"recipient": {"id": user_id}, "message": {"attachment": attachment}}
        payload["messaging_type"] = "MESSAGE_TAG" if tag else "RESPONSE"
        if tag: payload["tag"] = tag
        response = requests.post(
            "https://graph.facebook.com/v25.0/me/messages",
            headers={"Authorization": f"Bearer {PAGE_ACCESS_TOKEN}", "Content-Type": "application/json"},
            json=payload, timeout=30
        )
        response.raise_for_status()
    except Exception as e:
        print("SEND ATTACHMENT ERROR:", e)

def handle_attachment(user_id, attachments):
    result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
    if not result.data:
        send_help_menu(user_id)
        return
    partner = result.data[0]["partner_id"]

    for attachment in attachments:
        try:
            attachment_type = attachment.get("type", "")
            url = attachment.get("payload", {}).get("url", "")
            limit_type = None

            if attachment_type == "image" and (".gif" in url.lower() or "gif" in url.lower()): limit_type = "gif"
            elif attachment_type == "image": limit_type = "image"
            elif attachment_type == "video": limit_type = "video"
            elif attachment_type == "audio": limit_type = "audio"
            elif attachment_type == "file":
                send_message(user_id, "⚠️ 目前不支援檔案傳送")
                continue

            if limit_type and not check_rate_limit(user_id, limit_type):
                msgs = {"image": "⚠️ 圖片傳送過快", "gif": "⚠️ GIF 傳送過快", "video": "⚠️ 影片傳送過快", "audio": "⚠️ 語音傳送過快"}
                send_message(user_id, msgs[limit_type])
                continue

            if "payload" in attachment: attachment["payload"].pop("sticker_id", None)
            send_attachment(partner, attachment, tag="ACCOUNT_UPDATE")
        except Exception as e:
            print("ATTACHMENT ERROR:", e)

# =========================
# 清理聊天室配對與風險分數
# =========================
def clear_chat_pair(user_id):
    try:
        result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
        if result.data:
            partner = result.data[0]["partner_id"]
            supabase.table("chat_pairs").delete().or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").execute()
            supabase.table("chat_pairs").delete().or_(f"user_id.eq.{partner},partner_id.eq.{partner}").execute()
            supabase.table("waiting_users").delete().or_(f"user_id.eq.{user_id},user_id.eq.{partner}").execute()
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
    except Exception as e:
        print("CLEAR CHAT ERROR:", e)

def ensure_user_stats(user_id):
    check = supabase.table("user_stats").select("*").eq("user_id", user_id).limit(1).execute()
    if not check.data: supabase.table("user_stats").insert({"user_id": user_id}).execute()

def add_risk_score(user_id, block_add=0, report_add=0, risk_add=0):
    ensure_user_stats(user_id)
    current = supabase.table("user_stats").select("*").eq("user_id", user_id).limit(1).execute()
    if not current.data: return
    row = current.data[0]
    supabase.table("user_stats").update({
        "block_count": row["block_count"] + block_add,
        "report_count": row["report_count"] + report_add,
        "risk_score": row["risk_score"] + risk_add
    }).eq("user_id", user_id).execute()

# =========================
# 配對系統邏輯
# =========================
def start_match(user_id):
    if supabase.table("waiting_users").select("*").eq("user_id", user_id).execute().data:
        send_message(user_id, "⏳ 你已經在等待配對中了，目前人數較少須等待，還請各位幫小編多多推廣!!")
        return
    if supabase.table("chat_pairs").select("*").eq("user_id", user_id).execute().data:
        send_message(user_id, "💬 你目前已經在聊天中了")
        return

    waiting_users = supabase.table("waiting_users").select("*").neq("user_id", user_id).execute()
    partner = None

    for row in waiting_users.data:
        target = row["user_id"]
        if supabase.table("blacklist").select("*").eq("user_id", user_id).eq("blocked_user_id", target).execute().data: continue
        if supabase.table("blacklist").select("*").eq("user_id", target).eq("blocked_user_id", user_id).execute().data: continue

        one_day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        if supabase.table("recent_pairs").select("*").or_(f"and(user1.eq.{user_id},user2.eq.{target}),and(user1.eq.{target},user2.eq.{user_id})").gte("created_at", one_day_ago).execute().data: continue

        partner = target
        break

    if partner:
        supabase.table("waiting_users").delete().eq("user_id", partner).execute()
        nickname1, nickname2 = generate_nickname(), generate_nickname()
        fb_name1, fb_name2 = get_user_name(user_id), get_user_name(partner)

        supabase.table("chat_pairs").insert([
            {"user_id": user_id, "partner_id": partner, "nickname": nickname1, "partner_nickname": nickname2, "fb_name": fb_name1, "partner_fb_name": fb_name2},
            {"user_id": partner, "partner_id": user_id, "nickname": nickname2, "partner_nickname": nickname1, "fb_name": fb_name2, "partner_fb_name": fb_name1}
        ]).execute()
        supabase.table("recent_pairs").insert({"user1": user_id, "user2": partner}).execute()

        msg_template = "✅ 配對成功！打聲招呼讓對方知道你的存在吧！\n👤 你的暱稱：{}\n💬 對方的暱稱：{}\n\n🎮 目前有新增小遊戲輸入「終極密碼」、「猜拳」或「誰是臥底」跟對方一起玩吧！"
        send_message(user_id, msg_template.format(nickname1, nickname2))
        send_message(partner, msg_template.format(nickname2, nickname1), tag="ACCOUNT_UPDATE")
    else:
        supabase.table("waiting_users").insert({"user_id": user_id}).execute()
        send_message(user_id, "⏳ 等待配對中...目前人數較少須等待，還請各位幫小編多多推廣!!")

# =========================
# 文字處理核心 
# =========================
def handle_text(user_id, text):
    text = text.strip()
    
    # 🎯 就是這裡！一定要加上 try: 這三個字與冒號
    try:
        from game_modules import start_rps, handle_rps_move, start_undercover, handle_undercover_vote, cancel_game
    except ImportError:
        print("⚠️ [內部警告] 暫時無法加載 game_modules.py！")
        start_rps = handle_rps_move = start_undercover = handle_undercover_vote = cancel_game = None

    # ======= 【1. 管理員廣播與指令系統】 =======
    admin_ids = ["6564639913619557", "9563503117006764"]
    if user_id in admin_ids:
    
            # ======= 【1. 優先核心攔截：取消遊玩】 =======
            if text == "取消遊玩":
            if cancel_game and cancel_game(user_id): return
            send_message(user_id, "❌ 目前沒有正在進行中的互動小遊戲喔！")
            return

        # ======= 【2. 安全防禦：防止同時開啟多個小遊戲 ＆ 重複洗開局】 =======
        if text in ["終極密碼", "猜拳", "誰是臥底"]:
            result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
            if not result.data:
                send_message(user_id, "⚠️ 必須在聊天對話中才能開始遊戲喔！")
                return
                
            partner, n1, n2 = result.data[0]["partner_id"], result.data[0]["nickname"], result.data[0]["partner_nickname"]
            
            has_bomb = supabase.table("game_ultimate_password").select("id").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").execute().data
            has_rps = supabase.table("game_rps").select("id").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").execute().data
            has_spy = supabase.table("game_undercover").select("id").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").execute().data
            
            if has_bomb or has_rps or has_spy:
                send_message(user_id, "⚠️ 目前已有互動小遊戲（猜拳/終極密碼/誰是臥底）正在進行中，不能重複開啟！\n\n請先將當前遊戲玩完，或輸入「取消遊玩」結束遊戲後，才能開啟新局喔！")
                return

            if text == "終極密碼" and start_ultimate_password: start_ultimate_password(user_id, partner, n1, n2)
            elif text == "猜拳" and start_rps: start_rps(user_id, partner, n1, n2)
            elif text == "誰是臥底" and start_undercover: start_undercover(user_id, partner, n1, n2)
            return

        # ======= 【3. 外部化Pending指令處理】 =======
        pending = supabase.table("pending_actions").select("*").eq("user_id", user_id).limit(1).execute()
        if pending.data:
            if handle_pending_actions and handle_pending_actions(user_id, text, pending.data[0]["action"], pending.data[0]):
                return

        # ======= 【4. 行政/常規指令觸發】 =======
        if text in ["開始", "0011"]: start_match(user_id); return
        if text in ["取消配對", "0022"]:
            if not supabase.table("waiting_users").select("*").eq("user_id", user_id).execute().data:
                send_message(user_id, "❌ 目前沒有在等待配對")
                return
            supabase.table("waiting_users").delete().eq("user_id", user_id).execute()
            send_message(user_id, "✅ 已取消配對"); return

        if text in ["下一位", "0033", "離開", "0088", "封鎖", "0099", "檢舉", "0066"]:
            result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
            if not result.data:
                send_message(user_id, "目前沒有聊天對象")
                return
            partner = result.data[0]["partner_id"]
            
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            
            if text in ["下一位", "0033"]:
                supabase.table("pending_actions").insert({"user_id": user_id, "action": "confirm_next"}).execute()
                send_message(user_id, "⚠️ 確定要離開目前聊天室並尋找下一位嗎？\n\n請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否")
            elif text in ["離開", "0088"]:
                supabase.table("pending_actions").insert({"user_id": user_id, "action": "confirm_leave"}).execute()
                send_message(user_id, "⚠️ 確定要離開聊天室嗎？\n\n請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否")
            elif text in ["封鎖", "0099"]:
                if supabase.table("blacklist").select("*").eq("user_id", user_id).eq("blocked_user_id", partner).execute().data:
                    send_message(user_id, "⚠️ 你已經封鎖過此人"); return
                supabase.table("pending_actions").insert({"user_id": user_id, "action": "confirm_block"}).execute()
                send_message(user_id, "⚠️ 確定要封鎖對方嗎？\n\n請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否")
            elif text in ["檢舉", "0066"]:
                supabase.table("pending_actions").insert({"user_id": user_id, "action": "report_reason", "target_user_id": partner}).execute()
                send_message(user_id, "🚨 請輸入檢舉原因\n\n如果不想檢舉了請輸入：返回")
            return

        if text == "黑名單":
            res = supabase.table("blacklist").select("*").eq("user_id", user_id).execute()
            if not res.data: send_message(user_id, "📭 黑名單目前是空的"); return
            send_message(user_id, "🚫 黑名單列表\n\n" + "".join([f"{i}. 使用者 {r['blocked_user_id'][-6:]}\n" for i, r in enumerate(res.data, start=1)])); return

        if text == "解除封鎖":
            res = supabase.table("blacklist").select("*").eq("user_id", user_id).execute()
            if not res.data: send_message(user_id, "📭 目前沒有封鎖任何人"); return
            send_message(user_id, "🔓 請輸入要解除封鎖的編號\n\n" + "".join([f"{i}. 使用者 {r['blocked_user_id'][-6:]}\n" for i, r in enumerate(res.data, start=1)]) + "\n例如：解除封鎖 1")
            return

        if text.startswith("解除封鎖 "):
            try: index = int(text.split()[1]) - 1
            except: send_message(user_id, "❌ 格式錯誤"); return
            res = supabase.table("blacklist").select("*").eq("user_id", user_id).execute()
            if index < 0 or index >= len(res.data): send_message(user_id, "❌ 找不到此編號"); return
            supabase.table("blacklist").delete().eq("user_id", user_id).eq("blocked_user_id", res.data[index]["blocked_user_id"]).execute()
            send_message(user_id, "✅ 已成功解除封鎖"); return

        if text in ["解除配對限制", "2222"]:
            supabase.table("recent_pairs").delete().or_(f"user1.eq.{user_id},user2.eq.{user_id}").execute()
            send_message(user_id, "✅ 已解除配對限制"); return

        # ======= 【5. 聊天普通轉發與所有小遊戲輸入攔截】 =======
        result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
        if result.data:
            if handle_guess and handle_guess(user_id, text.strip()): return
            if handle_rps_move and handle_rps_move(user_id, text.strip()): return
            if handle_undercover_vote and handle_undercover_vote(user_id, text.strip()): return
            send_message(result.data[0]["partner_id"], f"{result.data[0]['nickname']}：{text}", tag="ACCOUNT_UPDATE")
        else:
            send_help_menu(user_id)
    except Exception as e:
        print("HANDLE_TEXT ERROR:", e)

# =========================
# Webhook 驗證與接收
# =========================
@app.route("/webhook", methods=["GET"])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN: return request.args.get("hub.challenge")
    return "驗證失敗"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if data.get("object") in ["page", "instagram"]:
        for entry in data.get("entry", []):
            if "changes" in entry:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    if "messages" in value:
                        for msg in value["messages"]:
                            sender_id = msg["from"]["id"]
                            
                            # ✨【自動自動解封過期用戶機制】：在收信當下，先自動清除所有已過期的封鎖
                            try:
                                now_str = datetime.now(timezone.utc).isoformat()
                                supabase.table("banned_users").delete().eq("user_id", sender_id).lt("expires_at", now_str).execute()
                            except:
                                pass
                                
                            if "text" in msg: handle_text(sender_id, msg["text"])
                            if "attachments" in msg: handle_attachment(sender_id, msg["attachments"])
            if "messaging" in entry:
                for messaging_event in entry.get("messaging", []):
                    sender_id = messaging_event["sender"]["id"]
                    if "postback" in messaging_event:
                        payload = messaging_event["postback"]["payload"]
                        if payload == "GET_STARTED": send_help_menu(sender_id)
                        elif payload in ["START_CHAT", "LEAVE_CHAT"]: handle_text(sender_id, "開始" if payload == "START_CHAT" else "離開")

                    if "message" in messaging_event:
                        # ✨【自動解封過期用戶機制】：Facebook 管道也同步做自動過期清理
                        try:
                            now_str = datetime.now(timezone.utc).isoformat()
                            supabase.table("banned_users").delete().eq("user_id", sender_id).lt("expires_at", now_str).execute()
                        except:
                            pass

                        if supabase.table("banned_users").select("*").eq("user_id", sender_id).limit(1).execute().data:
                            # 讀取剩餘時間提示玩家
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
                            send_message(sender_id, "🚫 你的帳號已被停權"); continue
                            
                        message = messaging_event["message"]
                        if "text" in message:
                            if not check_rate_limit(sender_id, "text"): pass # 觸發禁言通知後，在此直接攔截不往下跑
                            else: handle_text(sender_id, message["text"])
                        if "attachments" in message: handle_attachment(sender_id, message["attachments"])
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
