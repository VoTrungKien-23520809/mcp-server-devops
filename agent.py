import asyncio
import os
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_ollama import OllamaLLM

# 1. Giữ nguyên cấu hình Model của ông (Xịn nhất rồi)
Model_name = "qwen2.5:14b"
llm = OllamaLLM(model=Model_name)

async def run_agent():
    print(f"⏳ Đang khởi động AI Agent ({Model_name}) và kết nối MCP Server...")

    # Cấu hình kết nối tới file main.py
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

                # --- BƯỚC 3: AI TỔNG HỢP VÀ PHÂN TÍCH ---
                print(f"\n🧠 {Model_name} đang phân tích toàn diện hệ thống (Vui lòng đợi GPU)...")
                
                prompt = f"""
                Bạn là một chuyên gia SRE và DevOps cấp cao. 
                Dưới đây là dữ liệu từ hệ thống của tôi:

                [DỮ LIỆU CLUSTER K3S]:
                {k8s_data}

                [JENKINS BUILD LOG]:
                {log_output}

                Hãy lập một báo cáo chẩn đoán NGẮN GỌN bằng TIẾNG VIỆT theo cấu trúc:
                1. Tình trạng Cluster: (Các node có Ready không?)
                2. Tình trạng Pipeline: (Thành công hay Thất bại? Nếu lỗi thì lỗi ở Stage nào?)
                3. Hành động đề xuất: (Cần sửa gì để hệ thống hoàn hảo hơn?)
                """

                response = llm.invoke(prompt)
                
                print("\n" + "="*40)
                print("👉 BÁO CÁO PHÂN TÍCH HỆ THỐNG (AI SRE REPORT)")
                print("="*40)
                print(response)
                print("="*40)

    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_agent())