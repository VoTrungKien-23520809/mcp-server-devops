import asyncio
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_ollama import OllamaLLM
import requests
from dotenv import load_dotenv

load_dotenv()

# 1. Cấu hình Model 
Model_name = "qwen2.5:14b"
llm = OllamaLLM(model=Model_name)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_alert(message):
    """Hàm bắn báo cáo sang Discord qua Webhook có cơ chế chia nhỏ tin nhắn"""
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ Chưa cấu hình Discord Webhook URL!")
        return

    # Discord giới hạn 2000 ký tự. Ta cắt nhỏ tin nhắn thành các đoạn 1900 ký tự cho an toàn.
    max_length = 1900
    chunks = [message[i:i+max_length] for i in range(0, len(message), max_length)]

    for chunk in chunks:
        payload = {
            "content": chunk,
            "username": "AI SRE Agent (Qwen 14B)", 
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/4712/4712139.png" 
        }

        try:
            res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            if res.status_code == 204: 
                print("🚀 Đã bắn báo cáo sang Discord thành công!")
            else:
                print(f"⚠️ Lỗi gửi Discord ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"⚠️ Không thể kết nối tới Discord: {e}")

async def run_agent():
    print(f"⏳ Đang khởi động AI Agent ({Model_name}) và kết nối MCP Server...")

    server_params = StdioServerParameters(
        command="python",
        args=["main.py"],
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ Đã kết nối thành công tới MCP Server!")

                # BƯỚC 1: SOI SỨC KHỎE CLUSTER
                print("\n🔍 AI đang yêu cầu MCP Server quét trạng thái Cluster K3s...")
                k8s_result = await session.call_tool("get_k8s_nodes", arguments={})
                k8s_data = k8s_result.content[0].text

                # BƯỚC 2: KÍCH HOẠT JENKINS VÀ NGỒI ĐỢI
                print("🤖 AI đang ra lệnh cho Jenkins chạy bản Build mới nhất và đợi...")
                jenkins_result = await session.call_tool("trigger_jenkins_and_wait", arguments={"job_name": "weather-app-pipeline"})
                log_output = jenkins_result.content[0].text

                # BƯỚC 3: ĐO NHỊP TIM HỆ THỐNG (PROMETHEUS)
                print("📊 AI đang lấy chỉ số CPU/RAM từ Prometheus...")
                metrics_result = await session.call_tool("fetch_metrics", arguments={})
                metrics_data = metrics_result.content[0].text

                # BƯỚC 4: MÓC RUỘT POD ĐỌC LOG ỨNG DỤNG (Đã sửa sang namespace staging)
                print("📦 AI đang chui vào Pod để đọc Log ứng dụng...")
                # LƯU Ý: Nếu label app của sếp không phải 'weather-app', hãy đổi chỗ này!
                app_logs_result = await session.call_tool("get_app_logs", arguments={"namespace": "default", "label_selector": "app=meteo-hist"})
                app_logs_data = app_logs_result.content[0].text
                print("✅ Đã kéo được Log Ứng Dụng!")

                # BƯỚC 5: AI TỔNG HỢP VÀ PHÂN TÍCH
                print(f"\n🧠 {Model_name} đang phân tích toàn diện hệ thống (Vui lòng đợi GPU)...")
                
                prompt = f"""
                Bạn là một chuyên gia SRE và DevOps cấp cao. 
                ⚠️ LỆNH TỐI CAO: BẠN BẮT BUỘC PHẢI TRẢ LỜI 100% BẰNG TIẾNG VIỆT (VIETNAMESE). TUYỆT ĐỐI KHÔNG ĐƯỢC SỬ DỤNG TIẾNG TRUNG (CHINESE) HAY BẤT KỲ NGÔN NGỮ NÀO KHÁC TRONG BÁO CÁO NÀY!
                Dưới đây là dữ liệu toàn diện từ hệ thống của tôi:

                [DỮ LIỆU CLUSTER K3S]:
                {k8s_data}

                [JENKINS BUILD LOG]:
                {log_output}

                [CHỈ SỐ HIỆU NĂNG (METRICS)]:
                {metrics_data}

                [LOG ỨNG DỤNG ĐANG CHẠY (POD LOGS)]:
                {app_logs_data}

                Hãy lập một báo cáo chẩn đoán NGẮN GỌN bằng TIẾNG VIỆT theo cấu trúc:
                1. Tình trạng Hạ Tầng & CI/CD: (Đánh giá chung K3s và Jenkins)
                2. Đánh giá Hiệu năng: (CPU/RAM có đang quá tải không?)
                3. Tình trạng Ứng Dụng (QUAN TRỌNG): Phân tích Pod Logs xem app có đang chạy mượt không? Có quăng lỗi Exception, Panic, hay Error nào không? Nếu có lỗi, hãy chỉ đích danh lỗi đó là gì.
                4. Giải pháp & Lệnh thực thi: 
                   - Đưa ra giải pháp xử lý triệt để.
                   - Kèm theo câu lệnh `kubectl` hoặc lời khuyên sửa code cụ thể để người quản trị copy/paste xử lý ngay.
                """

                response = llm.invoke(prompt)
                
                print("\n" + "="*40)
                print("👉 BÁO CÁO PHÂN TÍCH HỆ THỐNG (AI SRE REPORT)")
                print("="*40)
                print(response)
                print("="*40)

                alert_msg = f"🚨 **BÁO CÁO SRE TOÀN DIỆN** 🚨\n\n{response}"
                send_discord_alert(alert_msg)

    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_agent())