from flask import Flask, request
import os
import requests
import random

from datetime import datetime, timedelta, timezone

from supabase import create_client

app = Flask(__name__)

# =========================
# ENV
# =========================
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# =========================
# Supabase
# =========================
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# 隨機暱稱
# =========================
nickname_1 = [
    "星", "月", "白", "夜", "風",
    "雨", "雪", "海", "雲", "光",
    "影", "花", "羽", "夢", "霧"
]

nickname_2 = [
    "空", "辰", "羽", "夜", "風",
    "語", "海", "光", "夢", "森",
    "月", "雪", "櫻", "川", "歌"
]

emoji_list = [
    "🌙", "⭐", "🍀", "🌸", "☁️",
    "🔥", "🦋", "🌊", "❄️", "✨"
]

def generate_nickname():

    name = (
        random.choice(nickname_1) +
        random.choice(nickname_2)
    )

    emoji = random.choice(emoji_list)

    return f"{emoji} {name}"

# =========================
# 發送文字訊息
# =========================
def send_message(user_id, text):

    url = "https://graph.facebook.com/v19.0/me/messages"

    headers = {
        "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "recipient": {
            "id": user_id
        },
        "message": {
            "text": text
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=data
    )

    print(response.text)

# =========================
# 發送附件
# =========================
def send_attachment(user_id, attachment):

    url = "https://graph.facebook.com/v19.0/me/messages"

    headers = {
        "Authorization": f"Bearer {PAGE_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    data = {
        "recipient": {
            "id": user_id
        },
        "message": {
            "attachment": attachment
        }
    }

    response = requests.post(
        url,
        headers=headers,
        json=data
    )

    print(response.text)

# =========================
# 處理附件
# =========================
def handle_attachment(user_id, attachments):

    result = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()

    if not result.data:

        send_message(
            user_id,
            "輸入「開始」開始匿名聊天"
        )
        return

    partner = result.data[0]["partner_id"]

    for attachment in attachments:

        try:

            send_attachment(
                partner,
                attachment
            )

        except Exception as e:

            print(e)

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

    if data.get("object") == "page":

        for entry in data["entry"]:

            for messaging_event in entry["messaging"]:

                sender_id = messaging_event["sender"]["id"]

                if "message" in messaging_event:

                    message = messaging_event["message"]

                    # =========================
                    # 文字
                    # =========================
                    if "text" in message:

                        text = message["text"]

                        handle_text(sender_id, text)

                    # =========================
                    # 附件
                    # =========================
                    if "attachments" in message:

                        handle_attachment(
                            sender_id,
                            message["attachments"]
                        )

    return "ok", 200

# =========================
# 執行開始配對
# =========================
def start_match(user_id):

    check_waiting = supabase.table("waiting_users") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if check_waiting.data:

        send_message(user_id, "⏳ 你已經在等待配對中了")
        return

    check_chat = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if check_chat.data:

        send_message(user_id, "💬 你目前已經在聊天中了")
        return

    waiting_users = supabase.table("waiting_users") \
        .select("*") \
        .neq("user_id", user_id) \
        .execute()

    partner = None

    for row in waiting_users.data:

        target = row["user_id"]

        check1 = supabase.table("blacklist") \
            .select("*") \
            .eq("user_id", user_id) \
            .eq("blocked_user_id", target) \
            .execute()

        check2 = supabase.table("blacklist") \
            .select("*") \
            .eq("user_id", target) \
            .eq("blocked_user_id", user_id) \
            .execute()

        if check1.data or check2.data:
            continue

        partner = target
        break

    if partner:

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

        recent = supabase.table("recent_pairs") \
            .select("*") \
            .or_(
                f"and(user1.eq.{user_id},user2.eq.{partner}),"
                f"and(user1.eq.{partner},user2.eq.{user_id})"
            ) \
            .gte("created_at", one_hour_ago.isoformat()) \
            .execute()

        if recent.data:

            send_message(
                user_id,
                "⏳ 正在尋找新的聊天對象..."
            )

            return

        supabase.table("waiting_users") \
            .delete() \
            .eq("user_id", partner) \
            .execute()

        nickname1 = generate_nickname()
        nickname2 = generate_nickname()

        supabase.table("chat_pairs").insert([
            {
                "user_id": user_id,
                "partner_id": partner,
                "nickname": nickname1,
                "partner_nickname": nickname2
            },
            {
                "user_id": partner,
                "partner_id": user_id,
                "nickname": nickname2,
                "partner_nickname": nickname1
            }
        ]).execute()

        supabase.table("recent_pairs").insert({
            "user1": user_id,
            "user2": partner
        }).execute()

        send_message(
            user_id,
            f"✅ 配對成功！\n你的暱稱：{nickname1}"
        )

        send_message(
            partner,
            f"✅ 配對成功！\n你的暱稱：{nickname2}"
        )

    else:

        supabase.table("waiting_users") \
            .upsert({
                "user_id": user_id
            }) \
            .execute()

        send_message(user_id, "⏳ 等待配對中...")

