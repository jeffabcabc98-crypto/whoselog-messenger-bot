import random
from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def start_ultimate_password(user_id, partner_id, nickname1, nickname2):
    from app import send_message 
    
    supabase.table("game_ultimate_password").delete().or_(f"user_id.eq.{user_id},user_id.eq.{partner_id}").execute()
    
    secret = random.randint(1, 100)
    
    # 隨機決定誰先開始，並存入資料庫
    if random.choice([True, False]):
        starter_id = user_id
        starter_name = nickname1
    else:
        starter_id = partner_id
        starter_name = nickname2
    
    supabase.table("game_ultimate_password").insert({
        "user_id": user_id,
        "partner_id": partner_id,
        "secret_number": secret,
        "min_range": 1,
        "max_range": 100,
        "is_active": True,
        "current_turn_user_id": starter_id  # 👈 鎖定第一回合
    }).execute()
    
    start_msg = (
        f"🎮 終極密碼遊戲開始！範圍 1 ~ 100\n\n"
        f"👉 系統決定由【{starter_name}】先開始！\n"
        "請輸入，如果要猜50的話要照格式，舉例:猜 50(一定要輸入:猜+空格+猜的數字)不能單一數字"
    )
    send_message(user_id, start_msg)
    send_message(partner_id, start_msg, tag="ACCOUNT_UPDATE")

def handle_guess(user_id, text):
    from app import send_message 
    
    # ⚙️ 修正：把全形的 ６６８８ 也加進來，防範手機輸入法鬼打牆
    if text in ["6688", "６６８８", "我想知道答案"]:
        game_query = supabase.table("game_ultimate_password").select("*").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").limit(1).execute()
        if game_query.data:
            secret = game_query.data[0]["secret_number"]
            send_message(user_id, f"🔍 [測試模式] 目前的終極密碼答案是：【 {secret} 】")
            return True # ✅ 只有真的有終極密碼遊戲在進行，才攔截！
        
        return False # ✅ 如果現在沒在玩終極密碼，放行（Return False）讓 app.py 繼續往下查猜拳跟臥底！

    if not text.startswith("猜"): return False

    game_query = supabase.table("game_ultimate_password").select("*").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").limit(1).execute()
    if not game_query.data: return True

    game = game_query.data[0]
    
    # 🚨【核心修正】：強制檢查回合鎖定
    if game["current_turn_user_id"] != user_id:
        send_message(user_id, "⚠️ 還沒輪到你喔！請等待對方先猜。如果要猜50的話要照格式，舉例:猜 50(一定要輸入:猜+空格+猜的數字)不能單一數字")
        return True 

    try:
            guess = int(text.replace("猜", "").strip())
        except:
            send_message(user_id, "⚠️ 格式錯誤！請輸入：猜 50")
            return True 
    
        # 撈出當前的密碼與最新上下限範圍
        secret = game["secret_number"]
        min_r, max_r = game["min_range"], game["max_range"]
    
        # 🚨【新增：超範圍防呆防護網】
        # 既然範圍是 min_r ~ max_r，猜的值就必須在這個開區間內（不能小於等於下限，不能大於等於上限）
        if guess <= min_r or guess >= max_r:
            send_message(user_id, f"⚠️ 超出當前有效範圍！目前範圍是 【{min_r} ~ {max_r}】，請重新輸入在這個範圍內的數字。")
            return True
    partner_id_db = game["user_id"] if game["partner_id"] == user_id else game["partner_id"]

    # 範圍檢查與判定邏輯 (同前)
    # ... (省略中間判定邏輯) ...

    # 判定 2：沒猜中，切換回合
    if guess != secret:
        # 更新範圍
        if guess < secret: min_r = guess
        else: max_r = guess
        
        # 🚨【核心修正】：切換 current_turn_user_id 給對方
        supabase.table("game_ultimate_password").update({
            "min_range": min_r, "max_range": max_r, "current_turn_user_id": partner_id_db
        }).eq("id", game["id"]).execute()

        update_msg = f"🎲 猜了 {guess}，範圍：{min_r} ~ {max_r}\n輪到對方猜了，如果要猜50的話要照格式，舉例:猜 50(一定要輸入:猜+空格+猜的數字)不能單一數字！"
        send_message(user_id, update_msg)
        send_message(partner_id_db, update_msg, tag="ACCOUNT_UPDATE")
        return True
