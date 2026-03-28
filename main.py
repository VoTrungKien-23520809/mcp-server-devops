import os
import logging
import subprocess
import requests
import time
from mcp.server.fastmcp import FastMCP
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# 1. Kích hoạt Khiên bảo mật: Tải biến môi trường từ file ẩn .env
load_dotenv()

# 2. Bật Radar theo dõi
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("devops_mcp_server")

# Khởi tạo MCP Server
mcp = FastMCP("devops-mcp-server")

# 3. Lấy thông tin cấu hình từ két sắt
JENKINS_URL = os.getenv("JENKINS_URL")
JENKINS_USER = os.getenv("JENKINS_USER")
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN")

AZURE_IP = os.getenv("AZURE_IP")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH")

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

# Tool 5: Soi Cluster
@mcp.tool()
def get_k8s_nodes() -> str:
    try:
        azure_ip = AZURE_IP
        ssh_key_path = SSH_KEY_PATH
        
        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-i", ssh_key_path, f"azureuser@{azure_ip}", "export KUBECONFIG=/etc/rancher/k3s/k3s.yaml && sudo kubectl get nodes -o wide"],
            capture_output=True,
            text=True,
            check=True,
            timeout=15
        )
        return f"Dữ liệu từ Cluster:\n{result.stdout.strip()}"
    except Exception as e:
        return f"Lỗi kết nối SSH tới Cluster: {str(e)}"

# Tool 6: Công cụ lấy metrics từ Prometheus (Buff thêm sức mạnh để lấy dữ liệu chính xác và nhanh hơn)
@mcp.tool()
def fetch_metrics() -> str:
    """Fetch real-time CPU and Memory usage from Prometheus."""
    logger.info("Đang lấy chỉ số CPU và RAM từ Prometheus...")
    
    # Sử dụng IP máy ảo Azure của ông
    prometheus_url = f"http://{AZURE_IP}:30003/api/v1/query"
    
    # Câu lệnh PromQL lấy % CPU và RAM của toàn Cụm
    cpu_query = '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
    ram_query = '100 * (1 - ((avg_over_time(node_memory_MemFree_bytes[5m]) + avg_over_time(node_memory_Cached_bytes[5m]) + avg_over_time(node_memory_Buffers_bytes[5m])) / avg_over_time(node_memory_MemTotal_bytes[5m])))'

    try:
        # Lấy CPU
        res_cpu = requests.get(prometheus_url, params={'query': cpu_query}, timeout=10)
        cpu_data = res_cpu.json()['data']['result']
        cpu_usage = float(cpu_data[0]['value'][1]) if cpu_data else 0

        # Lấy RAM
        res_ram = requests.get(prometheus_url, params={'query': ram_query}, timeout=10)
        ram_data = res_ram.json()['data']['result']
        ram_usage = float(ram_data[0]['value'][1]) if ram_data else 0

        metric_report = f"🔥 Chỉ số hệ thống hiện tại:\n- CPU Usage: {cpu_usage:.2f}%\n- Memory Usage: {ram_usage:.2f}%"
        logger.info(f"✅ Lấy metrics thành công: CPU {cpu_usage:.2f}%, RAM {ram_usage:.2f}%")
        return metric_report

    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu Prometheus: {str(e)}")
        return f"Không thể lấy chỉ số từ Prometheus: {str(e)}"

# Tool 7: AI tự động kích hoạt Jenkins và đợi lấy thành quả
@mcp.tool()
def trigger_jenkins_and_wait(job_name: str) -> str:
    """Kích hoạt Jenkins build, đợi chạy xong và trả về Log của bản build ĐÓ."""
    logger.info(f"🚀 AI ĐANG HÀNH ĐỘNG: Yêu cầu kích hoạt Jenkins Job: {job_name}")
    
    if not JENKINS_URL or not JENKINS_USER or not JENKINS_TOKEN:
        return "Error: Thiếu cấu hình Jenkins trong .env"

    base_url = JENKINS_URL.rstrip('/')
    build_url = f"{base_url}/job/{job_name}/build"
    
    try:
        # 1. Bấm nút Build từ xa
        res = session.post(build_url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
        res.raise_for_status()
        logger.info("✅ Kích hoạt Build thành công! AI đang đợi Jenkins chạy...")
        
        # Đợi 10 giây để Jenkins kịp đưa Job vào queue và bắt đầu
        time.sleep(10) 
        
        # 2. Theo dõi tiến độ của bản Build mới nhất
        info_url = f"{base_url}/job/{job_name}/lastBuild/api/json"
        
        while True:
            info_res = session.get(info_url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
            info_data = info_res.json()
            is_building = info_data.get('building', False)
            
            if not is_building:
                result_status = info_data.get('result', 'UNKNOWN')
                logger.info(f"🎯 Jenkins đã chạy xong với trạng thái: {result_status}")
                break
                
            logger.info("⏳ Jenkins vẫn đang chạy... AI tiếp tục đợi thêm 10 giây...")
            time.sleep(10) # Cứ 10 giây hỏi thăm Jenkins 1 lần
            
        # 3. Chạy xong rồi, gọi lại hàm kéo log để lấy kết quả nóng hổi
        log_content = get_jenkins_logs(job_name, "lastBuild")
        return f"Trạng thái Build: {result_status}\n\n=== LOG CHI TIẾT ===\n{log_content}"
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi điều khiển Jenkins: {str(e)}")
        return f"Lỗi không thể chạy Jenkins: {str(e)}"

if __name__ == "__main__":
    mcp.run()