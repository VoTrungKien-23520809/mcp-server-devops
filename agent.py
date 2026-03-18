import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_ollama import OllamaLLM

MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
TERRAFORM_DIR = os.getenv("TERRAFORM_DIR", "./terraform-jenkins")
llm = OllamaLLM(model=MODEL_NAME)

async def run_agent():
    print("⏳ Initializing AI Agent and connecting to MCP Server...")

    # Configure MCP Server connection (main.py)
    server_params = StdioServerParameters(
        command="python",
        args=["main.py"],
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ Successfully connected to MCP Server!")

                # Call get_terraform_plan tool
                print("\n🤖 Requesting MCP Server to run Terraform Plan...")
                tf_result = await session.call_tool(
                    "get_terraform_plan",
                    arguments={"tf_directory": TERRAFORM_DIR},
                )

                if not tf_result.content:
                    print("No Terraform output returned from MCP server.")
                    return

                tf_output = tf_result.content[0].text
                print("✅ Terraform log retrieved! Passing to Qwen for analysis...\n")

                prompt = f"""
                You are a DevOps and SRE expert. Please analyze the following Terraform Plan output and provide a concise report STRICTLY IN VIETNAMESE.

                Bao cao can co 2 phan:
                1. Ha tang sap co nhung thay doi gi?
                2. Co rui ro bao mat hay hanh dong nguy hiem nao khong (vi du: mo port qua rong, xoa tai nguyen quan trong)?

                TERRAFORM OUTPUT:
                {tf_output}
                """

                print(f"🧠 {MODEL_NAME} is analyzing (GPU is processing, please wait)...\n")
                response = llm.invoke(prompt)
                print("========================================")
                print(f"👉 AI ANALYSIS REPORT:\n{response}")
                print("========================================")
    except Exception as e:
        print(f"Fatal agent error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_agent())