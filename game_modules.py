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
    from app import send_message
    
    supabase.table("game_rps").delete().or_(f"user_id.eq.{user_id},user_id.eq.{partner_id}").execute()
    
    supabase.table("game_rps").insert({
        "user_id": user_id,
        "partner_id": partner_id,
        "is_active": True
    }).execute()
    
    msg = (
        "🎲 剪刀石頭布遊戲開始囉！\n\n"
        "請在對話框直接輸入：剪刀、石頭 或 布\n"
        "⚠️ 系統會秘密攔截你的出拳，不用擔心被對方偷看喔！\n\n"
        "💡 提示：若中途不想玩了，任一方輸入「取消遊玩」即可結束遊戲。"
    )
    send_message(user_id, msg)
    send_message(partner_id, msg, tag="ACCOUNT_UPDATE")

def handle_rps_move(user_id, text):
    from app import send_message
    
    # 🕵️‍♂️ 【猜拳偷看密碼】
    if text in ["6688", "６６８８"]:
        game = supabase.table("game_rps").select("*").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").limit(1).execute().data
        if game:
            g = game[0]
            send_message(user_id, f"🔍 [測試模式] 猜拳底牌：\n玩家A: {g.get('user_move', '尚未出拳')}\n玩家B: {g.get('partner_move', '尚未出拳')}")
            return True
    
    move = text.strip()
    if move not in ["剪刀", "石頭", "布"]:
        return False
        
    game_query = supabase.table("game_rps").select("*").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").limit(1).execute()
    if not game_query.data:
        return False
        
    game = game_query.data[0]
    game_id = game["id"]
    p1 = game["user_id"]
    p2 = game["partner_id"]
    partner_id = p2 if user_id == p1 else p1
    
    if user_id == p1:
        supabase.table("game_rps").update({"user_move": move}).eq("id", game_id).execute()
    else:
        supabase.table("game_rps").update({"partner_move": move}).eq("id", game_id).execute()

    check_now = supabase.table("game_rps").select("*").eq("id", game_id).limit(1).execute()
    if not check_now.data: return True
    
    p1_move = check_now.data[0]["user_move"]
    p2_move = check_now.data[0]["partner_move"]

    if not p1_move or not p2_move:
        send_message(user_id, f"✅ 你秘密出了【{move}】，正在等待對方出拳...")
        send_message(partner_id, f"⏳ 提示：對方已經出拳囉！快輸入你的出拳吧！", tag="ACCOUNT_UPDATE")
        return True

    # 雙方都出拳了，關閉遊戲
    supabase.table("game_rps").update({"is_active": False}).eq("id", game_id).execute()
    
    # 精準定義誰是我的拳、誰是物伴的拳
    my_move = p1_move if user_id == p1 else p2_move
    partner_move = p2_move if user_id == p1 else p1_move

    # ==========================================================
    # 🎯 【核心修正：拆分「你」與「對方」的客製化勝負訊息與勉勵話語】
    # ==========================================================
    
    # 狀況 A：平手
    if my_move == partner_move:
        msg_to_me = (
            f"💥 猜拳結果揭曉！ 💥\n\n"
            f"【 📢 你 】出了：{my_move}\n"
            f"【 👤 對方 】出了：{partner_move}\n\n"
            f"🤝 竟然平手！太有默契了吧！想再玩一次請重新輸入「猜拳」"
        )
        msg_to_partner = msg_to_me  # 平手時雙方視角文字剛好對稱，可直接複用

    # 狀況 B：我贏了（代表對方輸了）
    elif (my_move == "石頭" and partner_move == "剪刀") or \
         (my_move == "剪刀" and partner_move == "布") or \
         (my_move == "布" and partner_move == "石頭"):
        
        msg_to_me = (
            f"💥 猜拳結果揭曉！ 💥\n\n"
            f"【 👑 你 】出了：{my_move}\n"
            f"【 👤 對方 】出了：{partner_move}\n\n"
            f"🎉 恭喜【你】贏得了這場勝利！運氣爆棚太強啦！"
        )
        msg_to_partner = (
            f"💥 猜拳結果揭曉！ 💥\n\n"
            f"【 📢 你 】出了：{partner_move}\n"
            f"【 👑 對方 】出了：{my_move}\n\n"
            f"🥲 哎呀不小心輸掉了... 沒關係，勝敗乃兵家常事，再開一局贏回來！"
        )

    # 狀況 C：我輸了（代表對方贏了）
    else:
        msg_to_me = (
            f"💥 猜拳結果揭曉！ 💥\n\n"
            f"【 📢 你 】出了：{my_move}\n"
            f"【 👑 對方 】出了：{partner_move}\n\n"
            f"🥲 哎呀不小心輸掉了... 沒關係，勝敗乃兵家常事，再開一局贏回來！"
        )
        msg_to_partner = (
            f"💥 猜拳結果揭曉！ 💥\n\n"
            f"【 👑 你 】出了：partner_move\n"
            f"【 👤 對方 】出了：{my_move}\n\n"
            f"🎉 恭喜【你】贏得了這場勝利！運氣爆棚太強啦！"
        )
        # 修正 partner 視角的變數對齊
        msg_to_partner = (
            f"💥 猜拳結果揭曉！ 💥\n\n"
            f"【 👑 你 】出了：{partner_move}\n"
            f"【 👤 對方 】出了：{my_move}\n\n"
            f"🎉 恭喜【你】贏得了這場勝利！運氣爆棚太強啦！"
        )

    # 分別發送給當前猜拳玩家與夥伴
    send_message(user_id, msg_to_me)
    send_message(partner_id, msg_to_partner, tag="ACCOUNT_UPDATE")
    return True

