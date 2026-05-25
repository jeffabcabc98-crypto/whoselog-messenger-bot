from flask import Flask, request
import os
import requests
import random
from datetime import datetime, timedelta, timezone
from supabase import create_client

# ======= 模組匯入 =======
try:
    from number_bomb import start_ultimate_password, handle_guess
    from game_modules import start_rps, handle_rps_move, start_undercover, handle_undercover_vote, cancel_game
    from actions import handle_pending_actions
except ImportError:
    start_ultimate_password = handle_guess = start_rps = handle_rps_move = start_undercover = handle_undercover_vote = cancel_game = handle_pending_actions = None

app = Flask(__name__)
PAGE_ACCESS_TOKEN = os.getenv("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# ======= 基礎工具函式 =======
def send_message(user_id, text, tag=None):
    payload = {"recipient": {"id": user_id}, "message": {"text": text}}
    if tag: payload["messaging_type"] = "MESSAGE_TAG"; payload["tag"] = tag
    try:
        requests.post(f"https://graph.facebook.com/v25.0/me/messages?access_token={PAGE_ACCESS_TOKEN}", json=payload)
    except Exception as e:
        print("SEND ERROR:", e)

def generate_nickname():
    n1 = ["星","月","白","夜","風","雨","雪","海","雲","光","石","黑","影","安","亮"]
    n2 = ["空","辰","羽","夜","風","語","海","夢","森","歌","固","晨","霧","悟","凸"]
    return f"{random.choice(n1)}{random.choice(n2)}"

# ======= 核心功能：配對系統 (你之前消失的邏輯) =======
def start_match(user_id):
    # 檢查是否已在配對或聊天中
    if supabase.table("waiting_users").select("id").eq("user_id", user_id).execute().data or \
       supabase.table("chat_pairs").select("id").eq("user_id", user_id).execute().data:
        send_message(user_id, "⚠️ 你目前已在等待或聊天中。")
        return

    waiting = supabase.table("waiting_users").select("user_id").execute().data
    if waiting:
        partner = waiting[0]["user_id"]
        supabase.table("waiting_users").delete().eq("user_id", partner).execute()
        n1, n2 = generate_nickname(), generate_nickname()
        supabase.table("chat_pairs").insert([
            {"user_id": user_id, "partner_id": partner, "nickname": n1, "partner_nickname": n2},
            {"user_id": partner, "partner_id": user_id, "nickname": n2, "partner_nickname": n1}
        ]).execute()
        send_message(user_id, f"✅ 配對成功！你的暱稱：{n1}，對方暱稱：{n2}")
        send_message(partner, f"✅ 配對成功！你的暱稱：{n2}，對方暱稱：{n1}", tag="ACCOUNT_UPDATE")
    else:
        supabase.table("waiting_users").insert({"user_id": user_id}).execute()
        send_message(user_id, "⏳ 正在尋找配對中...")

# ======= 核心處理邏輯 =======
def handle_text(user_id, text):
    text = text.strip()
    
    # 1. 遊戲強制結束
    if text == "取消遊玩":
        if cancel_game and cancel_game(user_id): return
        send_message(user_id, "❌ 沒有進行中的小遊戲。")
        return

    # 2. 遊戲啟動攔截 (確保「誰是臥底」在此被正確捕捉)
    if text in ["終極密碼", "猜拳", "誰是臥底"]:
        pair = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute().data
        if not pair:
            send_message(user_id, "⚠️ 請先輸入「開始」配對成功後才能遊戲！")
            return
        
        partner, n1, n2 = pair[0]["partner_id"], pair[0]["nickname"], pair[0]["partner_nickname"]
        
        # 遊戲互斥檢查
        if (supabase.table("game_ultimate_password").select("id").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").execute().data or
            supabase.table("game_rps").select("id").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").execute().data or
            supabase.table("game_undercover").select("id").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").execute().data):
            send_message(user_id, "⚠️ 已有遊戲進行中。")
            return

        if text == "終極密碼": start_ultimate_password(user_id, partner, n1, n2)
        elif text == "猜拳": start_rps(user_id, partner, n1, n2)
        elif text == "誰是臥底": start_undercover(user_id, partner, n1, n2)
        return

    # 3. 處理遊戲過程與聊天轉發
    pair = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute().data
    if pair:
        if handle_guess(user_id, text) or handle_rps_move(user_id, text) or handle_undercover_vote(user_id, text): return
        send_message(pair[0]["partner_id"], f"{pair[0]['nickname']}：{text}", tag="ACCOUNT_UPDATE")
    else:
        if text in ["開始", "0011"]: start_match(user_id)
        else: send_message(user_id, "請輸入「開始」進行配對。")

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET": return request.args.get("hub.challenge") if request.args.get("hub.verify_token") == VERIFY_TOKEN else "Error"
    for entry in request.json.get("entry", []):
        for event in entry.get("messaging", []):
            if "message" in event and "text" in event["message"]:
                handle_text(event["sender"]["id"], event["message"]["text"])
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
