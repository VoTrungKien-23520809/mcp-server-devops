import os
import logging
import subprocess
import requests
from mcp.server.fastmcp import FastMCP
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# 1. Kích hoạt Khiên bảo mật: Tải biến môi trường từ file ẩn .env
load_dotenv()

# 2. Bật Radar theo dõi: Cấu hình hệ thống Logging chuẩn như Codex
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("devops_mcp_server")

# Khởi tạo MCP Server
mcp = FastMCP("devops-mcp-server")

# 3. Lấy thông tin cấu hình từ két sắt (Không còn Hardcode lộ liễu)
JENKINS_URL = os.getenv("JENKINS_URL")
JENKINS_USER = os.getenv("JENKINS_USER")
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN")

# 4. Trái tim bất tử: Cấu hình Session với cơ chế Retry (Chống sập mạng)
session = requests.Session()
retry_strategy = Retry(
    total=3,  # Nếu rớt mạng, thử lại tối đa 3 lần
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504], # Các mã lỗi server sẽ kích hoạt retry
    allowed_methods=["HEAD", "GET", "OPTIONS"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

# Tool 1: Test Server
@mcp.tool()
def ping_server() -> str:
    """Check MCP Server connection status."""
    logger.info("Ping tool được gọi.")
    return "Pong! The DevOps MCP Server is fully operational and secured."

# Tool 2: Fetch Jenkins Logs (Đã được buff sức mạnh)
@mcp.tool()
def get_jenkins_logs(job_name: str, build_number: str = "lastBuild") -> str:
    """Fetch the console log of a Jenkins build for error analysis."""
    logger.info(f"Đang kéo log Jenkins cho job: {job_name}, build: {build_number}")
    
    if not JENKINS_URL or not JENKINS_USER or not JENKINS_TOKEN:
        logger.error("THẤT BẠI: Thiếu biến môi trường Jenkins trong file .env")
        return "Error: Thiếu cấu hình Jenkins URL, User hoặc Token trong file .env."

    base_url = JENKINS_URL.rstrip('/')
    url = f"{base_url}/job/{job_name}/{build_number}/consoleText"

    try:
        # Dùng session có retry thay vì requests.get thông thường
        response = session.get(url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
        response.raise_for_status()
        
        logs = response.text
        if len(logs) > 5000:
            logger.warning("Log quá dài, đang tiến hành cắt bớt để bảo vệ não AI...")
            return "...[LOG TRUNCATED]...\n" + logs[-5000:]
        
        logger.info("✅ Kéo log Jenkins thành công!")
        return logs
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi khi gọi API Jenkins: {str(e)}")
        return f"Error fetching logs from Jenkins: {str(e)}"

# Tool 3: Read Terraform Plan
@mcp.tool()
def get_terraform_plan(tf_directory: str) -> str:
    """Run 'terraform plan' in the specified directory and return the output."""
    logger.info(f"Đang chạy terraform plan tại thư mục {tf_directory}")
    if not os.path.isdir(tf_directory):
        return f"Error: Directory '{tf_directory}' does not exist."
        
    try:
        result = subprocess.run(
            ["terraform", "plan", "-no-color"],
            cwd=tf_directory,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error("Terraform plan thất bại.")
        return f"Terraform plan failed:\n{e.stderr}"
    except FileNotFoundError:
        return "Error: Terraform is not installed or not in PATH."
    except Exception as e:
        logger.error(f"Lỗi không xác định: {str(e)}")
        return f"Unexpected error: {str(e)}"

# Tool 4: Read Code Context
@mcp.tool()
def read_code_context(file_path: str) -> str:
    """Read the content of a specific source code file."""
    logger.info(f"Đang đọc nội dung file: {file_path}")
    if not os.path.isfile(file_path):
        return f"Error: File '{file_path}' does not exist."
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if len(content) > 10000:
                return content[:10000] + "\n...[FILE TRUNCATED]..."
            return content
    except Exception as e:
        logger.error(f"Lỗi khi đọc file {file_path}: {str(e)}")
        return f"Error reading file '{file_path}': {str(e)}"

if __name__ == "__main__":
    mcp.run()