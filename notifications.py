import os
import requests
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


def send_discord_alert(message: str):
    """Gửi báo cáo sang Discord qua Webhook, tự động chia nhỏ nếu vượt giới hạn 2000 ký tự."""
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ Chưa cấu hình Discord Webhook URL!")
        return

    for chunk in [message[i:i+1900] for i in range(0, len(message), 1900)]:
        payload = {
            "content": chunk,
            "username": "AI SRE Agent (Qwen 14B)",
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/4712/4712139.png",
        }
        try:
            res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            if res.status_code == 204:
                print("🚀 Đã bắn báo cáo sang Discord thành công!")
            else:
                print(f"⚠️ Lỗi gửi Discord ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"⚠️ Không thể kết nối tới Discord: {e}")
