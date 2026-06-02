import os
import logging
import subprocess
import re
import requests
import time
import json
from datetime import datetime
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
SSH_KNOWN_HOSTS_PATH = os.path.expanduser(os.getenv("SSH_KNOWN_HOSTS_PATH", "~/.ssh/known_hosts"))

# 4. Trái tim bất tử: Cấu hình Session với cơ chế Retry
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("http://", adapter)
session.mount("https://", adapter)

K8S_NAMESPACE_RE = re.compile(r"^[a-z0-9]([-.a-z0-9]*[a-z0-9])?$")
K8S_LABEL_SELECTOR_RE = re.compile(r"^[A-Za-z0-9_.-]+=[A-Za-z0-9_.-]+$")


def _run_ssh_kubectl(kubectl_args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    if not AZURE_IP or not SSH_KEY_PATH:
        raise ValueError("Missing AZURE_IP or SSH_KEY_PATH in environment.")

    ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={SSH_KNOWN_HOSTS_PATH}",
        "-i", SSH_KEY_PATH,
        f"azureuser@{AZURE_IP}",
        "sudo",
        f"KUBECONFIG=/etc/rancher/k3s/k3s.yaml",
        "kubectl",
    ] + kubectl_args

    return subprocess.run(
        ssh_cmd,
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )


