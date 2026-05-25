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
    
    # 隨機決定誰先開始（True 代表 user_id 先，False 代表 partner_id 先）
    is_user_starter = random.choice([True, False])
    starter_id = user_id if is_user_starter else partner_id
    
    supabase.table("game_ultimate_password").insert({
        "user_id": user_id,
        "partner_id": partner_id,
        "secret_number": secret,
        "min_range": 1,
        "max_range": 100,
        "is_active": True,
        "current_turn_user_id": starter_id  # 👈 鎖定第一回合
    }).execute()
    
    # ==========================================================
    # 🎯 【客製化第一回合提示：區分「你」與「對方」】
    # ==========================================================
    if is_user_starter:
        # 如果是 user_id 先開局
        msg_for_user = f"👉 系統決定由【 📢 你 】先開始！"
        msg_for_partner = f"👉 系統決定由【 👤 對方（{nickname1}） 】先開始！"
    else:
        # 如果是 partner_id 先開局
        msg_for_user = f"👉 系統決定由【 👤 對方（{nickname2}） 】先開始！"
        msg_for_partner = f"👉 系統決定由【 📢 你 】先開始！"

    # 組裝發給 user_id 的完整訊息
    start_msg_user = (
        f"🎮 終極密碼遊戲開始！範圍 1 ~ 100\n\n"
        f"{msg_for_user}\n"
        f"請在對話框直接輸入：猜 數字 (例如：猜 50)\n\n"
        f"⚠️ 提示：若中途不想玩了，任一方輸入「取消遊玩」即可結束遊戲。"
    )

    # 組裝發給 partner_id 的完整訊息
    start_msg_partner = (
        f"🎮 終極密碼遊戲開始！範圍 1 ~ 100\n\n"
        f"{msg_for_partner}\n"
        f"請在對話框直接輸入：猜+空格+數字 (例如：猜 50)\n\n"
        f"⚠️ 提示：若中途不想玩了，任一方輸入「取消遊玩」即可結束遊戲。"
    )
    
    # 分別發送客製化後的訊息
    send_message(user_id, start_msg_user)
    send_message(partner_id, start_msg_partner, tag="ACCOUNT_UPDATE")

def handle_guess(user_id, text):
    from app import send_message, supabase
    
    # 🕵️‍♂️ 【安全攔截：如果對方已經離開，自動清理殘留遊戲】
    if text == "取消遊玩":
        return False 

    if not text.startswith("猜"): return False

    game_query = supabase.table("game_ultimate_password").select("*").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").limit(1).execute()
    if not game_query.data: return True

    game = game_query.data[0]
    
    # 🚨【核心修正】：強制檢查回合鎖定
    if game["current_turn_user_id"] != user_id:
        send_message(user_id, "⚠️ 還沒輪到你喔！請等待對方先猜。")
        return True 

    # 取出後面的純數字
    try:
        guess = int(text.replace("猜", "").strip())
    except:
        send_message(user_id, "⚠️ 格式錯誤！請輸入：猜 50")
        return True 

    # 執行猜數字邏輯...
    secret = game["secret_number"]
    min_r, max_r = game["min_range"], game["max_range"]
    partner_id_db = game["user_id"] if game["partner_id"] == user_id else game["partner_id"]

    # ==========================================================
    # 🚨 【超範圍防呆防護網】
    # ==========================================================
    if guess <= min_r or guess >= max_r:
        send_message(user_id, f"⚠️ 超出當前有效範圍！目前範圍是 【{min_r} ~ {max_r}】，請重新輸入在這個範圍內的數字。")
        return True

    # 判定 1：直接猜中！遊戲結束
    if guess == secret:
        # 關閉遊戲
        supabase.table("game_ultimate_password").update({"is_active": False}).eq("id", game["id"]).execute()
        
        # 傳送客製化的獲勝/爆炸通知
        send_message(user_id, f"💥 爆炸了！【 🔴 你 】猜中了密碼 【{secret}】！遊戲結束 💀")
        send_message(partner_id_db, f"💥 爆炸了！【 🟢 對方 】猜中了密碼 【{secret}】！恭喜你活下來了 🎉", tag="ACCOUNT_UPDATE")
        return True

    # 判定 2：沒猜中，更新最新範圍並切換回合
    if guess < secret:
        new_min = guess
        new_max = max_r
    else:
        new_min = min_r
        new_max = guess

    # 更新資料庫中的範圍，並將回合擁有者移交給對方
    supabase.table("game_ultimate_password").update({
        "min_range": new_min,
        "max_range": new_max,
        "current_turn_user_id": partner_id_db  # 👈 切換回合給對方
    }).eq("id", game["id"]).execute()

    # ==========================================================
    # 🎯 【核心修正：拆分「你」與「對方」的戰況廣播訊息】
    # ==========================================================
    
    # 1. 給剛猜完的人（也就是目前的 user_id）看到的訊息
    msg_for_me = (
        f"【 📢 你 】猜了 {guess}！沒中！\n"
        f"📉 範圍縮小為：【 {new_min} ~ {new_max} 】\n\n"
        f"⏳ 下一回合輪到 👉【 👤 對方 】填寫"
    )
    
    # 2. 給正在等待的人（也就是對方的 partner_id_db）看到的訊息
    msg_for_partner = (
        f"【 👤 對方 】猜了 {guess}！沒中！\n"
        f"📉 範圍縮小為：【 {new_min} ~ {new_max} 】\n\n"
        f"⚔️ 這回合輪到 👉【 📢 你 】出題囉！請輸入:猜+數字"
    )
    
    # 分別投遞客製化訊息
    send_message(user_id, msg_for_me)
    send_message(partner_id_db, msg_for_partner, tag="ACCOUNT_UPDATE")
    
    return True
