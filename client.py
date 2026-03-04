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
        return response.json().get("response", "AI is not responding.")
    except Exception as e:
        return f"AI connection error: {e}"

async def main():
    print("1. Connecting to the MCP Server...")
    # Cấu hình để tự động chạy file server.py
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"]
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            print("2. Requesting the MCP Server to access the K3s infrastructure...")
            # Gọi tool mà chúng ta đã định nghĩa trong server.py
            result = await session.call_tool("get_k8s_nodes", arguments={})
            raw_k8s_data = result.content[0].text
            
            print("\n--- [Raw K3s data retrieved] ---")
            print(raw_k8s_data)
            print("----------------------------------\n")
            
            print("3. Sending data to AI for analysis...\n")
            # Tạo câu lệnh (prompt) nhờ AI đọc dữ liệu thô
            prompt = f"Here are the details of the nodes in my Kubernetes cluster:\n{raw_k8s_data}\n\nPlease analyze and tell me how many nodes are in the system, what types they are, and their current status in brief Vietnamese."
            
            ai_response = ask_ai(prompt)
            print("🤖 [AI Response]:")
            print(ai_response)

if __name__ == "__main__":
    asyncio.run(main())
