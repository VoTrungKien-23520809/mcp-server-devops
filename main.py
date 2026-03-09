import requests
from mcp.server.fastmcp import FastMCP

# Initialize MCP Server
mcp = FastMCP("devops-mcp-server")

# ==========================================
# JENKINS CONFIGURATION
# ==========================================
JENKINS_URL = "http://20.89.52.40:8080"
JENKINS_USER = "kienvo" # Ensure this matches your login username
JENKINS_TOKEN = "11dafa493f1dac3240587c90ed7e6333a4" 

# Tool 1: Test Server
@mcp.tool()
def ping_server() -> str:
    """Check MCP Server connection status."""
    return "Pong! The DevOps MCP Server is fully operational."

# Tool 2: Fetch Jenkins Logs
@mcp.tool()
def get_jenkins_logs(job_name: str, build_number: str) -> str:
    """
    Fetch the console log of a Jenkins build for error analysis.
    """
    # Nếu người dùng để trống build_number thì tự gán bằng lastBuild
    if not build_number:
        build_number = "lastBuild"
        
    try:
        url = f"{JENKINS_URL}/job/{job_name}/{build_number}/consoleText"
        response = requests.get(url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
        response.raise_for_status()
        
        logs = response.text
        if len(logs) > 5000:
            return "...[LOG TRUNCATED]...\n" + logs[-5000:]
        return logs
        
    except requests.exceptions.RequestException as e:
        return f"Error fetching logs from Jenkins: {str(e)}"

if __name__ == "__main__":
    mcp.run()


