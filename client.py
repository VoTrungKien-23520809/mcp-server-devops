import asyncio
import os
import sys

import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Ollama runtime configuration
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder")
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))


def ask_ai(prompt_text: str) -> str:
    """Send prompt to local Ollama and return a non-empty textual response."""
    if not prompt_text or not prompt_text.strip():
        return "Error: prompt_text must not be empty."

    url = f"{OLLAMA_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt_text,
        "stream": False,
    }

    try:
        response = requests.post(url, json=payload, timeout=AI_TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.json()
        answer = body.get("response", "").strip()
        if not answer:
            return "AI returned an empty response."
        return answer
    except requests.exceptions.RequestException as e:
        return f"AI connection error: {e}"
    except ValueError as e:
        return f"AI response parsing error: {e}"
    except Exception as e:
        return f"AI connection error: {e}"


async def main():
    print("1. Connecting to the MCP Server...")

    # Configure stdio transport to run server.py.
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"],
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                print("2. Requesting the MCP Server to access the K3s infrastructure...")
                result = await session.call_tool("get_k8s_nodes", arguments={})
                if not result.content:
                    print("No K3s data returned from MCP server.")
                    return

                raw_k8s_data = result.content[0].text
                print("\n--- [Raw K3s data retrieved] ---")
                print(raw_k8s_data)
                print("----------------------------------\n")

                print("3. Sending data to AI for analysis...\n")
                prompt = (
                    "Here are the details of the nodes in my Kubernetes cluster:\n"
                    f"{raw_k8s_data}\n\n"
                    "Please analyze and tell me how many nodes are in the system, "
                    "what types they are, and their current status in brief Vietnamese."
                )

                ai_response = ask_ai(prompt)
                print("🤖 [AI Response]:")
                print(ai_response)
    except Exception as e:
        print(f"Fatal client error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
