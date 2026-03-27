import asyncio
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_ollama import OllamaLLM
import requests
from dotenv import load_dotenv

load_dotenv()

# 1. cấu hình Model 
Model_name = "qwen2.5:14b"
llm = OllamaLLM(model=Model_name)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_alert(message):
    """Hàm bắn báo cáo sang Discord qua Webhook"""
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ Chưa cấu hình Discord Webhook URL!")
        return

    payload = {
        "content": message,
        "username": "AI SRE Agent (Qwen 14B)", # Tên bot hiển thị
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/4712/4712139.png" 
    }

    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if res.status_code == 204: # Discord Webhook trả về 204 là thành công
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

                # --- BƯỚC 1: SOI SỨC KHỎE CLUSTER ---
                print("\n🔍 AI đang yêu cầu MCP Server quét trạng thái Cluster K3s...")
                k8s_result = await session.call_tool("get_k8s_nodes", arguments={})
                k8s_data = k8s_result.content[0].text
                print("✅ Đã lấy được dữ liệu Cluster!")

                # --- BƯỚC 2: SOI LOG JENKINS ---
                print("🤖 AI đang kéo log Jenkins mới nhất...")
                jenkins_result = await session.call_tool(
                    "get_jenkins_logs",
                    arguments={"job_name": "mcp-server-pipeline", "build_number": "lastBuild"}
                )
                log_output = jenkins_result.content[0].text
                print("✅ Đã lấy được log Jenkins!")

                # --- BƯỚC 3: ĐO NHỊP TIM HỆ THỐNG (PROMETHEUS) ---
                print("📊 AI đang lấy chỉ số CPU/RAM từ Prometheus...")
                metrics_result = await session.call_tool("fetch_metrics", arguments={})
                metrics_data = metrics_result.content[0].text
                print(f"✅ Đã lấy được Metrics: \n{metrics_data}")

                # --- BƯỚC 4: AI TỔNG HỢP VÀ PHÂN TÍCH ---
                print(f"\n🧠 {Model_name} đang phân tích toàn diện hệ thống (Vui lòng đợi GPU)...")
                
                prompt = f"""
                Bạn là một chuyên gia SRE và DevOps cấp cao. 
                Dưới đây là dữ liệu từ hệ thống của tôi:

                [DỮ LIỆU CLUSTER K3S]:
                {k8s_data}

                [JENKINS BUILD LOG]:
                {log_output}

                [CHỈ SỐ HIỆU NĂNG (METRICS)]:
                {metrics_data}

                Hãy lập một báo cáo chẩn đoán NGẮN GỌN bằng TIẾNG VIỆT theo cấu trúc:
                1. Tình trạng Cluster: (Các node có Ready không?)
                2. Tình trạng Pipeline: (Thành công hay Thất bại? Nếu lỗi thì lỗi ở Stage nào?)
                3. Đánh giá Hiệu năng: (CPU và RAM hiện tại có ở mức an toàn không? Có rủi ro gì không?)
                4. Hành động đề xuất: (Cần tối ưu gì để hệ thống chạy mượt hơn?)
                5. Giải pháp & Lệnh thực thi: 
                   - Đưa ra giải pháp xử lý (nếu có vấn đề).
                   - NẾU CPU > 60% hoặc hệ thống có dấu hiệu quá tải, BẮT BUỘC cung cấp sẵn câu lệnh `kubectl scale deployment <tên-app> -n <namespace> --replicas=3` để người quản trị copy/paste xử lý ngay. 
                   - Đặt câu lệnh trong block code bash.
                """

                response = llm.invoke(prompt)
                
                print("\n" + "="*40)
                print("👉 BÁO CÁO PHÂN TÍCH HỆ THỐNG (AI SRE REPORT)")
                print("="*40)
                print(response)
                print("="*40)

                alert_msg = f"🚨 **CẢNH BÁO TỪ AI SRE** 🚨\n\n{response}"
                send_discord_alert(alert_msg)

    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_agent())