# ==========================================
# 👑 4. 誰是臥底 遊戲邏輯
# ==========================================
WORDS_POOL = [("生魚片", "壽司"), ("麥當勞", "肯德基"), ("珍珠奶茶", "牛肉麵"), ("可口可樂", "百事可樂"), ("火鍋", "麻辣燙"), ("滷肉飯", "雞肉飯"), ("漢堡", "三明治"), ("咖啡", "茶"), ("巧克力", "糖果"), ("泡麵", "乾拌麵"), ("鋼筆", "鉛筆"), ("口罩", "防毒面具"), ("吉他", "烏克麗麗"), ("鏡子", "玻璃"), ("雨傘", "雨衣"), ("牙刷", "電動牙刷"), ("手機", "平板電腦"), ("耳機", "音響"), ("手錶", "鬧鐘"), ("錢包", "信用卡"), ("航海王", "火影忍者"), ("鋼鐵人", "蝙蝠俠"), ("哆啦A夢", "抱抱熊"), ("名偵探柯南", "金田一"), ("蜘蛛人", "蟻人"), ("皮卡丘", "伊布"), ("眉毛", "睫毛"), ("班導師", "教官"), ("男朋友", "前男友"), ("班長", "副班長"), ("腳踏車", "摩托車"), ("捷運", "火車"), ("飛機", "直升機"), ("結婚", "訂婚"), ("初戀", "單戀"), ("情敵", "暗戀"), ("臉書", "Instagram"), ("LINE", "微信"), ("YouTube", "Netflix"), ("網紅", "明星"), ("電腦遊戲", "手機遊戲"), ("ChatGPT", "Siri"), ("獅子", "老虎"), ("貓咪", "狗狗"), ("海豚", "鯨魚"), ("玫瑰花", "向日葵"), ("香蕉", "芭樂"), ("蘋果", "水梨"), ("加班", "熬夜"), ("薪水", "年終獎金"), ("放假", "請假"), ("開會", "報告"), ("夜市", "老街"), ("悠遊卡", "一卡通"), ("蝦皮", "淘寶"), ("鹹酥雞", "雞排"), ("珍奶", "黑糖鮮奶"), ("棒球", "壘球"), ("唱歌", "去夜店"), ("看電影", "追劇"), ("泡溫泉", "三溫暖"), ("腳底按摩", "全身Spa"), ("護手霜", "乳液"), ("護唇膏", "口紅"), ("隱形眼鏡", "放大片"), ("香水", "體香噴霧"), ("吸管", "環保吸管"), ("拖鞋", "涼鞋"), ("西裝", "襯衫"), ("雨鞋", "布鞋"), ("牙線", "牙籤"), ("指甲剪", "銼刀"), ("期末考", "畢業展"), ("寫論文", "做報告"), ("交女朋友", "脫單"), ("教授", "指導教授"), ("退學", "休學"), ("遲到", "請假"), ("創業", "擺攤"), ("中發票", "中樂透"), ("提辭職", "被開除"), ("領紅包", "發紅包"), ("芒果", "木瓜"), ("西瓜", "哈密瓜"), ("草莓", "櫻桃"), ("鳳梨酥", "蛋黃酥"), ("甜甜圈", "雞蛋糕"), ("雞排", "豬排"), ("火龍果", "奇異果"), ("地瓜", "馬鈴薯"), ("起司", "奶油"), ("冰淇淋", "霜淇淋"), ("鬼滅之刃", "咒術迴戰"), ("進擊的巨人", "東京喰種"), ("火影忍者", "死神"), ("漫威", "DC"), ("演唱會", "音樂祭"), ("Cosplay", "萬聖節變裝"), ("YouTuber", "實況主"), ("周杰倫", "蔡依林"), ("九妹", "館長"), ("五月天", "告五人")]