def _find_build_by_date(job_name: str, date_str: str) -> str | None:
    """
    Tìm build number gần nhất chạy vào ngày chỉ định.
    date_str: định dạng 'DD/MM/YYYY'
    Trả về build number dạng string, hoặc None nếu không tìm thấy.
    """
    try:
        target_date = datetime.strptime(date_str, "%d/%m/%Y").date()
    except ValueError:
        logger.error(f"Định dạng ngày sai: {date_str}. Phải là DD/MM/YYYY.")
        return None

    base_url = JENKINS_URL.rstrip('/')
    # Lấy danh sách 50 build gần nhất kèm timestamp
    url = f"{base_url}/job/{job_name}/api/json?tree=builds[number,timestamp]{{0,50}}"

    try:
        res = session.get(url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
        res.raise_for_status()
        builds = res.json().get("builds", [])

        matched = []
        for build in builds:
            build_date = datetime.fromtimestamp(build["timestamp"] / 1000).date()
            if build_date == target_date:
                matched.append(build["number"])

        if not matched:
            return None

        # Trả về build number lớn nhất (mới nhất) trong ngày đó
        return str(max(matched))

    except Exception as e:
        logger.error(f"Lỗi khi tìm build theo ngày: {str(e)}")
        return None


# ==========================================
# TOOL 1: Test Server
# ==========================================
@mcp.tool()
def ping_server() -> str:
    """Check MCP Server connection status."""
    logger.info("Ping tool được gọi.")
    return "Pong! The DevOps MCP Server is fully operational and secured."


# ==========================================
# TOOL 2: Fetch Jenkins Logs (Nâng cấp - hỗ trợ lọc theo ngày)
# ==========================================
@mcp.tool()
def get_jenkins_logs(
    job_name: str,
    build_number: str = "lastBuild",
    date_filter: str = None
) -> str:
    """
    Fetch the console log of a Jenkins build for error analysis.

    Tham số:
    - job_name: tên Jenkins job
    - build_number: số build cụ thể, mặc định là 'lastBuild'
    - date_filter: lọc theo ngày, định dạng 'DD/MM/YYYY'.
                   Nếu có, sẽ tự tìm build chạy vào ngày đó,
                   bỏ qua tham số build_number.
    """
    logger.info(f"Đang kéo log Jenkins cho job: {job_name}, build: {build_number}, date_filter: {date_filter}")

    if not JENKINS_URL or not JENKINS_USER or not JENKINS_TOKEN:
        return "Error: Thiếu cấu hình Jenkins URL, User hoặc Token trong file .env."

    # Nếu có date_filter → ưu tiên tìm build theo ngày
    if date_filter:
        logger.info(f"Đang tìm build của job '{job_name}' vào ngày {date_filter}...")
        found_build = _find_build_by_date(job_name, date_filter)
        if not found_build:
            return (
                f"Không tìm thấy build nào của job '{job_name}' vào ngày {date_filter}. "
                f"Hãy thử lại với ngày khác hoặc dùng build_number cụ thể."
            )
        build_number = found_build
        logger.info(f"Tìm thấy build #{build_number} vào ngày {date_filter}.")

    base_url = JENKINS_URL.rstrip('/')
    url = f"{base_url}/job/{job_name}/{build_number}/consoleText"

    try:
        response = session.get(url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
        response.raise_for_status()

        logs = response.text
        prefix = f"[Build #{build_number}" + (f" | Ngày {date_filter}" if date_filter else "") + "]\n"

        if len(logs) > 5000:
            logger.warning("Log quá dài, đang tiến hành cắt bớt...")
            return prefix + "...[LOG TRUNCATED]...\n" + logs[-5000:]

        logger.info("✅ Kéo log Jenkins thành công!")
        return prefix + logs

    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi khi gọi API Jenkins: {str(e)}")
        return f"Error fetching logs from Jenkins: {str(e)}"


# ==========================================
# TOOL 3: Read Terraform Plan
# ==========================================
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
        return f"Terraform plan failed:\n{e.stderr}"
    except FileNotFoundError:
        return "Error: Terraform is not installed or not in PATH."
    except Exception as e:
        return f"Unexpected error: {str(e)}"


# ==========================================
# TOOL 4: Read Code Context
# ==========================================
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
        return f"Error reading file '{file_path}': {str(e)}"


# ==========================================
# TOOL 5: Soi Cluster
# ==========================================
@mcp.tool()
def get_k8s_nodes() -> str:
    """Lấy danh sách và trạng thái các Node trong K3s cluster."""
    try:
        result = _run_ssh_kubectl(["get", "nodes", "-o", "wide"], timeout=15)
        return f"Dữ liệu từ Cluster:\n{result.stdout.strip()}"
    except Exception as e:
        return f"Lỗi kết nối SSH tới Cluster: {str(e)}"


# ==========================================
# TOOL 6: Fetch Metrics từ Prometheus
# ==========================================
@mcp.tool()
def fetch_metrics() -> str:
    """Fetch real-time CPU and Memory usage from Prometheus."""
    logger.info("Đang lấy chỉ số CPU và RAM từ Prometheus...")

    prometheus_url = f"http://{AZURE_IP}:30003/api/v1/query"

    cpu_query = '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)'
    ram_query = '100 * (1 - ((avg_over_time(node_memory_MemFree_bytes[5m]) + avg_over_time(node_memory_Cached_bytes[5m]) + avg_over_time(node_memory_Buffers_bytes[5m])) / avg_over_time(node_memory_MemTotal_bytes[5m])))'

    try:
        res_cpu = requests.get(prometheus_url, params={'query': cpu_query}, timeout=10)
        cpu_data = res_cpu.json()['data']['result']
        cpu_usage = float(cpu_data[0]['value'][1]) if cpu_data else 0

        res_ram = requests.get(prometheus_url, params={'query': ram_query}, timeout=10)
        ram_data = res_ram.json()['data']['result']
        ram_usage = float(ram_data[0]['value'][1]) if ram_data else 0

        metric_report = f"🔥 Chỉ số hệ thống hiện tại:\n- CPU Usage: {cpu_usage:.2f}%\n- Memory Usage: {ram_usage:.2f}%"
        logger.info(f"✅ Lấy metrics thành công: CPU {cpu_usage:.2f}%, RAM {ram_usage:.2f}%")
        return metric_report

    except Exception as e:
        logger.error(f"Lỗi khi lấy dữ liệu Prometheus: {str(e)}")
        return f"Không thể lấy chỉ số từ Prometheus: {str(e)}"


# ==========================================
# TOOL 7: Trigger Jenkins và đợi kết quả
# ==========================================
@mcp.tool()
def trigger_jenkins_and_wait(job_name: str) -> str:
    """Kích hoạt Jenkins build, đợi chạy xong và trả về Log của bản build đó."""
    logger.info(f"🚀 AI ĐANG HÀNH ĐỘNG: Yêu cầu kích hoạt Jenkins Job: {job_name}")

    if not JENKINS_URL or not JENKINS_USER or not JENKINS_TOKEN:
        return "Error: Thiếu cấu hình Jenkins trong .env"

    base_url = JENKINS_URL.rstrip('/')
    build_url = f"{base_url}/job/{job_name}/build"

    try:
        res = session.post(build_url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
        res.raise_for_status()
        logger.info("✅ Kích hoạt Build thành công! AI đang đợi Jenkins chạy...")
        time.sleep(10)

        info_url = f"{base_url}/job/{job_name}/lastBuild/api/json"
        while True:
            info_res = session.get(info_url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
            info_data = info_res.json()
            is_building = info_data.get('building', False)
            if not is_building:
                result_status = info_data.get('result', 'UNKNOWN')
                break
            logger.info("⏳ Jenkins vẫn đang chạy... đợi thêm 10 giây...")
            time.sleep(10)

        log_content = get_jenkins_logs(job_name, "lastBuild")
        return f"Trạng thái Build: {result_status}\n\n=== LOG CHI TIẾT ===\n{log_content}"

    except Exception as e:
        return f"Lỗi không thể chạy Jenkins: {str(e)}"


# ==========================================
# TOOL 8: Đọc Log Ứng Dụng (Nâng cấp - hỗ trợ lọc theo ngày)
# ==========================================
@mcp.tool()
def get_app_logs(
    namespace: str = "default",
    label_selector: str = "app=weather-app",
    since: str = None,
    tail: int = 50
) -> str:
    """
    Fetch logs from a specific application pod in Kubernetes.

    Tham số:
    - namespace: namespace K8s, mặc định 'default'
    - label_selector: nhãn pod, định dạng 'key=value'
    - since: lọc log từ thời điểm nào, hỗ trợ:
             'DD/MM/YYYY'  → lấy log từ đầu ngày đó đến cuối ngày
             '1h', '30m'  → lấy log trong N giờ/phút gần đây
             Nếu None     → lấy {tail} dòng cuối
    - tail: số dòng log cuối cần lấy (mặc định 50), bỏ qua nếu có since
    """
    logger.info(f"🔍 Đang kéo log: {label_selector} / namespace={namespace} / since={since}")

    try:
        if not K8S_NAMESPACE_RE.fullmatch(namespace):
            return "Invalid namespace format."
        if not K8S_LABEL_SELECTOR_RE.fullmatch(label_selector):
            return "Invalid label selector format. Use key=value."

        kubectl_args = ["logs", "-l", label_selector, "-n", namespace]

        if since:
            # Trường hợp 1: lọc theo ngày cụ thể DD/MM/YYYY
            date_pattern = re.compile(r"^\d{2}/\d{2}/\d{4}$")
            if date_pattern.match(since):
                try:
                    target_date = datetime.strptime(since, "%d/%m/%Y")
                    # --since-time nhận định dạng RFC3339
                    since_time = target_date.strftime("%Y-%m-%dT00:00:00Z")
                    kubectl_args += ["--since-time", since_time]
                    logger.info(f"Lọc log từ {since_time}")
                except ValueError:
                    return f"Định dạng ngày không hợp lệ: {since}. Phải là DD/MM/YYYY."

            # Trường hợp 2: lọc theo khoảng thời gian (1h, 30m, ...)
            elif re.match(r"^\d+[hms]$", since):
                kubectl_args += ["--since", since]
                logger.info(f"Lọc log trong {since} gần đây")

            else:
                return f"Giá trị 'since' không hợp lệ: '{since}'. Dùng 'DD/MM/YYYY' hoặc '1h', '30m'."
        else:
            # Không có since → lấy N dòng cuối
            kubectl_args += [f"--tail={tail}"]

        result = _run_ssh_kubectl(kubectl_args, timeout=20)
        logs = result.stdout.strip()

        if not logs:
            if since:
                return f"Không có log nào trong khoảng thời gian '{since}' cho pod '{label_selector}'."
            return "Không có log nào hoặc không tìm thấy pod khớp với nhãn này."

        prefix = f"[Log của '{label_selector}'"
        if since:
            prefix += f" | Khoảng thời gian: {since}"
        prefix += "]\n"

        logger.info("✅ Đã lấy được log ứng dụng thành công!")
        return prefix + logs

    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi kubectl: {e.stderr}"
    except Exception as e:
        logger.error(f"❌ Lỗi khi lấy log ứng dụng: {str(e)}")
        return f"Lỗi không thể lấy log ứng dụng: {str(e)}"


# ==========================================
# TOOL 9: Liệt kê thư mục
# ==========================================
@mcp.tool()
def list_directory(directory_path: str = ".") -> str:
    """List all files and folders in a given directory within the project."""
    logger.info(f"📂 AI đang quét thư mục: {directory_path}")
    try:
        safe_path = os.path.abspath(directory_path)
        if not safe_path.startswith(os.getcwd()):
            return "❌ Lỗi bảo mật: Không được phép truy cập ngoài thư mục dự án."
        items = os.listdir(safe_path)
        return f"--- Danh sách file trong '{directory_path}' ---\n" + "\n".join(items)
    except Exception as e:
        return f"❌ Không thể đọc thư mục {directory_path}: {str(e)}"


# ==========================================
# TOOL 10: Đọc file dự án
# ==========================================
@mcp.tool()
def read_project_file(file_path: str) -> str:
    """Read the content of a file (e.g., Dockerfile, Jenkinsfile, .py) to analyze code or configuration."""
    logger.info(f"📖 AI đang đọc file: {file_path}")
    try:
        safe_path = os.path.abspath(file_path)
        if not safe_path.startswith(os.getcwd()):
            return "❌ Lỗi bảo mật: Không được phép đọc file ngoài thư mục dự án."
        with open(safe_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"--- NỘI DUNG FILE '{file_path}' ---\n{content}"
    except FileNotFoundError:
        return f"❌ Lỗi: Không tìm thấy file '{file_path}'"
    except Exception as e:
        return f"❌ Lỗi khi đọc file {file_path}: {str(e)}"


# ==========================================
# TOOL 11: Kiểm tra sức khỏe hệ thống
# ==========================================
@mcp.tool()
def check_system_health(namespace: str = "default") -> str:
    """Kiểm tra tổng quan sức khỏe của các Pods trong K3s."""
    logger.info(f"🏥 AI đang kiểm tra sức khỏe K8s (namespace: {namespace})")
    try:
        result = _run_ssh_kubectl(["get", "pods", "-n", namespace, "-o", "wide"])
        lines = result.stdout.strip().split('\n')

        if len(lines) <= 1:
            return f"⚠️ Không tìm thấy Pod nào trong '{namespace}'."

        health_report = [f"--- TÌNH TRẠNG PODS ({namespace}) ---"]
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 3:
                pod_name, ready, status = parts[0], parts[1], parts[2]
                if status not in ["Running", "Completed"]:
                    health_report.append(f"🔴 LỖI: {pod_name} | Trạng thái: {status} | Ready: {ready}")
                else:
                    health_report.append(f"🟢 TỐT: {pod_name} | Trạng thái: {status}")
        return "\n".join(health_report)
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi K8s: {e.stderr}"


# ==========================================
# TOOL 12: Restart Pod
# ==========================================
@mcp.tool()
def restart_pod(pod_name: str, namespace: str = "default") -> str:
    """
    Khởi động lại một Pod.
    CHỈ DÙNG khi Pod bị treo ngẫu nhiên.
    TUYỆT ĐỐI CẤM SỬ DỤNG nếu Pod đang ở trạng thái CrashLoopBackOff.
    """
    logger.info(f"🔄 AI đang RESTART Pod: {pod_name}")
    try:
        result = _run_ssh_kubectl(["delete", "pod", pod_name, "-n", namespace])
        return f"✅ Đã gửi lệnh xóa Pod '{pod_name}' thành công.\nLog: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi restart Pod: {e.stderr}"


# ==========================================
# TOOL 13: Scale Deployment
# ==========================================
@mcp.tool()
def scale_deployment(deployment_name: str, replicas: int, namespace: str = "default") -> str:
    """Tăng/Giảm số lượng Pods của một Deployment (Tối đa 5)."""
    logger.info(f"⚖️ AI đang SCALE Deployment: {deployment_name} -> {replicas}")
    if replicas > 5 or replicas < 1:
        return "❌ TỪ CHỐI LỆNH: Replicas phải nằm trong khoảng từ 1 đến 5."
    try:
        result = _run_ssh_kubectl(["scale", "deployment", deployment_name, f"--replicas={replicas}", "-n", namespace])
        return f"✅ Đã scale Deployment '{deployment_name}' lên {replicas} thành công.\nLog: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi scale: {e.stderr}"


# ==========================================
# TOOL 14: Rollback Deployment
# ==========================================
@mcp.tool()
def rollback(deployment_name: str, namespace: str = "default") -> str:
    """
    Khôi phục Deployment về phiên bản hoạt động trước.
    BẮT BUỘC SỬ DỤNG khi phát hiện CrashLoopBackOff hoặc lỗi nghiêm trọng.
    """
    logger.info(f"⏪ AI đang ROLLBACK Deployment: {deployment_name}")
    try:
        result = _run_ssh_kubectl(["rollout", "undo", f"deployment/{deployment_name}", "-n", namespace])
        return f"✅ Đã rollback Deployment '{deployment_name}' thành công.\nLog: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi rollback: {e.stderr}"


if __name__ == "__main__":
    mcp.run()