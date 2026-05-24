import random
from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 🎲 1. 剪刀石頭布 遊戲邏輯
# ==========================================
def start_rps(user_id, partner_id, nickname1, nickname2):
    """初始化猜拳遊戲"""
    from app import send_message
    
    # 清理舊局
    supabase.table("game_rps").delete().or_(f"user_id.eq.{user_id},user_id.eq.{partner_id}").execute()
    
    # 寫入新局
    supabase.table("game_rps").insert({
        "user_id": user_id,
        "partner_id": partner_id,
        "is_active": True
    }).execute()
    
    msg = (
        "🎲 剪刀石頭布遊戲開始囉！\n\n"
        "請在對話框直接輸入：剪刀、石頭 或 布\n"
        "⚠️ 系統會秘密攔截你的出拳，不用擔心被對方偷看喔！"
    )
    send_message(user_id, msg)
    send_message(partner_id, msg, tag="ACCOUNT_UPDATE")

def handle_rps_move(user_id, text):
    """處理玩家出拳"""
    from app import send_message
    move = text.strip()
    if move not in ["剪刀", "石頭", "布"]:
        return False
        
    # 查詢這兩個人進行中的猜拳
    game_query = supabase.table("game_rps").select("*").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").limit(1).execute()
    if not game_query.data:
        return False
        
    game = game_query.data[0]
    game_id = game["id"]
    p1 = game["user_id"]
    p2 = game["partner_id"]
    
    # 找出對方 ID
    partner_id = p2 if user_id == p1 else p1
    
    # 更新出拳狀態
    if user_id == p1:
        supabase.table("game_rps").update({"user_move": move}).eq("id", game_id).execute()
        p1_move = move
        p2_move = game["partner_move"]
    else:
        supabase.table("game_rps").update({"partner_move": move}).eq("id", game_id).execute()
        p1_move = game["user_move"]
        p2_move = move

    # 撈取暱稱
    pair_query = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
    my_name = pair_query.data[0]["nickname"] if pair_query.data else "神秘人"
    partner_name = pair_query.data[0]["partner_nickname"] if pair_query.data else "神秘人"

    # 如果有一方還沒出
    if not p1_move or not p2_move:
        send_message(user_id, f"✅ 你秘密出了【{move}】，正在等待對方出拳...")
        send_message(partner_id, f"⏳ 提示：【{my_name}】已經出拳囉！快輸入你的出拳吧！", tag="ACCOUNT_UPDATE")
        return True

    # 雙方都出拳了，結算勝負
    supabase.table("game_rps").update({"is_active": False}).eq("id", game_id).execute()
    
    # 決定誰對應誰的暱稱
    p1_name = my_name if user_id == p1 else partner_name
    p2_name = partner_name if user_id == p1 else my_name
    
    result_msg = f"💥 猜拳結果揭曉！ 💥\n\n【{p1_name}】出了：{p1_move}\n【{p2_name}】出了：{p2_move}\n\n"
    
    if p1_move == p2_move:
        result_msg += "🤝 竟然平手！太有默契了吧！"
    elif (p1_move == "石頭" and p2_move == "剪刀") or (p1_move == "剪刀" and p2_move == "布") or (p1_move == "布" and p2_move == "石頭"):
        result_msg += f"👑 恭喜【{p1_name}】贏得了這場勝利！"
    else:
        result_msg += f"👑 恭喜【{p2_name}】贏得了這場勝利！"
        
    send_message(p1, result_msg)
    send_message(p2, result_msg, tag="ACCOUNT_UPDATE")
    return True


# ==========================================
# 👑 4. 誰是臥底 遊戲邏輯
# ==========================================
# 雙人臥底經典詞庫
WORDS_POOL = [
    ("生魚片", "壽司"), ("麥當勞", "肯德基"), ("鋼筆", "鉛筆"), 
    ("珍珠奶茶", "牛肉麵"), ("口罩", "防毒面具"), ("吉他", "烏克麗麗")
]

