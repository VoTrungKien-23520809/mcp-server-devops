import asyncio
import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Hàm để giao tiếp với Local AI (Ollama)
def ask_ai(prompt_text):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": "qwen2.5-coder",
        "prompt": prompt_text,
        "stream": False
    }
    try:
        response = requests.post(url, json=payload)
        return response.json().get("response", "AI không phản hồi.")
    except Exception as e:
        return f"Lỗi kết nối AI: {e}"

async def main():
    print("1. Đang kết nối với MCP Server...")
    # Cấu hình để tự động chạy file server.py
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            print("2. Đang yêu cầu MCP Server chọc vào hạ tầng K3s...")
            # Gọi tool mà chúng ta đã định nghĩa trong server.py
            result = await session.call_tool("get_k8s_nodes", arguments={})
            raw_k8s_data = result.content[0].text
            
            print("\n--- [Dữ liệu K3s thô lấy được] ---")
            print(raw_k8s_data)
            print("----------------------------------\n")
            
            print("3. Đang gửi dữ liệu cho AI phân tích...\n")
            # Tạo câu lệnh (prompt) nhờ AI đọc dữ liệu thô
            prompt = f"Dưới đây là thông tin các node trong hệ thống Kubernetes của tôi:\n{raw_k8s_data}\n\nHãy phân tích và cho tôi biết hệ thống đang có bao nhiêu node, gồm những loại nào và trạng thái hiện tại ra sao bằng tiếng Việt ngắn gọn."
            
            ai_response = ask_ai(prompt)
            print("🤖 [AI Trả lời]:")
            print(ai_response)

if __name__ == "__main__":
    asyncio.run(main())
