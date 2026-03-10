import requests
from mcp.server.fastmcp import FastMCP

# Initialize MCP Server
mcp = FastMCP("devops-mcp-server")


# JENKINS CONFIGURATION
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

import os
import subprocess

# Tool 3: Read Terraform Plan
@mcp.tool()
def get_terraform_plan(tf_directory: str) -> str:
    """
    Run 'terraform plan' in the specified directory and return the output.
    Allows AI to evaluate infrastructure changes and potential risks.
    """
    if not os.path.isdir(tf_directory):
        return f"Error: Directory '{tf_directory}' does not exist."
        
    try:
        # Chạy lệnh terraform plan và lấy kết quả text (không màu để AI dễ đọc)
        result = subprocess.run(
            ["terraform", "plan", "-no-color"],
            cwd=tf_directory,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Terraform plan failed:\n{e.stderr}"
    except FileNotFoundError:
        return "Error: Terraform is not installed or not in PATH."
    except Exception as e:
        return f"Unexpected error: {str(e)}"

# Tool 4: Read Code Context
@mcp.tool()
def read_code_context(file_path: str) -> str:
    """
    Read the content of a specific source code, script, or configuration file.
    Helps the AI understand the project context to suggest fixes.
    """
    if not os.path.isfile(file_path):
        return f"Error: File '{file_path}' does not exist."
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            # Giới hạn độ dài để không làm nghẽn context của AI (ví dụ 10,000 ký tự)
            if len(content) > 10000:
                return content[:10000] + "\n...[FILE TRUNCATED]..."
            return content
    except Exception as e:
        return f"Error reading file '{file_path}': {str(e)}"

if __name__ == "__main__":
    mcp.run()


