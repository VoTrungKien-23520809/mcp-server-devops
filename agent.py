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
            print("\n🤖 Requesting MCP Server to run Terraform Plan...")
            tf_result = await session.call_tool(
                "get_terraform_plan", 
                arguments={"tf_directory": "./terraform-jenkins"}
            )
            
            tf_output = tf_result.content[0].text
            print("✅ Terraform log retrieved! Passing to Qwen for analysis...\n")
            
            # Prompt the LLM in English for better tech context
            prompt = f"""
            You are a DevOps and SRE expert. Please analyze the following Terraform Plan output and provide a concise report STRICTLY IN VIETNAMESE. 
            
            Báo cáo cần có 2 phần:
            1. Hạ tầng sắp có những thay đổi gì?
            2. Có rủi ro bảo mật hay hành động nguy hiểm nào không (ví dụ: mở port bừa bãi, xóa tài nguyên quan trọng)?
            
            TERRAFORM OUTPUT:
            {tf_output}
            """
            
            print(f"🧠 {Model_name} is analyzing (GPU is processing, please wait)...\n")
            response = llm.invoke(prompt)
            print("========================================")
            print(f"👉 AI ANALYSIS REPORT:\n{response}")
            print("========================================")

if __name__ == "__main__":
    asyncio.run(run_agent())