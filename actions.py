from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def handle_pending_actions(user_id, text, action, pending_data):
    """處理所有需要二次確認的Pending指令 (離開/封鎖/下一位/檢舉)"""
    from app import send_message, clear_chat_pair, add_risk_score, start_match
    
    # =========================
    # 1. 確認離開聊天室
    # =========================
    if action == "confirm_leave":
        if text in ["是", "1"]:
            result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            if not result.data:
                send_message(user_id, "開目前沒有聊天對象")
                return True
                
            partner = result.data[0]["partner_id"]
            clear_chat_pair(user_id)
            try:
                send_message(partner, "⚠️ 對方已離開聊天室", tag="ACCOUNT_UPDATE")
            except:
                pass
            send_message(user_id, "✅ 你已離開聊天")
            return True

        if text in ["否", "2"]:
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            send_message(user_id, "✅ 已取消離開聊天室")
            return True
            
        send_message(user_id, "請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否")
        return True

    # =========================
    # 2. 確認封鎖
    # =========================
    if action == "confirm_block":
        if text in ["是", "1"]:
            result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            if not result.data:
                send_message(user_id, "開目前沒有聊天對象")
                return True

            partner = result.data[0]["partner_id"]
            check = supabase.table("blacklist").select("*").eq("user_id", user_id).eq("blocked_user_id", partner).execute()
            if check.data:
                send_message(user_id, "⚠️ 你已經封鎖過此人")
                return True

            supabase.table("blacklist").insert({"user_id": user_id, "blocked_user_id": partner}).execute()
            
            pair_data = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
            reporter_name = "未知使用者"
            reported_name = "未知使用者"
            if pair_data.data:
                reporter_name = pair_data.data[0].get("fb_name", "未知使用者")
                reported_name = pair_data.data[0].get("partner_fb_name", "未知使用者")

            supabase.table("reports").insert({
                "reporter_id": user_id,
                "reporter_name": reporter_name,
                "reported_user_id": partner,
                "reported_name": reported_name,
                "reason": "使用者封鎖"
            }).execute()

            add_risk_score(partner, block_add=1, report_add=1, risk_add=4)
            clear_chat_pair(user_id)
            send_message(user_id, "🚫 已成功將對方封鎖")
            try:
                send_message(partner, "🥲 對方似乎不喜歡你，已離開聊天室", tag="ACCOUNT_UPDATE")
            except:
                pass
            return True

        if text in ["否", "2"]:
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            send_message(user_id, "✅ 已取消封鎖")
            return True

        send_message(user_id, "請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否")
        return True

    # =========================
    # 3. 確認下一位
    # =========================
    if action == "confirm_next":
        if text in ["是", "1"]:
            result = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            if result.data:
                partner = result.data[0]["partner_id"]
                supabase.table("recent_pairs").insert({"user1": user_id, "user2": partner}).execute()
                clear_chat_pair(user_id)

            try:
                send_message(partner, "🥲 對方似乎不喜歡你，已離開聊天室", tag="ACCOUNT_UPDATE")
            except:
                pass
            send_message(user_id, "🔄 正在幫你尋找下一位...")
            start_match(user_id)
            return True

        if text in ["否", "2"]:
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            send_message(user_id, "✅ 已取消尋找下一位")
            return True

        send_message(user_id, "請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否")
        return True

    # =========================
    # 4. 填寫檢舉原因
    # =========================
    if action == "report_reason":
        target_user = pending_data["target_user_id"]
        if text == "返回":
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            send_message(user_id, "✅ 已取消檢舉")
            return True

        reason = text.strip()
        if not reason:
            send_message(user_id, "⚠️ 請輸入檢舉原因")
            return True

        pair_data = supabase.table("chat_pairs").select("*").eq("user_id", user_id).limit(1).execute()
        reporter_name = "未知使用者"
        reported_name = "未知使用者"
        if pair_data.data:
            reporter_name = pair_data.data[0].get("fb_name", "未知使用者")
            reported_name = pair_data.data[0].get("partner_fb_name", "未知使用者")

        supabase.table("reports").insert({
            "reporter_id": user_id,
            "reporter_name": reporter_name,
            "reported_user_id": target_user,
            "reported_name": reported_name,
            "reason": reason
        }).execute()

        add_risk_score(target_user, report_add=1, risk_add=3)
        supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
        supabase.table("pending_actions").insert({"user_id": user_id, "action": "report_confirm", "target_user_id": target_user}).execute()
        send_message(user_id, "✅ 已送出檢舉\n\n是否要封鎖並離開聊天室？\n\n請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否")
        return True

    # =========================
    # 5. 檢舉後的封鎖確認
    # =========================
    if action == "report_confirm":
        target_user = pending_data["target_user_id"]
        check = supabase.table("blacklist").select("*").eq("user_id", user_id).eq("blocked_user_id", target_user).execute()
        if check.data:
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            clear_chat_pair(user_id)
            send_message(user_id, "⚠️ 你已經封鎖過此人")
            return True

        if text in ["是", "1"]:
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            supabase.table("blacklist").insert({"user_id": user_id, "blocked_user_id": target_user}).execute()
            clear_chat_pair(user_id)
            send_message(user_id, "🚫 已封鎖對方並離開聊天室")
            try:
                send_message(target_user, "🥲 對方似乎不喜歡你，已離開聊天室", tag="ACCOUNT_UPDATE")
            except:
                pass
            return True

        if text in ["否", "2"]:
            supabase.table("pending_actions").delete().eq("user_id", user_id).execute()
            send_message(user_id, "✅ 已完成檢舉")
            return True

        send_message(user_id, "請回覆：\n\n1️⃣ 或 是\n2️⃣ 或 否")
        return True

    return False