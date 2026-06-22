import os
import logging
import subprocess
import re
import requests
import time
import json
from mcp.server.fastmcp import FastMCP
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

# 1. Kích hoạt Khiên bảo mật: Tải biến môi trường từ file ẩn .env
load_dotenv()

# 2. Bật Radar theo dõi
import sys
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr
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

K8S_NAMESPACE_RE = re.compile(r"^[a-z0-9]([-.a-z0-9]*[a-z0-9])?$")
K8S_LABEL_SELECTOR_RE = re.compile(r"^[A-Za-z0-9_.-]+=[A-Za-z0-9_.-]+$")


def _run_ssh_kubectl(kubectl_args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    if not AZURE_IP or not SSH_KEY_PATH:
        raise ValueError("Missing AZURE_IP or SSH_KEY_PATH in environment.")

    ssh_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={SSH_KNOWN_HOSTS_PATH}",
        "-i",
        SSH_KEY_PATH,
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

# Tool 1: Test Server
@mcp.tool()
def ping_server() -> str:
    """Check MCP Server connection status."""
    logger.info("Ping tool được gọi.")
    return "Pong! The DevOps MCP Server is fully operational and secured."

# Tool 2.1: Get Build Overview
@mcp.tool()
def get_build_overview(job_name: str, build_number: str = "lastBuild") -> str:
    """Get an overview of all stages in a Jenkins build, including their status and duration."""
    logger.info(f"Đang kéo tổng quan build cho job: {job_name}, build: {build_number}")
    
    if not JENKINS_URL or not JENKINS_USER or not JENKINS_TOKEN:
        logger.error("THẤT BẠI: Thiếu biến môi trường Jenkins trong file .env")
        return "Error: Thiếu cấu hình Jenkins URL, User hoặc Token trong file .env."

    base_url = JENKINS_URL.rstrip('/')
    wfapi_url = f"{base_url}/job/{job_name}/{build_number}/wfapi/describe"
    
    try:
        response = session.get(wfapi_url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
        response.raise_for_status()
        
        stages = response.json().get("stages", [])
        if not stages:
            return "Không tìm thấy stage nào trong build này."
            
        overview = f"### Tổng quan Build: {job_name} #{build_number}\n\n"
        overview += "| Tên Stage | Trạng thái | Thời gian chạy (giây) |\n"
        overview += "|---|---|---|\n"
        
        for stage in stages:
            name = stage.get("name", "Unknown")
            status = stage.get("status", "UNKNOWN")
            duration_ms = stage.get("durationMillis", 0)
            duration_sec = duration_ms / 1000.0
            overview += f"| {name} | {status} | {duration_sec:.2f}s |\n"
            
        return overview
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi khi gọi API wfapi: {str(e)}")
        return f"Error fetching build overview: {str(e)}"

# Tool 2.2: Fetch Jenkins Logs
@mcp.tool()
def get_jenkins_logs(job_name: str, build_number: str = "lastBuild", target_stage: str = None) -> str:
    """
    Lấy log Jenkins build. Nếu target_stage được cung cấp, trả về log tập trung vào stage đó.
    Chiến lược 3 lớp:
      1. wfapi node-log API (chính xác nhất, theo từng step bên trong stage)
      2. Regex trên raw console log (dự phòng nếu wfapi không hỗ trợ)
      3. Raw log toàn bộ, CẮT TỪ ĐẦU (không cắt đuôi để tránh mất error message)
    """
    logger.info(f"Kéo log: job={job_name}, build={build_number}, stage={target_stage}")

    if not JENKINS_URL or not JENKINS_USER or not JENKINS_TOKEN:
        return "Error: Thiếu cấu hình Jenkins URL/User/Token trong .env."

    base_url = JENKINS_URL.rstrip('/')
    auth = (JENKINS_USER, JENKINS_TOKEN)
    MAX_LOG_CHARS = 4000

    # ============================================================
    # LAYER 1: Jenkins Pipeline wfapi — Lấy log chính xác theo node
    # Endpoint chính xác: GET /execution/node/{node_id}/wfapi/log
    # trả về JSON: { "nodeId": "...", "text": "...", "hasMore": bool }
    # ============================================================
    if target_stage:
        try:
            wfapi_url = f"{base_url}/job/{job_name}/{build_number}/wfapi/describe"
            stages = session.get(wfapi_url, auth=auth, timeout=10).json().get("stages", [])

            # Tìm stage: ưu tiên exact match, fallback substring (case-insensitive)
            target_lower = target_stage.strip().lower()
            matched_stage = None
            for s in stages:
                if s.get("name", "").strip().lower() == target_lower:
                    matched_stage = s
                    break
            if not matched_stage:
                for s in stages:
                    if target_lower in s.get("name", "").strip().lower():
                        matched_stage = s
                        break

            if matched_stage:
                stage_id   = matched_stage["id"]
                stage_name = matched_stage.get("name", target_stage)
                stage_status = matched_stage.get("status", "UNKNOWN")

                # Lấy danh sách các step (stageFlowNodes) bên trong stage
                node_desc_url = f"{base_url}/job/{job_name}/{build_number}/execution/node/{stage_id}/wfapi/describe"
                flow_nodes = session.get(node_desc_url, auth=auth, timeout=10).json().get("stageFlowNodes", [])

                if flow_nodes:
                    parts = [f"=== LOG STAGE: '{stage_name}' | Status: {stage_status} ==="]
                    total_chars = len(parts[0])

                    for node in flow_nodes:
                        node_id     = node.get("id")
                        node_name   = node.get("name", "Step")
                        node_status = node.get("status", "")
                        log_href    = node.get("_links", {}).get("log", {}).get("href", "")
                        if not log_href:
                            continue

                        log_url = f"{base_url}{log_href}" if log_href.startswith("/") else log_href
                        node_log_json = session.get(log_url, auth=auth, timeout=10).json()
                        node_text = node_log_json.get("text", "").strip()

                        if not node_text:
                            continue

                        # Lọc bỏ các dòng noise của Trivy (DB download, legend, separator)
                        _noise_prefixes = (
                            "Downloading", "Fetching", "Loading", "Updating",
                            "Legend:", "- K =", "- U =", "- F =", "- D =", "- L =",
                            "────", "━━━━", "════",
                        )
                        filtered_lines = [
                            ln for ln in node_text.splitlines()
                            if not any(ln.strip().startswith(p) for p in _noise_prefixes)
                        ]
                        node_text = "\n".join(filtered_lines).strip()
                        if not node_text:
                            continue

                        header = f"\n--- [{node_status}] {node_name} (node {node_id}) ---\n"
                        chunk  = header + node_text

                        # Dừng lại khi sắp tràn ngưỡng ký tự, ưu tiên giữ phần đầu (chứa lỗi)
                        if total_chars + len(chunk) > MAX_LOG_CHARS:
                            remaining = MAX_LOG_CHARS - total_chars
                            if remaining > len(header) + 100:
                                parts.append(chunk[:remaining] + "\n...[CẮT BỚT]...")
                            parts.append("\n⚠️ Log đã đạt giới hạn. Các step sau bị bỏ qua.")
                            break

                        parts.append(chunk)
                        total_chars += len(chunk)

                    result = "\n".join(parts)
                    logger.info(f"✅ Layer 1 thành công: stage='{stage_name}', {total_chars} ký tự.")
                    return result
                else:
                    logger.warning(f"Stage '{stage_name}' không có stageFlowNodes → sang Layer 2.")
            else:
                logger.warning(f"Không tìm thấy stage '{target_stage}' trong wfapi → sang Layer 2.")

        except Exception as e:
            logger.warning(f"Layer 1 thất bại ({e}) → sang Layer 2.")

    # ============================================================
    # LAYER 2: Regex cắt đoạn stage từ raw console log
    # Tìm vị trí BẮT ĐẦU của stage và lấy từ đó, KHÔNG cắt từ đuôi
    # ============================================================
    try:
        raw_url  = f"{base_url}/job/{job_name}/{build_number}/consoleText"
        raw_logs = session.get(raw_url, auth=auth, timeout=15).text

        if target_stage:
            pattern = re.compile(
                rf"\[Pipeline\] \{{ \({re.escape(target_stage)}\)(.*?)(?=\[Pipeline\] \{{ \(|\Z)",
                re.DOTALL | re.IGNORECASE
            )
            match = pattern.search(raw_logs)
            if match:
                stage_log = match.group(1).strip()
                if len(stage_log) > MAX_LOG_CHARS:
                    # Cắt từ ĐẦU, không cắt đuôi
                    stage_log = stage_log[:MAX_LOG_CHARS] + "\n...[CẮT BỚT - phần cuối stage bị lược bỏ]..."
                logger.info(f"✅ Layer 2 thành công: stage='{target_stage}' qua regex.")
                return f"--- LOG STAGE (regex): {target_stage} ---\n{stage_log}"
            else:
                logger.warning(f"Layer 2 regex không tìm thấy stage '{target_stage}' → trả về raw log.")

        # ============================================================
        # LAYER 3: Trả về raw log, luôn cắt từ ĐẦU (không cắt đuôi)
        # Lý do: error message thường xuất hiện NGAY ĐẦU stack trace,
        # cắt từ đuôi sẽ giữ lại phần cleanup/footer vô nghĩa.
        # ============================================================
        if len(raw_logs) > MAX_LOG_CHARS:
            logger.warning("Layer 3: Raw log quá dài, cắt từ đầu để bảo toàn error message.")
            return raw_logs[:MAX_LOG_CHARS] + "\n...[CẮT BỚT - phần sau bị lược bỏ để bảo toàn thông tin lỗi]..."

        logger.info("✅ Layer 3: Trả về toàn bộ raw log.")
        return raw_logs

    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi kéo log Jenkins: {e}")
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
        result = _run_ssh_kubectl(["get", "nodes", "-o", "wide"], timeout=15)
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

# Tool 8: Đọc Log Ứng Dụng 
@mcp.tool()
def get_app_logs(namespace: str = "default", label_selector: str = "app=weather-app") -> str:
    """Fetch the last 50 lines of logs from a specific application pod in Kubernetes."""
    logger.info(f"🔍 Đang kéo log của ứng dụng có nhãn {label_selector} trong namespace '{namespace}'...")
    try:
        if not K8S_NAMESPACE_RE.fullmatch(namespace):
            return "Invalid namespace format."
        if not K8S_LABEL_SELECTOR_RE.fullmatch(label_selector):
            return "Invalid label selector format. Use key=value."

        result = _run_ssh_kubectl(
            ["logs", "-l", label_selector, "-n", namespace, "--tail=50"],
            timeout=15,
        )
        logs = result.stdout.strip()
        
        if not logs:
            return "Không có log nào được sinh ra hoặc không tìm thấy pod nào khớp với nhãn này."
            
        logger.info("✅ Đã lấy được log ứng dụng thành công!")
        return logs
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi lấy log ứng dụng: {str(e)}")
        return f"Lỗi không thể lấy log ứng dụng: {str(e)}"

import os

# Tool 9: AI xem trong thư mục có những file gì (như lệnh 'ls')
@mcp.tool()
def list_directory(directory_path: str = ".") -> str:
    """List all files and folders in a given directory within the project."""
    logger.info(f"📂 AI đang quét thư mục: {directory_path}")
    try:
        safe_path = os.path.abspath(directory_path)
        # Khóa an toàn: Chỉ cho phép quét trong thư mục dự án
        if not safe_path.startswith(os.getcwd()):
            return "❌ Lỗi bảo mật: Không được phép truy cập ngoài thư mục dự án."
            
        items = os.listdir(safe_path)
        return f"--- Danh sách file trong '{directory_path}' ---\n" + "\n".join(items)
    except Exception as e:
        return f"❌ Không thể đọc thư mục {directory_path}: {str(e)}"

# Tool 10: AI dùng cái này để đọc nội dung file code/config (như lệnh 'cat -n')
@mcp.tool()
def read_project_file(file_path: str, start_line: int = 1, end_line: int = 0) -> str:
    """
    Đọc nội dung một file trong project, có đánh số dòng để AI biết chính xác vị trí cần sửa.
    - start_line: Dòng bắt đầu đọc (mặc định: 1 = đầu file).
    - end_line: Dòng kết thúc (mặc định: 0 = đọc đến cuối file).
    Ví dụ: read_project_file('weather-app/Dockerfile') hoặc read_project_file('app.py', 10, 50)
    """
    logger.info(f"📖 AI đang đọc file: {file_path} (dòng {start_line}-{end_line or 'EOF'})")
    try:
        safe_path = os.path.abspath(file_path)
        if not safe_path.startswith(os.getcwd()):
            return "❌ Lỗi bảo mật: Không được phép đọc file ngoài thư mục dự án."

        with open(safe_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        s = max(1, start_line) - 1          # convert to 0-indexed
        e = total_lines if end_line <= 0 else min(end_line, total_lines)
        selected = all_lines[s:e]

        # Đánh số dòng để AI biết chính xác dòng nào cần sửa
        numbered = "".join(f"{s + i + 1:4d} | {line}" for i, line in enumerate(selected))

        MAX_CHARS = 6000
        if len(numbered) > MAX_CHARS:
            numbered = numbered[:MAX_CHARS] + f"\n... [CẮT BỚT - file có {total_lines} dòng, hãy dùng start_line/end_line để đọc phần tiếp]"

        return (
            f"--- FILE: '{file_path}' | Tổng {total_lines} dòng | Đang xem dòng {s+1}-{s+len(selected)} ---\n"
            f"{numbered}"
        )
    except FileNotFoundError:
        return f"❌ Lỗi: Không tìm thấy file '{file_path}'"
    except Exception as e:
        return f"❌ Lỗi khi đọc file {file_path}: {str(e)}"

# Tool 10b: AI dùng tool này để tìm kiếm từ khóa trong file (như lệnh 'grep')
@mcp.tool()
def search_in_file(file_path: str, keyword: str, context_lines: int = 5) -> str:
    """
    Tìm kiếm một từ khóa/chuỗi lỗi trong một file và trả về các dòng chứa từ khóa đó
    cùng với (context_lines) dòng xung quanh để AI hiểu ngữ cảnh.
    Rất hữu ích khi biết tên hàm/class/biến lỗi từ stack trace và muốn tìm nó trong code.
    Ví dụ: search_in_file('weather-app/app.py', 'ImportError', 3)
    """
    logger.info(f"🔍 AI đang tìm '{keyword}' trong file: {file_path}")
    try:
        safe_path = os.path.abspath(file_path)
        if not safe_path.startswith(os.getcwd()):
            return "❌ Lỗi bảo mật: Không được phép đọc file ngoài thư mục dự án."

        with open(safe_path, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        keyword_lower = keyword.lower()
        results = []
        for idx, line in enumerate(all_lines):
            if keyword_lower in line.lower():
                lo = max(0, idx - context_lines)
                hi = min(len(all_lines), idx + context_lines + 1)
                block_lines = []
                for i in range(lo, hi):
                    marker = ">>" if i == idx else "  "
                    block_lines.append(f"{i+1:4d}{marker}| {all_lines[i]}".rstrip())
                results.append("\n".join(block_lines))

        if not results:
            return f"🔍 Không tìm thấy '{keyword}' trong file '{file_path}'."

        header = f"🔍 Tìm thấy {len(results)} kết quả cho '{keyword}' trong '{file_path}':\n"
        body = ("\n" + "-"*40 + "\n").join(results)
        output = header + body

        MAX_CHARS = 5000
        if len(output) > MAX_CHARS:
            output = output[:MAX_CHARS] + "\n... [CẮT BỚT - còn nhiều kết quả hơn]"
        return output

    except FileNotFoundError:
        return f"❌ Lỗi: Không tìm thấy file '{file_path}'"
    except Exception as e:
        return f"❌ Lỗi khi tìm kiếm trong file {file_path}: {str(e)}"
    
# ==========================================
# NHÓM TOOLS: MONITORING & HEALTH CHECK
# ==========================================

# Tool 11: AI dùng cái này để xem trạng thái các Pod (như lệnh 'kubectl get pods')
@mcp.tool()
def check_system_health(namespace: str = "default") -> str:
    """Kiểm tra tổng quan sức khỏe của các Pods trong K3s."""
    logger.info(f"🏥 AI đang kiểm tra sức khỏe K8s (namespace: {namespace})")
    try:
        result = _run_ssh_kubectl(["get", "pods", "-n", namespace, "-o", "wide"])
        lines = result.stdout.strip().split('\n')
        
        if len(lines) <= 1: return f"⚠️ Không tìm thấy Pod nào trong '{namespace}'."

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
# NHÓM TOOLS: AUTO-REMEDIATION (HÀNH ĐỘNG SỬA CHỮA)
# ==========================================

# Tool 12: AI dùng cái này để xóa/khởi động lại một Pod bị lỗi
@mcp.tool()
def restart_pod(pod_name: str, namespace: str = "default") -> str:
    """""
    Khởi động lại một Pod.
    CẢNH BÁO: CHỈ DÙNG khi Pod bị treo ngẫu nhiên.
    TUYỆT ĐỐI CẤM SỬ DỤNG nếu Pod đang ở trạng thái CrashLoopBackOff, Error, hoặc ErrImagePull.
    """
    logger.info(f"🔄 AI đang RESTART Pod: {pod_name}")
    try:
        result = _run_ssh_kubectl(["delete", "pod", pod_name, "-n", namespace])
        return f"✅ Đã gửi lệnh xóa Pod '{pod_name}' thành công.\nLog: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi restart Pod: {e.stderr}"

# Tool 13: AI dùng cái này để tăng giảm số lượng Pod khi quá tải
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
    
# Tool 14: AI dùng cái này để lùi phiên bản K8s nếu code mới bị lỗi
@mcp.tool()
def rollback(deployment_name: str, namespace: str = "default") -> str:
    """
    Khôi phục (Undo/Rollback) Deployment về phiên bản hoạt động trước nếu phát hiện lỗi CRASH.
    BẮT BUỘC PHẢI SỬ DỤNG ngay lập tức khi phát hiện lỗi CrashLoopBackOff hoặc cấu hình sai lan rộng khiến Pod mới không thể khởi động.
    """
    logger.info(f"⏪ AI đang ROLLBACK Deployment: {deployment_name}")
    try:
        result = _run_ssh_kubectl(["rollout", "undo", f"deployment/{deployment_name}", "-n", namespace])
        return f"✅ Đã rollback Deployment '{deployment_name}' thành công.\nLog: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi rollback: {e.stderr}"

if __name__ == "__main__":
    mcp.run()