# =========================
# 文字處理
# =========================
def handle_text(user_id, text):

    text = text.strip()

    try:

        # =========================
        # 開始
        # =========================
        if text == "開始":

            start_match(user_id)

            return

        # =========================
        # 下一位
        # =========================
        if text == "下一位":

            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if result.data:

                partner = result.data[0]["partner_id"]

                supabase.table("chat_pairs") \
                    .delete() \
                    .eq("user_id", user_id) \
                    .execute()

                supabase.table("chat_pairs") \
                    .delete() \
                    .eq("user_id", partner) \
                    .execute()

                try:
                    send_message(
                        partner,
                        "⚠️ 對方已離開聊天"
                    )
                except:
                    pass

            send_message(
                user_id,
                "🔄 正在幫你尋找下一位..."
            )

            start_match(user_id)

            return

        # =========================
        # 離開
        # =========================
        if text == "離開":

            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if not result.data:

                send_message(user_id, "目前沒有聊天對象")
                return

            partner = result.data[0]["partner_id"]

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", partner) \
                .execute()

            try:
                send_message(
                    partner,
                    "⚠️ 對方已離開聊天"
                )
            except:
                pass

            send_message(
                user_id,
                "✅ 你已離開聊天"
            )

            return

        # =========================
        # 封鎖
        # =========================
        if text == "封鎖":

            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if not result.data:

                send_message(user_id, "目前沒有聊天對象")
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

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", partner) \
                .execute()

            send_message(
                user_id,
                "🚫 已成功將對方封鎖，離開聊天室了"
            )

            try:
                send_message(
                    partner,
                    "🥲 對方似乎不喜歡你，已經離開聊天室"
                )
            except:
                pass

            return

        # =========================
        # 黑名單
        # =========================
        if text == "黑名單":

            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if not result.data:

                send_message(
                    user_id,
                    "📭 你的黑名單目前是空的"
                )
                return

            msg = "🚫 黑名單列表\n\n"

            for i, row in enumerate(result.data, start=1):

                blocked_id = row["blocked_user_id"]

                short_id = blocked_id[-6:]

                msg += f"{i}. 使用者 {short_id}\n"

            send_message(user_id, msg)

            return

        # =========================
        # 解除封鎖列表
        # =========================
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

                blocked_id = row["blocked_user_id"]

                short_id = blocked_id[-6:]

                msg += f"{i}. 使用者 {short_id}\n"

            msg += "\n例如：解除封鎖 1"

            send_message(user_id, msg)

            return

        # =========================
        # 執行解除封鎖
        # =========================
        if text.startswith("解除封鎖 "):

            parts = text.split()

            if len(parts) != 2:

                send_message(
                    user_id,
                    "❌ 格式錯誤\n例如：解除封鎖 1"
                )
                return

            try:
                index = int(parts[1]) - 1
            except:
                send_message(
                    user_id,
                    "❌ 請輸入正確數字"
                )
                return

            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if not result.data:

                send_message(
                    user_id,
                    "📭 黑名單是空的"
                )
                return

            if index < 0 or index >= len(result.data):

                send_message(
                    user_id,
                    "❌ 找不到此編號"
                )
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

        # =========================
        # 聊天轉發
        # =========================
        result = supabase.table("chat_pairs") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()

        if result.data:

            partner = result.data[0]["partner_id"]
            nickname = result.data[0]["nickname"]

            send_message(
                partner,
                f"{nickname}：{text}"
            )

        else:

            send_message(
                user_id,
                "輸入「開始」開始匿名聊天"
            )

    except Exception as e:

        print("錯誤")
        print(e)

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000
    )
