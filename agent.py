import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_ollama import OllamaLLM

# Initialize Qwen 2.5 Coder model
Model_name = "qwen2.5:14b"
llm = OllamaLLM(model=Model_name)

async def run_agent():
    print("⏳ Initializing AI Agent and connecting to MCP Server...")
    
    # Configure MCP Server connection (main.py)
    server_params = StdioServerParameters(
        command="python",
        args=["main.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ Successfully connected to MCP Server!")
            
            # Call get_terraform_plan Tool
            print("\n🤖 Đang yêu cầu MCP Server lấy log Jenkins...")
            
            jenkins_result = await session.call_tool(
                "get_jenkins_logs", 
                arguments={"job_name": "mcp-server-pipeline", "build_number": "lastBuild"}
            )
            
            log_output = jenkins_result.content[0].text
            print("✅ Đã lấy được log Jenkins! Đang chuyển cho Qwen phân tích...\n")
            
            # Đổi Prompt để AI đóng vai chuyên gia chẩn đoán CI/CD
            prompt = f"""
            You are a DevOps and SRE expert. Please analyze the following Jenkins Build Log and provide a concise report STRICTLY IN VIETNAMESE. 
            
            Báo cáo cần có 2 phần:
            1. Nguyên nhân chính khiến Pipeline bị lỗi (hoặc thành công) là gì?
            2. Đề xuất cách sửa lỗi cụ thể (ví dụ: cần cài thêm thư viện gì, sửa lại cú pháp nào, hay kiểm tra quyền truy cập nào).
            
            JENKINS LOG OUTPUT:
            {log_output}
            """
            
            print(f"🧠 {Model_name} is analyzing (GPU is processing, please wait)...\n")
            response = llm.invoke(prompt)
            print("========================================")
            print(f"👉 AI ANALYSIS REPORT:\n{response}")
            print("========================================")

if __name__ == "__main__":
    asyncio.run(run_agent())