def start_undercover(user_id, partner_id, nickname1, nickname2):
    """初始化誰是臥底遊戲"""
    from app import send_message
    
    # 清理舊局
    supabase.table("game_undercover").delete().or_(f"user_id.eq.{user_id},user_id.eq.{partner_id}").execute()
    
    # 隨機選一組詞，並隨機決定誰是臥底
    word_pair = random.choice(WORDS_POOL)
    spy_is_p1 = random.choice([True, False])
    
    if spy_is_p1:
        p1_word, p2_word = word_pair[1], word_pair[0] # p1 是臥底
        spy_id = user_id
    else:
        p1_word, p2_word = word_pair[0], word_pair[1] # p2 是臥底
        spy_id = partner_id

    # 寫入資料庫
    supabase.table("game_undercover").insert({
        "user_id": user_id,
        "partner_id": partner_id,
        "user_word": p1_word,
        "partner_word": p2_word,
        "spy_id": spy_id,
        "is_active": True
    }).execute()
    
    # 秘密發送詞彙給雙方
    msg_p1 = (
        "🕵️ 誰是臥底遊戲開始囉！\n\n"
        f"🤫 你拿到的秘密詞彙是：【 {p1_word} 】\n\n"
        "👉 玩法：請各自用「一句話」描述你的詞（不能直接打出詞彙本身），並推理誰的詞跟自己不一樣！\n"
        "當你們描述完想投票抓臥底時，請輸入，舉例：`抓臥底 你的推測對象暱稱`"
    )
    msg_p2 = msg_p1.replace(p1_word, p2_word)
    
    send_message(user_id, msg_p1)
    send_message(partner_id, msg_p2, tag="ACCOUNT_UPDATE")

def handle_undercover_vote(user_id, text):
    """處理抓臥底投票"""
    from app import send_message
    if not text.startswith("抓臥底"):
        return False
        
    # 查詢是否有正在進行的臥底局
    game_query = supabase.table("game_undercover").select("*").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").limit(1).execute()
    if not game_query.data:
        send_message(user_id, "❌ 目前沒有正在進行中的臥底遊戲喔！")
        return True
        
    game = game_query.data[0]
    game_id = game["id"]
    spy_id = game["spy_id"]
    partner_id = game["partner_id"] if game["user_id"] == user_id else game["user_id"]
    
    # 取得雙方暱稱
    pair_query = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
    my_name = pair_query.data[0]["nickname"] if pair_query.data else "神秘人"
    partner_name = pair_query.data[0]["partner_nickname"] if pair_query.data else "神秘人"
    
    target_name = text.replace("抓臥底", "").strip()
    if not target_name:
        send_message(user_id, "⚠️ 請輸入你想抓的對象暱稱，舉例：抓臥底 白凸")
        return True
        
    # 判斷投票對象
    if target_name != partner_name:
        send_message(user_id, f"⚠️ 聊天室裡找不到暱稱叫【{target_name}】的人喔！請確認拼字（對方的暱稱是：{partner_name}）。")
        return True
        
    # 結束遊戲
    supabase.table("game_undercover").update({"is_active": False}).eq("id", game_id).execute()
    
    # 結算勝負：猜對方是不是臥底
    if partner_id == spy_id:
        # 指向的對方真的是臥底 -> 投票人獲勝
        win_msg = f"🎉 抓到了！【{my_name}】指控成功！臥底真的就是【{partner_name}】！\n\n正義方詞彙：{game['user_word'] if user_id != spy_id else game['partner_word']}\n臥底方詞彙：{game['user_word'] if user_id == spy_id else game['partner_word']}\n\n恭喜【{my_name}】贏得勝利！"
    else:
        # 指向的對方是平民 -> 臥底獲勝
        win_msg = f"💥 抓錯人啦！【{my_name}】指控冤枉平民！【{partner_name}】是無辜的平民！\n\n真正的臥底其實是【{my_name}】！\n臥底成功潛伏，贏得勝利！"
        
    send_message(user_id, win_msg)
    send_message(partner_id, win_msg, tag="ACCOUNT_UPDATE")
    return True