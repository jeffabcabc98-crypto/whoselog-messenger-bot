from flask import Flask, request
import os
import requests
import random
from datetime import datetime, timedelta, timezone
from supabase import create_client

# ======= 【安全防禦：動態安全匯入遊戲模組，防止找不到檔案崩潰】 =======
try:
    from number_bomb import start_ultimate_password, handle_guess
except ImportError:
    print("⚠️ [警告] 伺服器暫時找不到 number_bomb.py 模組！")
    start_ultimate_password = None
    handle_guess = None
# =====================================================================

app = Flask(__name__)

PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# 防洗版
# =========================
def check_rate_limit(user_id, msg_type):

    limits = {
        "text": (10, 5),
        "image": (60, 3),
        "gif": (60, 2),
        "video": (60, 1),
        "audio": (60, 3)
    }

    seconds, max_count = limits[msg_type]

    since_time = (
        datetime.now(timezone.utc)
        - timedelta(seconds=seconds)
    ).isoformat()

    result = supabase.table("rate_limits") \
        .select("*") \
        .eq("user_id", user_id) \
        .eq("msg_type", msg_type) \
        .gte("created_at", since_time) \
        .execute()

    if len(result.data) >= max_count:
        return False

   
    supabase.table("rate_limits").insert({
        "user_id": user_id,
        "msg_type": msg_type
    }).execute()

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

        # =========================
        # 先查本地資料庫 cache
        # =========================
        cached = supabase.table("users") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()

        if cached.data:

            fb_name = cached.data[0].get("fb_name")

            if fb_name:

                supabase.table("users") \
                    .update({
                        "last_seen": datetime.now(timezone.utc).isoformat()
                    }) \
                    .eq("user_id", user_id) \
                    .execute()

                print("USING CACHED FB NAME:", fb_name)

                return fb_name

        # =========================
        # 查 Facebook API
        # =========================
        response = requests.get(
            f"https://graph.facebook.com/v19.0/{user_id}",
            params={
                "fields": "first_name,last_name,name",
                "access_token": PAGE_ACCESS_TOKEN
            },
            timeout=15
        )

        response.raise_for_status()

        data = response.json()

        print("FB USER API:", data)

   
        name = (
            data.get("name")
            or (
                data.get("first_name", "") + " " + data.get("last_name", "")
            ).strip()
        )

        if not name:
            name = "未知使用者"

 
        # =========================
        # 存入 cache
        # =========================
        supabase.table("users").upsert({
            "user_id": user_id,
            "fb_name": name,
            "last_seen": datetime.now(timezone.utc).isoformat()
        }).execute()

        return name

    except Exception as e:

  
        print("GET USER NAME ERROR:", e)

        try:
            print("FB ERROR RESPONSE:", response.text)
        except:
            pass

        # =========================
        # API 失敗時再查 cache
        # =========================
        try:

          
            cached = supabase.table("users") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if cached.data:

              
                fb_name = cached.data[0].get(
                    "fb_name",
                    "未知使用者"
                )

                print("FALLBACK CACHE NAME:", fb_name)

                return fb_name

    
        except Exception as cache_error:

            print("CACHE FALLBACK ERROR:", cache_error)

        return "未知使用者"

# =========================
# 發送文字
# =========================
def send_message(user_id, text, tag=None):

    try:

        payload = {
            "recipient": {"id": user_id},
            "message": {"text": text}
        }

        if tag:
            payload["messaging_type"] = "MESSAGE_TAG"
            payload["tag"] = tag
        else:
            payload["messaging_type"] = "RESPONSE"

        response = requests.post(
            "https://graph.facebook.com/v25.0/me/messages",
            headers={
                "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=15
        )

        print("SEND MESSAGE:", response.text)

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
        
        "✨ 其他功能\n"

        "目前還處在開發階段，人可能會比較少，請各位還手下留情，多多幫小編推廣感激!!"
    )

