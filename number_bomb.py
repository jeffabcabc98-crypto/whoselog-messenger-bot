import random
from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# 💡 關鍵：千萬不要在最頂部寫 from app import send_message，這會導致開機卡死！

def start_ultimate_password(user_id, partner_id, nickname1, nickname2):
    """由主程式觸發：初始化終極密碼遊戲，並隨機決定誰先開始"""
    # 區域匯入：等到遊戲真的要執行了，才進 app 拿功能，徹底避開死結
    from app import send_message 
    
    # 1. 清理這兩個人可能殘留的舊局
    supabase.table("game_ultimate_password")\
        .delete()\
        .or_(f"user_id.eq.{user_id},user_id.eq.{partner_id}")\
        .execute()
        
    # 2. 系統隨機生成一個 1 ~ 100 的終極密碼
    secret = random.randint(1, 100)
    
    # 3. 隨機決定誰先開始 (50% 機率)
    if random.choice([True, False]):
        starter_name = nickname1
    else:
        starter_name = nickname2
    
    # 4. 將遊戲資料寫入資料庫
    supabase.table("game_ultimate_password").insert({
        "user_id": user_id,
        "partner_id": partner_id,
        "secret_number": secret,
        "min_range": 1,
        "max_range": 100,
        "is_active": True
    }).execute()
    
    # 5. 組裝通知訊息
    start_msg = (
        "🎮 終極密碼遊戲開始囉！\n"
        "目前範圍：1 ~ 100\n\n"
        "👉 系統決定由【" + starter_name + "】先開始！\n"
        "請在對話框輸入，舉例：猜 50"
    )
    
    # 6. 發送通知給雙方
    send_message(user_id, start_msg)
    send_message(partner_id, start_msg, tag="ACCOUNT_UPDATE")


def handle_guess(user_id, text):
    """處理遊戲邏輯，包含猜數字、查詢答案指令"""
    # 區域匯入：等到要猜數字了，才進 app 拿功能
    from app import send_message 
    
    # ======= 【偷看答案指令攔截】 =======
    if text in ["6688", "我想知道答案"]:
        game_query = supabase.table("game_ultimate_password")\
            .select("*")\
            .eq("is_active", True)\
            .or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}")\
            .limit(1)\
            .execute()
            
        if game_query.data:
            secret = game_query.data[0]["secret_number"]
            send_message(user_id, f"🤫 天知地知你知我知，這局的終極密碼答案是：【 {secret} 】！\n快去算計對方吧。")
        else:
            send_message(user_id, "❌ 目前沒有正在進行中的遊戲喔！")
            
        return True # 攔截成功，不轉發給對方
    # ==========================================

    # 如果使用者不是輸入「猜」開頭，直接當作一般聊天轉發
    if not text.startswith("猜"):
        return False

    # 取出後面的純數字
    number_part = text.replace("猜", "").strip()

    try:
        guess = int(number_part)
    except ValueError:
        send_message(user_id, "⚠️ 格式錯誤！想猜數字請輸入，舉例：猜 50")
        return True 

    # 查詢是否有進行中的遊戲
    game_query = supabase.table("game_ultimate_password")\
        .select("*") \
        .eq("is_active", True)\
        .or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}")\
        .limit(1)\
        .execute()
        
    if not game_query.data:
        send_message(user_id, "❌ 目前沒有正在進行的遊戲喔！輸入「終極密碼」可發起遊戲。")
        return True 

    game = game_query.data[0]
    game_id = game["id"]
    secret = game["secret_number"]
    min_r = game["min_range"]
    max_r = game["max_range"]
    partner_id_db = game["user_id"] if game["partner_id"] == user_id else game["partner_id"]

    # 撈取目前兩人的暱稱
    pair_query = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
    if pair_query.data:
        my_name = pair_query.data[0]["nickname"]
        partner_name = pair_query.data[0]["partner_nickname"]
    else:
        my_name = "神秘人"
        partner_name = "神秘人"

    # 範圍防呆
    if guess <= min_r or guess >= max_r:
        send_message(user_id, f"⚠️ 猜錯範圍囉！密碼在 {min_r} ~ {max_r} 之間，請重新輸入。")
        return True

    # 判定 1：猜中了
    if guess == secret:
        supabase.table("game_ultimate_password").update({"is_active": False}).eq("id", game_id).execute()
        
        msg_winner = f"💥 💥 💥 💥 💥\n【{my_name}】踩中炸彈！終極密碼就是：{secret}！\n遊戲結束，你輸了～"
        msg_loser = f"🎉 🎉 🎉 🎉 🎉\n【{my_name}】踩中炸彈！終極密碼就是：{secret}！\n恭喜你活下來了，遊戲結束！"
        
        send_message(user_id, msg_winner)
        send_message(partner_id_db, msg_loser, tag="ACCOUNT_UPDATE")
        return True

    # 判定 2：沒猜中，縮小範圍
    if guess < secret:
        min_r = guess
    else:
        max_r = guess

    supabase.table("game_ultimate_password").update({
        "min_range": min_r,
        "max_range": max_r
    }).eq("id", game_id).execute()

    update_msg = f"🎲 【{my_name}】猜了 {guess}\n最新範圍縮小為：\n👉 {min_r}  ~  {max_r} 👈\n\n下一位輪到【{partner_name}】囉！"
    
    send_message(user_id, update_msg)
    send_message(partner_id_db, update_msg, tag="ACCOUNT_UPDATE")
    return True