def start_undercover(user_id, partner_id, nickname1, nickname2):
    from app import send_message
    supabase.table("game_undercover").delete().or_(f"user_id.eq.{user_id},user_id.eq.{partner_id}").execute()
    word_pair = random.choice(WORDS_POOL)
    spy_is_p1 = random.choice([True, False])
    if spy_is_p1: p1_word, p2_word, spy_id = word_pair[1], word_pair[0], user_id
    else: p1_word, p2_word, spy_id = word_pair[0], word_pair[1], partner_id
    supabase.table("game_undercover").insert({"user_id": user_id, "partner_id": partner_id, "user_word": p1_word, "partner_word": p2_word, "spy_id": spy_id, "is_active": True}).execute()
    send_message(user_id, f"🕵️ 誰是臥底開始！\n🤫 詞彙：【 {p1_word} 】\n👉 描述你的詞，想抓臥底輸入：抓臥底 {nickname2}")
    send_message(partner_id, f"🕵️ 誰是臥底開始！\n🤫 詞彙：【 {p2_word} 】\n👉 描述你的詞，想抓臥底輸入：抓臥底 {nickname1}", tag="ACCOUNT_UPDATE")

def handle_undercover_vote(user_id, text):
    from app import send_message
    
    # 🕵️‍♂️ 【臥底偷看密碼】
    if text in ["6688", "６６８８"]: 
        game = supabase.table("game_undercover").select("*").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").limit(1).execute().data
        if game:
            g = game[0]
            send_message(user_id, f"🔍 [測試模式] 臥底底牌：\n玩家A詞: {g.get('user_word')}\n玩家B詞: {g.get('partner_word')}\n臥底ID: {g.get('spy_id')[-6:]}")
            return True

    if not text.startswith("抓臥底"): return False
    game_query = supabase.table("game_undercover").select("*").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").limit(1).execute()
    if not game_query.data: return False
    game = game_query.data[0]
    spy_id = game["spy_id"]
    p1 = game["user_id"]
    partner_id = game["partner_id"] if p1 == user_id else p1
    pair_query = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
    my_name = pair_query.data[0]["nickname"] if pair_query.data else "神秘人"
    partner_name = pair_query.data[0]["partner_nickname"] if pair_query.data else "神秘人"
    target_name = text.replace("抓臥底", "").strip()
    if not target_name:
        send_message(user_id, f"⚠️ 請輸入你想抓的對象暱稱"); return True
    if target_name == my_name:
        send_message(user_id, f"⚠️ 不能抓自己啦！"); return True
    if target_name != partner_name:
        send_message(user_id, f"⚠️ 找不到【{target_name}】的人喔！"); return True
    supabase.table("game_undercover").update({"is_active": False}).eq("id", game["id"]).execute()
    spy_word = game["user_word"] if spy_id == p1 else game["partner_word"]
    civilian_word = game["partner_word"] if spy_id == p1 else game["user_word"]
    if partner_id == spy_id:
        win_msg = f"🎉 抓到了！【{my_name}】指控成功！臥底是【{partner_name}】！\n正義方詞彙：{civilian_word}\n臥底方詞彙：{spy_word}"
    else:
        win_msg = f"💥 抓錯人啦！【{partner_name}】是無辜的平民！真正的臥底是【{my_name}】！\n正義方詞彙：{civilian_word}\n臥底方詞彙：{spy_word}"
    send_message(user_id, win_msg)
    send_message(partner_id, win_msg, tag="ACCOUNT_UPDATE")
    return True

def cancel_game(user_id):
    from app import send_message
    pair_query = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
    if not pair_query.data: return False
    my_name, partner_id = pair_query.data[0]["nickname"], pair_query.data[0]["partner_id"]
    game_was_canceled = False
    for table in ["game_ultimate_password", "game_rps", "game_undercover"]:
        if supabase.table(table).select("id").eq("is_active", True).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").execute().data:
            supabase.table(table).update({"is_active": False}).or_(f"user_id.eq.{user_id},partner_id.eq.{user_id}").execute()
            game_was_canceled = True
    if game_was_canceled:
        msg = f"❌ 玩家【{my_name}】使用了【取消遊玩】指令，目前的互動小遊戲已強制結束！"
        send_message(user_id, msg)
        send_message(partner_id, msg, tag="ACCOUNT_UPDATE")
        return True
    return False