# =========================
# 發送附件
# =========================
def send_attachment(user_id, attachment, tag=None):

    try:

        payload = {
            "recipient": {"id": user_id},
            "message": {"attachment": attachment}
        }

        if tag:
            payload["messaging_type"] = "MESSAGE_TAG"
            payload["tag"] = tag
        else:
            payload["messaging_type"] = "RESPONSE"

        response = requests.post(
            "https://graph.facebook.com/v25.0/me/messages",
            headers={
                "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )

        print("SEND ATTACHMENT:", response.text)

        response.raise_for_status()

    except Exception as e:

        print("SEND ATTACHMENT ERROR:", e)

# =========================
# 附件處理
# =========================
def handle_attachment(user_id, attachments):

    result = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()

    if not result.data:

        send_help_menu(user_id)
        return

    partner = result.data[0]["partner_id"]


    for attachment in attachments:

        try:

            attachment_type = attachment.get("type", "")
            payload = attachment.get("payload", {})
            url = payload.get("url", "")

            limit_type = None

            if attachment_type == "image" and (
               ".gif" in url.lower()
                or "gif" in url.lower()
            ):
                limit_type = "gif"

            elif attachment_type == "image":
                limit_type = "image"

            elif attachment_type == "video":
                limit_type = "video"

            elif attachment_type == "audio":
                limit_type = "audio"

            elif attachment_type == "file":

                send_message(
                    user_id,
                    "⚠️ 目前不支援檔案傳送"
                )

                continue

            if limit_type:

                if not check_rate_limit(
                    user_id,
                    limit_type
                ):

                    msgs = {
                        "image": "⚠️ 圖片傳送過快",
                        "gif": "⚠️ GIF 傳送過快",
                        "video": "⚠️ 影片傳送過快",
                        "audio": "⚠️ 語音傳送過快"
                    }

                    send_message(
                        user_id,
                        msgs[limit_type]
                    )

                    continue

            if "payload" in attachment:
                attachment["payload"].pop(
                    "sticker_id",
                    None
                )

            # 轉發附件給對方時加上 tag
            send_attachment(
                partner,
                attachment,
                tag="ACCOUNT_UPDATE"
            )

        except Exception as e:
            print("ATTACHMENT ERROR:", e)

# =========================
# 清理聊天室配對
# =========================
def clear_chat_pair(user_id):

    try:

        result = supabase.table("chat_pairs") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()

        if result.data:

            partner = result.data[0]["partner_id"]

            supabase.table("chat_pairs") \
                .delete() \
                .or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}") \
                .execute()

            supabase.table("chat_pairs") \
                .delete() \
                .or_(f"user_id.eq.{partner},partner_id.eq.{partner}") \
                .execute()

            supabase.table("waiting_users") \
                .delete() \
                .or_(f"user_id.eq.{user_id},user_id.eq.{partner}") \
                .execute()

            supabase.table("pending_actions") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

    except Exception as e:
        print("CLEAR CHAT ERROR:", e)

# =========================
# 使用者統計初始化
# =========================
def ensure_user_stats(user_id):

    check = supabase.table("user_stats") \
        .select("*") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()

    if not check.data:

        supabase.table("user_stats").insert({
             "user_id": user_id
        }).execute()

# =========================
# 增加風險分數
# =========================
def add_risk_score(
    user_id,
    block_add=0,
    report_add=0,
    risk_add=0
):

    ensure_user_stats(user_id)

    current = supabase.table("user_stats") \
        .select("*") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()

    if not current.data:
        return

    row = current.data[0]

  
    supabase.table("user_stats") \
        .update({
            "block_count": row["block_count"] + block_add,
            "report_count": row["report_count"] + report_add,
            "risk_score": row["risk_score"] + risk_add
        }) \
        .eq("user_id", user_id) \
        .execute()

# =========================
# 配對
# =========================
def start_match(user_id):

    waiting = supabase.table("waiting_users") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if waiting.data:

        send_message(
            user_id,
            "⏳ 你已經在等待配對中了"
        )
        return

    chatting = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if chatting.data:

        send_message(
            user_id,
            "💬 你目前已經在聊天中了"
        )
        return

    waiting_users = supabase.table("waiting_users") \
        .select("*") \
        .neq("user_id", user_id) \
        .execute()

   
    partner = None

    for row in waiting_users.data:

        target = row["user_id"]

        black1 = supabase.table("blacklist") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("blocked_user_id", target) \
            .execute()

        black2 = supabase.table("blacklist") \
            .select("*") \
            .eq("user_id", target) \
            .eq("blocked_user_id", user_id) \
            .execute()

        if black1.data or black2.data:
            continue

        
        one_day_ago = datetime.now(
            timezone.utc
        ) - timedelta(days=1)

        recent = supabase.table("recent_pairs") \
            .select("*") \
            .or_(
                f"and(user1.eq.{user_id},user2.eq.{target}),and(user1.eq.{target},user2.eq.{user_id})"
            ) \
            .gte(
                "created_at",
                one_day_ago.isoformat() 
            ) \
            .execute()

        if recent.data:
            continue

        partner = target
        break

    if partner:

        supabase.table("waiting_users") \
            .delete() \
            .eq("user_id", partner) \
            .execute()

        nickname1 = generate_nickname()
        nickname2 = generate_nickname()

        fb_name1 = get_user_name(user_id)
        fb_name2 = get_user_name(partner)

        supabase.table("chat_pairs").insert([
            {
                "user_id": user_id,
                "partner_id": partner,
                "nickname": nickname1,
                "partner_nickname": nickname2,
                "fb_name": fb_name1,
                "partner_fb_name": fb_name2
            },
            {
                "user_id": partner,
                "partner_id": user_id,
                "nickname": nickname2,
                "partner_nickname": nickname1,
                "fb_name": fb_name2,
                "partner_fb_name": fb_name1
            }
        ]).execute()

        supabase.table("recent_pairs").insert({
            "user1": user_id,
            "user2": partner
        }).execute()

        # 已更新：讓雙方配對成功時能知道彼此的暱稱
        send_message(
            user_id,
            f"✅ 配對成功！打聲招呼讓對方知道你的存在吧！\n"
            f"👤 你的暱稱：{nickname1}\n"
            f"💬 對方的暱稱：{nickname2}"
        )

        send_message(
            partner,
            f"✅ 配對成功！打聲招呼讓對方知道你的存在吧！\n"
            f"👤 你的暱稱：{nickname2}\n"
            f"💬 對方的暱稱：{nickname1}",
            tag="ACCOUNT_UPDATE"
        )

    
    else:

        supabase.table("waiting_users").insert({
             "user_id": user_id
        }).execute()

        send_message(
            user_id,
            "⏳ 等待配對中..."
        )

# =========================
# 文字處理
# =========================
def handle_text(user_id, text):

    text = text.strip()

    try:

        # ======= 【新增：終極密碼小遊戲關鍵字觸發】 =======
        if text == "終極密碼":
            if start_ultimate_password:
                result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
                if result.data:
                    partner = result.data[0]["partner_id"]
                    nickname1 = result.data[0]["nickname"]
                    nickname2 = result.data[0]["partner_nickname"]
                    start_ultimate_password(user_id, partner, nickname1, nickname2)
                    return
                else:
                    send_message(user_id, "⚠️ 必須在聊天對話中才能開始遊戲喔！")
                    return
            else:
                send_message(user_id, "⚠️ 遊戲功能暫時關閉，請確認伺服器有上傳 number_bomb.py。")
                return
        # ===============================================

        pending = supabase.table("pending_actions") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()

        if pending.data:

            action = pending.data[0]["action"]
            # 確認離開聊天室
            if action == "confirm_leave":

                if text in ["是", "1"]:

                    result = supabase.table("chat_pairs") \
                        .select("*") \
                        .eq("user_id", user_id) \
                        .limit(1) \
                        .execute()

                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

                    if not result.data:

                        send_message(
                            user_id,
                            "開目前沒有聊天對象"
                        )

                        return

           
                    partner = result.data[0]["partner_id"]

                    clear_chat_pair(user_id)

                    try:
                        send_message(
                            partner,
                            "⚠️ 對方已離開聊天室",
                            tag="ACCOUNT_UPDATE"
                        )
                    except:
                        pass

                    send_message(
                        user_id,
                        "✅ 你已離開聊天"
                    )

                    return

                if text in ["否", "2"]:

               
                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

                   
                    send_message(
                        user_id,
                        "✅ 已取消離開聊天室"
                    )

                    return

          
                send_message(
                    user_id,
                    "請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否"
                )

                return

            # 確認封鎖
            if action == "confirm_block":

                if text in ["是", "1"]:

                    result = supabase.table("chat_pairs") \
                        .select("*") \
                        .eq("user_id", user_id) \
                        .limit(1) \
                        .execute()

                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

                    if not result.data:

                        send_message(
                            user_id,
                            "開目前沒有聊天對象"
                        )

                        return

 
                    partner = result.data[0]["partner_id"]

                    check = supabase.table("blacklist") \
                        .select("*") \
                        .eq("user_id", user_id) \
                        .eq("blocked_user_id", partner) \
                        .execute()

                    if check.data:

                        send_message(
                            user_id,
                            "⚠️ 你已經封鎖過此人"
                        )

                        return

     
                    supabase.table("blacklist").insert({
                        "user_id": user_id,
                        "blocked_user_id": partner
                    }).execute()

               
                    pair_data = supabase.table("chat_pairs") \
                        .select("*") \
                        .eq("user_id", user_id) \
                        .limit(1) \
                        .execute()

                    reporter_name = "未知使用者"
                    reported_name = "未知使用者"

                    if pair_data.data:

                        reporter_name = pair_data.data[0].get(
                            "fb_name",
                            "未知使用者"
                        )

                     
                        reported_name = pair_data.data[0].get(
                            "partner_fb_name",
                            "未知使用者"
                        )

               
                    supabase.table("reports").insert({
                        "reporter_id": user_id,
                        "reporter_name": reporter_name,
                        "reported_user_id": partner,
                        "reported_name": reported_name,
                        "reason": "使用者封鎖"
                    }).execute()

                    add_risk_score(
                        partner,
                        block_add=1,
                        report_add=1,
                        risk_add=4
                    )

              
                    clear_chat_pair(user_id)

                    send_message(
                        user_id,
                        "🚫 已成功將對方封鎖"
                    )
                    try:
                        send_message(
                            partner,
                            "🥲 對方似乎不喜歡你，已離開聊天室",
                            tag="ACCOUNT_UPDATE"
                        )
                    except:
                        pass

                    return

                if text in ["否", "2"]:

                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

                    send_message(
                        user_id,
                        "✅ 已取消封鎖"
                    )

                    return

                send_message(
                    user_id,
                    "請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否"
                )

                return
            

            # 確認下一位
            if action == "confirm_next":

    
                if text in ["是", "1"]:

                    result = supabase.table("chat_pairs") \
                        .select("*") \
                        .eq("user_id", user_id) \
                        .limit(1) \
                        .execute()

                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

                    if result.data:

                        partner = result.data[0]["partner_id"]

                  
                        supabase.table("recent_pairs").insert({
                            "user1": user_id,
                            "user2": partner
                        }).execute()

            
                        clear_chat_pair(user_id)

                    try:
                        send_message(
                            partner,
                            "🥲 對方似乎不喜歡你，已離開聊天室",
                            tag="ACCOUNT_UPDATE"
                        )
                    except:
                        pass

                    send_message(
                        user_id,
                        "🔄 正在幫你尋找下一位..."
                    )

                    start_match(user_id)

                    return

                if text in ["否", "2"]:

               
                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

                   
                    send_message(
                        user_id,
                        "✅ 已取消尋找下一位"
                    )

                    return

          
                send_message(
                    user_id,
                    "請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否"
                )

                return

            # 檢舉原因
            if action == "report_reason":

                target_user = pending.data[0]["target_user_id"]

                if text == "返回":

                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

                    send_message(
                        user_id,
                        "✅ 已取消檢舉"
                    )

                    return

                reason = text.strip()

                if not reason:

            
                    send_message(
                        user_id,
                        "⚠️ 請輸入檢舉原因"
                    )

                    return

   
                pair_data = supabase.table("chat_pairs") \
                    .select("*") \
                    .eq("user_id", user_id) \
                    .limit(1) \
                    .execute()

                reporter_name = "未知使用者"
                reported_name = "未知使用者"

                if pair_data.data:

                    reporter_name = pair_data.data[0].get(
                        "fb_name",
                        "未知使用者"
                    )

                    reported_name = pair_data.data[0].get(
                        "partner_fb_name",
                        "未知使用者"
                    )

                supabase.table("reports").insert({
                    "reporter_id": user_id,
                    "reporter_name": reporter_name,
                    "reported_user_id": target_user,
                    "reported_name": reported_name,
                    "reason": reason
                }).execute()

                add_risk_score(
                    target_user,
                    report_add=1,
                    risk_add=3
                )

                supabase.table("pending_actions") \
                    .delete() \
                    .eq("user_id", user_id) \
                    .execute()

                supabase.table("pending_actions").insert({
                    "user_id": user_id,
                    "action": "report_confirm",
                    "target_user_id": target_user
                }).execute()

                send_message(
                    user_id,
                    "✅ 已送出檢舉\n\n是否要封鎖並離開聊天室？\n\n請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否"
                )

                return

            # 檢舉確認
            if action == "report_confirm":

                target_user = pending.data[0]["target_user_id"]

                check = supabase.table("blacklist") \
                    .select("*") \
                    .eq("user_id", user_id) \
                    .eq("blocked_user_id", target_user) \
                    .execute()

                if check.data:

   
                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

       
                    clear_chat_pair(user_id)

                    send_message(
                        user_id,
                        "⚠️ 你已經封鎖過此人"
                    )

                    return

                if text in ["是", "1"]:

                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

                    supabase.table("blacklist").insert({
                        "user_id": user_id,
                        "blocked_user_id": target_user
                    }).execute()

                    clear_chat_pair(user_id)

                    send_message(
                        user_id,
                        "🚫 已封鎖對方並離開聊天室"
                    )

                    try:
                        send_message(
                            target_user,
                            "🥲 對方似乎不喜歡你，已離開聊天室",
                            tag="ACCOUNT_UPDATE"
                        )
                    except:
                        pass

                    return

                if text in ["否", "2"]:

                    supabase.table("pending_actions") \
                        .delete() \
                        .eq("user_id", user_id) \
                        .execute()

   
                    send_message(
                        user_id,
                        "✅ 已完成檢舉"
                    )

              
                    return

                send_message(
                    user_id,
                    "請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否"
                )

                return

  
        # 開始
        if text in ["開始", "0011"]:

            start_match(user_id)
            return

        # 取消配對
        if text in ["取消配對", "0022"]:

            check = supabase.table("waiting_users") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if not check.data:

                send_message(
                    user_id,
                    "❌ 目前沒有在等待配對"
                )

                return

            supabase.table("waiting_users") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

   
            send_message(
                user_id,
                "✅ 已取消配對"
            )

            return

        # 下一位
        if text in ["下一位", "0033"]:

            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if not result.data:

                send_message(
                    user_id,
                    "目前沒有聊天對象"
                )

                return

            supabase.table("pending_actions") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

            supabase.table("pending_actions").insert({
                "user_id": user_id,
                "action": "confirm_next"
            }).execute()

      
            send_message(
                user_id,
                "⚠️ 確定要離開目前聊天室並尋找下一位嗎？\n\n請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否"
            )

            return

        # 離開
        if text in ["離開", "0088"]:

            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if not result.data:

               
                send_message(
                    user_id,
                    "開目前沒有聊天對象"
                )

                return

            supabase.table("pending_actions") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

            supabase.table("pending_actions").insert({
                "user_id": user_id,
                "action": "confirm_leave"
            }).execute()

     
            send_message(
                user_id,
                "⚠️ 確定要離開聊天室嗎？\n\n請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否"
            )

            return

        # 封鎖
        if text in ["封鎖", "0099"]:

           
            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if not result.data:

              
                send_message(
                    user_id,
                    "目前沒有聊天對象"
                )

                return

            partner = result.data[0]["partner_id"]

        
            check = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .eq("blocked_user_id", partner) \
                .execute()

            if check.data:

           
                send_message(
                    user_id,
                    "⚠️ 你已經封鎖過此人"
                )

                return

            supabase.table("pending_actions") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

            supabase.table("pending_actions").insert({
                "user_id": user_id,
                "action": "confirm_block"
            }).execute()

            send_message(
                user_id,
                "⚠️ 確定要封鎖對方嗎？\n\n請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否"
            )

            return

        # 黑名單
        if text == "黑名單":

       
            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if not result.data:

                send_message(
                     user_id,
                    "📭 黑名單目前是空的"
                )

                return

            msg = "🚫 黑名單列表\n\n"

            for i, row in enumerate(result.data, start=1):

                msg += f"{i}. 使用者 {row['blocked_user_id'][-6:]}\n"

            send_message(user_id, msg)

            return

        # 解除封鎖列表
        if text == "解除封鎖":

            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if not result.data:

                send_message(
                    user_id,
                    "📭 目前沒有封鎖任何人"
                )

 
                return

            msg = "🔓 請輸入要解除封鎖的編號\n\n"

            for i, row in enumerate(result.data, start=1):

                msg += f"{i}. 使用者 {row['blocked_user_id'][-6:]}\n"

            msg += "\n例如：解除封鎖 1"

            send_message(user_id, msg)

            return

        # 執行解除封鎖
        if text.startswith("解除封鎖 "):

            try:
                index = int(text.split()[1]) - 1
        
            except:
                send_message(user_id, "❌ 格式錯誤")
                return

            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if index < 0 or index >= len(result.data):

                send_message(user_id, "❌ 找不到此編號")
                return

            blocked_user = result.data[index]["blocked_user_id"]

            supabase.table("blacklist") \
                .delete() \
                .eq("user_id", user_id) \
                .eq("blocked_user_id", blocked_user) \
                .execute()

            send_message(
                user_id,
                "✅ 已成功解除封鎖"
            )

            return

        # 解除配對限制
        if text in ["解除配對限制", "2222"]:

            supabase.table("recent_pairs") \
                .delete() \
                .or_(f"user1.eq.{user_id},user2.eq.{user_id}") \
                .execute()

            send_message(
                user_id,
                "✅ 已解除配對限制"
            )

            return

        # 檢舉
        if text in ["檢舉", "0066"]:

            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if not result.data:

                send_message(
                    user_id,
                    "目前沒有聊天對象"
                )

                return

            partner = result.data[0]["partner_id"]

     
            supabase.table("pending_actions") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

            supabase.table("pending_actions").insert({
                "user_id": user_id,
                "action": "report_reason",
                "target_user_id": partner
            }).execute()

            send_message(
                user_id,
                "🚨 請輸入檢舉原因\n\n如果不想檢舉了請輸入：返回"
            )

         
            return

        # 聊天轉發
        result = supabase.table("chat_pairs") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()

        if result.data:

            partner = result.data[0]["partner_id"]
            nickname = result.data[0]["nickname"]

            # ======= 【優先攔截猜數字與外掛指令】 =======
            if handle_guess and handle_guess(user_id, text):
                return
            # =============================================

            # 轉發
            send_message(
                partner,
                f"{nickname}：{text}",
                tag="ACCOUNT_UPDATE"
            )

        else:

            send_help_menu(user_id)

    except Exception as e:
        print("HANDLE_TEXT ERROR:", e)

# =========================
# Webhook 驗證
# =========================
@app.route("/webhook", methods=["GET"])
def verify():

    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if token == VERIFY_TOKEN:
        return challenge

    return "驗證失敗"

# =========================
# Webhook
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():

    data = request.json

    if data["object"] in ["page", "instagram"]:

        for entry in data["entry"]:
        
            print("ENTRY:", entry)
     
            # =========================
            # Instagram webhook
            # =========================
            if "changes" in entry:
        
                print("INSTAGRAM CHANGES:", entry["changes"])
        
                for change in entry["changes"]:
        
                    value = change.get("value", {})
        
                    if "messages" in value:
        
                        for msg in value["messages"]:
        
                            sender_id = msg["from"]["id"]
        
                            print("IG MESSAGE:", msg)
        
                            # 文字
                            if "text" in msg:
        
                                text = msg["text"]
     
                                handle_text(
                                    sender_id,
                                    text
                                )
        
                            # 附件
                            if "attachments" in msg:
        
                                handle_attachment(
                                    sender_id,
                                    msg["attachments"]
                                )
        
            print("FULL WEBHOOK:", data)
  
        
            # =========================
            # Facebook Messenger webhook
            # =========================
            if "messaging" not in entry:
                continue

            for messaging_event in entry["messaging"]:

                sender_id = messaging_event["sender"]["id"]

                # ===== 選單按鈕 =====
                if "postback" in messaging_event:
                
                    payload = messaging_event["postback"]["payload"]
            
                    if payload == "GET_STARTED":

                        send_help_menu(sender_id)

                    elif payload == "START_CHAT":
                
                        handle_text(sender_id, "開始")
                 
                    elif payload == "LEAVE_CHAT":
                
                        handle_text(sender_id, "離開")
    

                # ===== 一般訊息 =====
                if "message" in messaging_event:

                    banned = supabase.table("banned_users") \
                        .select("*") \
                        .eq("user_id", sender_id) \
                        .limit(1) \
                        .execute()

                    if banned.data:

                        send_message(
                            sender_id,
                            "🚫 你的帳號已被停權"
                        )

                        continue

                    message = messaging_event["message"]

                    if "text" in message:

                        text = message["text"]

                        if not check_rate_limit(
                            sender_id,
                            "text"
                        ):

                            send_message(
                                sender_id,
                                "⚠️ 傳送過快，請稍後再試"
                             )

                        else:

                            handle_text(
                                sender_id,
                                text
                            )

                    if "attachments" in message:

                        handle_attachment(
                            sender_id,
                            message["attachments"]
                        )

    return "ok", 200

if __name__ == "__main__":
    try:
        setup_persistent_menu()
    except NameError:
        print("setup_persistent_menu is not defined, boot sequence continues...")

    app.run(
        host="0.0.0.0",
        port=5000
    )
