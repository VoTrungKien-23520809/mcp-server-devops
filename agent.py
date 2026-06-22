import asyncio
import os
import sys
import json
import re
import requests
import signal
import threading
import uvicorn
import subprocess
from pyngrok import ngrok, conf
from fastapi import FastAPI, BackgroundTasks, Request
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import asynccontextmanager
from langchain_ollama import OllamaLLM
from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.key_binding import KeyBindings

import psutil

@asynccontextmanager
async def intercepted_stdio_client(server_params):
    r, w = os.pipe()
    wf = os.fdopen(w, "w")
    
    async def read_pipe():
        f = os.fdopen(r, "r")
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, f.readline)
                if not line:
                    break
                if line.strip():
                    print(f"⚙️ [MCP] {line.strip()}")
            except:
                break
                
    reader_task = asyncio.create_task(read_pipe())
    
    try:
        async with stdio_client(server_params, errlog=wf) as (read, write):
            yield (read, write)
    finally:
        try:
            wf.close()
        except:
            pass
        await asyncio.sleep(0.1)
        reader_task.cancel()

load_dotenv()

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
def analyze_system_hardware():
    ram_gb = psutil.virtual_memory().total / (1024**3)
    vram_gb = 0
    gpu_name = "N/A"
    try:
        nvidia_smi = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], 
            text=True
        )
        if nvidia_smi.strip():
            parts = nvidia_smi.strip().split(',')
            gpu_name = parts[0].strip()
            vram_gb = float(parts[1].strip()) / 1024
    except Exception:
        pass
    
    print(f"💻 Thông số phần cứng: RAM {ram_gb:.1f}GB | VRAM {vram_gb:.1f}GB ({gpu_name})")
    
    if ram_gb > 31 or vram_gb >= 16:
        ctx = 16384
        history_chars = 60000
        print("🚀 Kích hoạt cấu hình: MAX SETTINGS (Context: 16k tokens)")
    elif ram_gb > 15 or vram_gb >= 8:
        ctx = 8192
        history_chars = 30000
        print("⚖️ Kích hoạt cấu hình: TIÊU CHUẨN (Context: 8k tokens)")
    else:
        ctx = 4096
        history_chars = 15000
        print("🛡️ Kích hoạt cấu hình: AN TOÀN (Context: 4k tokens)")
        
    return ctx, history_chars

OPT_CTX, MAX_HISTORY_CHARS = analyze_system_hardware()
Model_name = "qwen2.5:14b"
llm = OllamaLLM(model=Model_name, num_ctx=OPT_CTX)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

app = FastAPI()

def setup_self_register_webhook():
    print("🌐 Đang khởi động hệ thống Tự động đăng ký Webhook (K3s Mode)...")
    
    auth_token = os.getenv("NGROK_AUTH_TOKEN")
    if not auth_token:
        print("⚠️ LỖI: Thiếu NGROK_AUTH_TOKEN trong .env")
        return None

    try:
        #Cấu hình và khởi động Ngrok tunnel tại cổng 5000
        conf.get_default().auth_token = auth_token
        public_url = ngrok.connect(5000).public_url
        webhook_url = f"{public_url}/prometheus-webhook"
        print(f"🚀 Ngrok Tunnel đã mở: {public_url}")
        print(f"🔗 Link Webhook mục tiêu: {webhook_url}")

        azure_ip = os.getenv("AZURE_IP")
        ssh_key = os.getenv("SSH_KEY_PATH")
        
        #Chuỗi lệnh Bash tự động lấy Secret, sửa URL và apply lại vào K3s
        bash_script = f"""
        export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
        
        kubectl get secret alertmanager-prom-stack-kube-prometheus-alertmanager -n monitoring -o jsonpath='{{.data.alertmanager\\.yaml}}' | base64 --decode > /tmp/am.yaml
        
        sed -i "s|url:.*|url: '{webhook_url}'|g" /tmp/am.yaml
        
        kubectl create secret generic alertmanager-prom-stack-kube-prometheus-alertmanager -n monitoring --from-file=alertmanager.yaml=/tmp/am.yaml --dry-run=client -o yaml | kubectl apply -f -
        
        rm /tmp/am.yaml
        """

        full_ssh_cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no", "-i", ssh_key,
            f"azureuser@{azure_ip}",
            "bash", "-c", bash_script
        ]

        print(f"📡 Đang kết nối tới Azure ({azure_ip}) để cập nhật Secret Alertmanager...")
        result = subprocess.run(full_ssh_cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            print("✅ Alertmanager (K3s) đã được cập nhật link Webhook mới tự động!")
            return webhook_url
        else:
            print(f"❌ Lỗi khi cập nhật cấu hình K3s: {result.stderr}")
            return None

    except Exception as e:
        print(f"❌ Lỗi trong quá trình tự đăng ký: {str(e)}")
        return None

def send_discord_alert(message):
    """Hàm bắn báo cáo sang Discord qua Webhook có cơ chế chia nhỏ tin nhắn"""
    if not DISCORD_WEBHOOK_URL:
        print("⚠️ Chưa cấu hình Discord Webhook URL!")
        return

    # Discord giới hạn 2000 ký tự. Cắt nhỏ tin nhắn thành các đoạn 1900 ký tự.
    max_length = 1900
    chunks = [message[i:i+max_length] for i in range(0, len(message), max_length)]

    for chunk in chunks:
        payload = {
            "content": chunk,
            "username": "AI SRE Agent (Qwen 14B)", 
            "avatar_url": "https://cdn-icons-png.flaticon.com/512/4712/4712139.png" 
        }
        try:
            res = requests.post(DISCORD_WEBHOOK_URL, json=payload)
            if res.status_code == 204: 
                print("🚀 Đã bắn báo cáo sang Discord thành công!")
            else:
                print(f"⚠️ Lỗi gửi Discord ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"⚠️ Không thể kết nối tới Discord: {e}")


# ==========================================
# 1. BỘ NÃO ĐIỀU TRA CI/CD (JENKINS)
# ==========================================
async def run_investigation(job_name: str):
    print(f"\n🕵️ AI THÁM TỬ ĐÃ THỨC DẬY! Bắt đầu điều tra sự cố cho Job: {job_name}")

    server_params = StdioServerParameters(command="python", args=["main.py"])

    try:
        async with intercepted_stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ Đã kết nối thành công tới MCP Server (CI/CD Mode)!")

                SYSTEM_PROMPT = """Bạn là một Kỹ sư SRE + Developer cấp cao, có khả năng đọc log và phân tích mã nguồn.
QUY TẮC ĐIỀU TRA (REACT LOOP):
1. THOUGHT: Suy nghĩ phải NGẮN GỌN (tối đa 4 câu). Phân tích logic vấn đề.
2. ACTION: Bạn CHỈ ĐƯỢC GỌI 1 TOOL DUY NHẤT trong mỗi vòng lặp. Phải đợi có kết quả rồi mới gọi tool tiếp theo.

Danh sách Tools:
- get_build_overview: {"job_name": "tên-job"}
- get_jenkins_logs: {"job_name": "tên-job", "target_stage": "Tên Stage (Tùy chọn)"}
- list_directory: {"directory_path": "đường-dẫn"}
- read_project_file: {"file_path": "đường-dẫn-file", "start_line": số-dòng-bắt-đầu (tùy chọn), "end_line": số-dòng-kết-thúc (tùy chọn)}
- search_in_file: {"file_path": "đường-dẫn-file", "keyword": "từ-khóa-lỗi", "context_lines": 5}
- get_app_logs: {"namespace": "tên-namespace", "label_selector": "app=tên-app"}
- get_k8s_nodes: {}
- fetch_metrics: {}
- check_system_health: {"namespace": "tên-namespace"}
- rollback: {"deployment_name": "tên-deployment", "namespace": "tên-namespace"}
- restart_pod: {"pod_name": "tên-pod", "namespace": "tên-namespace"}

BẠN CHỈ ĐƯỢC PHẢN HỒI THEO 1 TRONG 2 ĐỊNH DẠNG SAU:

ĐỊNH DẠNG 1 (Khi cần gọi Tool):
Thought: [Suy nghĩ ngắn gọn]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (CHỈ GỌI KHI ĐÃ ĐỌC XONG FILE CODE VÀ XÁC ĐỊNH ĐƯỢC DÒNG LỖI):
Thought: Tôi đã tìm ra nguyên nhân và đọc xong code cần sửa. Sẵn sàng báo cáo.
Final Answer:
[BẠN BẮT BUỘC PHẢI VIẾT BÁO CÁO SRE TOÀN DIỆN BẰNG TIẾNG VIỆT, SỐNG ĐỘNG, DÙNG MARKDOWN CHUYÊN NGHIỆP:]
#### 1. Tóm tắt sự cố:
- Stage nào bị lỗi, mã lỗi gì, thông báo lỗi gốc là gì (trích dẫn nguyên văn từ log).
#### 2. Phân tích nguyên nhân gốc rễ (Root Cause):
- Lỗi xuất phát từ file nào, dòng nào, hàm nào (dựa vào kết quả read_project_file hoặc search_in_file).
#### 3. Giải pháp sửa lỗi (Cụ thể 100%):
- Phải cung cấp đoạn code sửa lỗi cụ thể trong khối markdown ```language, chỉ rõ dòng số cần sửa, giải thích lý do thay đổi.
#### 4. Tình trạng ứng dụng / Hạ tầng:
- (Nếu Deploy lỗi: nêu hành động rollback/restart. Nếu Build lỗi: ghi 'Chưa deploy, không cần kiểm tra K8s').
"""

                USER_TASK = f"""
Nhiệm vụ điều tra:

[GIAI ĐOẠN 1 - XÁC ĐỊNH LỖI]
1. Gọi `get_build_overview` (job_name: '{job_name}') ĐẦU TIÊN để xác định Stage nào bị FAILED.
2. Gọi `get_jenkins_logs` với `target_stage` = tên Stage bị lỗi để lấy thông tin lỗi chi tiết.
   - Đọc kỹ log: tìm EXCEPTION TYPE, ERROR MESSAGE, FILE/MODULE lỗi (e.g. 'ModuleNotFoundError: No module named X', 'SyntaxError at line Y', 'COPY failed: file not found').

[GIAI ĐOẠN 2 - ĐỐI CHIẾU VỚI CODE (BẮT BUỘC)]
3. Dựa vào thông tin từ log, xác định file nào trong repo có khả năng gây ra lỗi. Sử dụng:
   - `search_in_file` để tìm từ khóa lỗi / tên hàm / tên module trong file liên quan.
   - `read_project_file` để đọc toàn bộ file và hiểu context (có thể dùng start_line/end_line để chỉ đọc khu vực xung quanh dòng lỗi).
   - Nếu không biết file ở đâu: gọi `list_directory` trước để khám phá cấu trúc thư mục.

[RẼ NHÁNH ĐIỀU TRA]
- Lỗi ở Build / Unit Test / Security Scan: Nguyên nhân là mã nguồn hoặc config. Cần đọc code để gợi ý sửa. KHÔNG cần kiểm tra K8s.
- Lỗi ở Deploy: Cần gọi `check_system_health` và `get_app_logs`. Nếu Pod bị CrashLoop/ImagePull → BẮT BUỘC gọi `rollback`.

⚠️ QUY TẮC ĐƯỜNG DẪN QUAN TRỌNG:
- Khi dùng tool đọc file: Bạn đang đứng ở thư mục gốc của Repo. Dùng đường dẫn tương đối (VD: 'weather-app/Dockerfile', 'main.py').
- TUYỆT ĐỐI KHÔNG gọi Final Answer khi chưa thực hiện ĐỐI CHIẾU VỚI CODE (Giai đoạn 2).
"""

                history = ""
                max_steps = 10 
                
                for step in range(max_steps):
                    print(f"\n--- [Vòng lặp CI/CD thứ {step + 1}/{max_steps}] ---")
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử điều tra:\n{history}\n\nNhiệm vụ của bạn: {USER_TASK}\n\nBước tiếp theo của bạn là gì?"
                    response = llm.invoke(prompt)
                    print(f"🤖 AI Suy nghĩ & Quyết định:\n{response}\n")
                    
                    if "Final Answer:" in response:
                        final_report = response.split("Final Answer:")[1].strip()
                        print("\n" + "="*40 + "\n👉 BÁO CÁO PHÂN TÍCH HỆ THỐNG (AI SRE REPORT)\n" + "="*40)
                        print(final_report)
                        print("="*40)
                        alert_msg = f"🚨 **BÁO CÁO JENKINS TỪ AI SRE** 🚨\n\n{final_report}"
                        send_discord_alert(alert_msg)
                        break
                        
                    action_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response)
                    input_match = re.search(r"Action Input:\s*(\{.*?\})", response, re.DOTALL)
                    
                    if action_match and input_match:
                        tool_name = action_match.group(1).strip()
                        raw_json = re.sub(r'```json\s*|```', '', input_match.group(1).strip())
                        
                        try:
                            tool_args = json.loads(raw_json)
                            print(f"🛠️ MCP Server đang thực thi Tool: [{tool_name}] với tham số {tool_args}")
                            tool_result = await session.call_tool(tool_name, arguments=tool_args)
                            observation = tool_result.content[0].text
                            
                            if len(observation) > 6000:
                                observation = observation[:6000] + "\n...[ĐÃ CẮT BỚT VÌ LOG QUÁ DÀI]..."
                                
                            print(f"✅ Đã có bằng chứng! (Observation: {len(observation)} ký tự). Trả về cho AI phân tích...")
                            history += f"\nThought: {response}\nObservation: {observation}\n"
                        except json.JSONDecodeError:
                            print("⚠️ AI xuất sai định dạng JSON! Bắt nó thử lại...")
                            history += f"\nThought: {response}\nObservation: LỖI: Action Input không phải JSON hợp lệ.\n"
                        except Exception as e:
                            print(f"⚠️ Lỗi máy chủ khi gọi Tool {tool_name}: {e}")
                            history += f"\nThought: {response}\nObservation: LỖI KHI GỌI TOOL: {str(e)}.\n"
                    else:
                        print("⚠️ AI đang 'ngáo', không tuân thủ định dạng. Ép nó trả lời lại...")
                        history += f"\nThought: {response}\nObservation: LỖI: Bạn BẮT BUỘC phải dùng từ khóa 'Action:' và 'Action Input:' hoặc 'Final Answer:'.\n"
                    
                    if len(history) > MAX_HISTORY_CHARS:
                        history = "...\n" + history[-MAX_HISTORY_CHARS:]

    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng: {e}")


# ==========================================
# 2. BỘ NÃO ĐIỀU TRA HẠ TẦNG (PROMETHEUS ALERTS)
# ==========================================
async def run_metrics_investigation(alert_name: str, alert_desc: str):
    print(f"\n🚨 AI THÁM TỬ ĐÃ THỨC DẬY! Điều tra cảnh báo hạ tầng: {alert_name}")

    server_params = StdioServerParameters(command="python", args=["main.py"])

    try:
        async with intercepted_stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ Đã kết nối thành công tới MCP Server (Infra Mode)!")

                SYSTEM_PROMPT = """Bạn là một Kỹ sư SRE cấp cao. 
QUY TẮC ĐIỀU TRA (REACT LOOP):
1. THOUGHT: Suy nghĩ NGẮN GỌN (tối đa 4 câu).
2. ACTION: CHỈ ĐƯỢC GỌI 1 TOOL DUY NHẤT trong mỗi vòng lặp.

Danh sách Tools: 
- get_app_logs: {"namespace": "tên-namespace", "label_selector": "app=tên-app"}
- get_k8s_nodes: {}
- fetch_metrics: {}
- list_directory: {"directory_path": "đường-dẫn"}
- read_project_file: {"file_path": "đường-dẫn-file"}
- check_system_health: {"namespace": "tên-namespace"}
- restart_pod: {"pod_name": "tên-pod", "namespace": "tên-namespace"}
- scale_deployment: {"deployment_name": "tên-deployment", "replicas": số-lượng, "namespace": "tên-namespace"}
- rollback: {"deployment_name": "tên-deployment", "namespace": "tên-namespace"}
(TUYỆT ĐỐI KHÔNG dùng tool get_jenkins_logs vì đây là lỗi hạ tầng, không phải lỗi build).

ĐỊNH DẠNG 1 (Khi cần gọi Tool):
Thought: [Suy nghĩ ngắn gọn]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (CHỈ GỌI KHI ĐÃ CÓ ĐỦ BẰNG CHỨNG VÀ ĐÃ THỰC THI XONG HÀNH ĐỘNG SỬA CHỮA):
Final Answer:
#### 1. Nguyên nhân cảnh báo: (Phân tích lý do gây ra Alert).
#### 2. Tình trạng thực tế: (Trích xuất data từ fetch_metrics, get_k8s_nodes và check_system_health).
#### 3. Phân tích Ứng dụng: (Có pod nào đang spam log hoặc ngốn tài nguyên không?).
#### 4. Hành động Tự động đã thực hiện (Auto-remediation): (BẮT BUỘC NÊU RÕ bạn đã dùng lệnh scale, restart hay rollback nào, số lượng bao nhiêu, và kết quả log trả về ra sao).

QUY TẮC XỬ LÝ SỰ CỐ NGHIÊM NGẶT (MUST FOLLOW):
1. ĐỊNH TUYẾN DEADLOCK: Nếu Alert Name là "AppDeadlock" hoặc nội dung chứa từ "Deadlock":
   - BỎ QUA bước kiểm tra log ứng dụng (get_app_logs).
   - BẮT BUỘC gọi công cụ `restart_pod` ngay lập tức để giải phóng bộ nhớ. Không được phép dùng `rollback`.
2. ĐỊNH TUYẾN CRASHLOOP: Nếu Pod ở trạng thái 'CrashLoopBackOff', 'Error', hoặc 'ImagePullBackOff':
   - TUYỆT ĐỐI KHÔNG dùng `restart_pod`.
   - BẮT BUỘC gọi công cụ `rollback` để quay về revision an toàn.
3. NGHIÊM CẤM suy diễn nguyên nhân từ các cảnh báo log cũ (như 'client.caching') nếu trạng thái Pod vẫn đang Running.
"""

                USER_TASK = f"""
Cảnh báo từ Prometheus: '{alert_name}'
Mô tả chi tiết: '{alert_desc}'

Nhiệm vụ của bạn:
1. Đọc kỹ mô tả cảnh báo để tự suy luận tên Ứng dụng, Deployment và Namespace đang gặp sự cố.
(💡 MẸO SRE QUAN TRỌNG: Trong hệ thống này, tên Deployment thường là tên ứng dụng cộng thêm hậu tố '-deployment'. Ví dụ: ứng dụng 'meteo-hist' thì deployment là 'meteo-hist-deployment').
2. Gọi `fetch_metrics` hoặc `check_system_health` để thu thập dữ liệu tải thực tế và trạng thái Pod.
3. Gọi `get_app_logs` (namespace: 'default', label_selector: 'app=meteo-hist') để xem ứng dụng có sinh log bất thường gây nghẽn tài nguyên không.
4. Hành động khắc phục (BẮT BUỘC):
- Dựa vào tính chất của lỗi, hãy tự quyết định gọi `scale_deployment` (để tăng Pod nếu quá tải), HOẶC `restart_pod` (nếu Pod treo), HOẶC `rollback` (nếu lỗi nghiêm trọng).
⚠️ QUY TẮC THÉP: Bạn PHẢI thực hiện việc gọi Tool hành động bằng ĐỊNH DẠNG 1 trước. Chỉ khi Tool trả về kết quả thành công thì mới được phép chuyển sang ĐỊNH DẠNG 2 (Final Answer) để kết thúc.
TUYỆT ĐỐI KHÔNG ĐƯỢC nhét lệnh Action vào bên trong khối Final Answer!
5. Dựa trên dữ liệu và hành động ĐÃ THỰC HIỆN XONG, đưa ra Final Answer báo cáo.
"""

                history = ""
                max_steps = 10 
                
                for step in range(max_steps):
                    print(f"\n--- [Vòng lặp Hạ Tầng thứ {step + 1}/{max_steps}] ---")
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử:\n{history}\n\nNhiệm vụ: {USER_TASK}\n\nBước tiếp theo là gì?"
                    response = llm.invoke(prompt)
                    print(f"🤖 AI Suy nghĩ:\n{response}\n")
                    
                    if "Final Answer:" in response:
                        final_report = response.split("Final Answer:")[1].strip()
                        alert_msg = f"🔥 **BÁO ĐỘNG K3S TỪ AI SRE** 🔥\n\n{final_report}"
                        send_discord_alert(alert_msg)
                        break
                        
                    action_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response)
                    input_match = re.search(r"Action Input:\s*(\{.*?\})", response, re.DOTALL)
                    
                    if action_match and input_match:
                        tool_name = action_match.group(1).strip()
                        raw_json = re.sub(r'```json\s*|```', '', input_match.group(1).strip())
                        try:
                            tool_args = json.loads(raw_json)
                            tool_result = await session.call_tool(tool_name, arguments=tool_args)
                            observation = tool_result.content[0].text
                            if len(observation) > 4000: observation = observation[:4000] + "\n...[CẮT BỚT]..."
                            history += f"\nThought: {response}\nObservation: {observation}\n"
                        except Exception as e:
                            history += f"\nObservation: LỖI KHI GỌI TOOL: {str(e)}.\n"
                    else:
                        history += "\nObservation: Sai định dạng ReAct. Vui lòng thử lại.\n"
                        
                    if len(history) > MAX_HISTORY_CHARS:
                        history = "...\n" + history[-MAX_HISTORY_CHARS:]

    except Exception as e:
        print(f"❌ Lỗi: {e}")

# ==========================================
# 3. BỘ NÃO BÁO CÁO SAU DEPLOY (SUCCESS)
# ==========================================
async def run_success_report(job_name: str):
    print(f"\n✅ AI ĐÃ THỨC DẬY! Tổng hợp báo cáo sức khỏe hệ thống sau khi Deploy: {job_name}")

    server_params = StdioServerParameters(command="python", args=["main.py"])

    try:
        async with intercepted_stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ Đã kết nối thành công tới MCP Server (Report Mode)!")

                SYSTEM_PROMPT = """Bạn là một Kỹ sư SRE cấp cao. 
QUY TẮC LÀM VIỆC (REACT LOOP):
1. THOUGHT: Suy nghĩ phải NGẮN GỌN (tối đa 4 câu).
2. ACTION: CHỈ ĐƯỢC GỌI 1 TOOL DUY NHẤT trong mỗi vòng lặp.

Danh sách Tools:
- fetch_metrics: {}
- check_system_health: {"namespace": "tên-namespace"}

ĐỊNH DẠNG 1 (Khi cần gọi Tool):
Thought: [Suy nghĩ bước tiếp theo]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (CHỈ GỌI KHI ĐÃ LẤY ĐỦ DỮ LIỆU TỪ PROMETHEUS VÀ K8S):
Final Answer:
[BẠN BẮT BUỘC PHẢI VIẾT BÁO CÁO BẰNG TIẾNG VIỆT, SỬ DỤNG MARKDOWN CHUYÊN NGHIỆP VỚI CẤU TRÚC SAU:]
#### 1. Trạng thái CI/CD:
- (Xác nhận bản build đã deploy thành công).
#### 2. Tình trạng Kubernetes:
- (Liệt kê số lượng Pod đang chạy, namespace, có Pod nào bị lỗi không dựa vào tool check_system_health).
#### 3. Hiệu năng Hệ thống (Prometheus):
- (Ghi rõ % CPU và RAM hiện tại).
#### 4. Đánh giá chung:
- (Đưa ra kết luận hệ thống có an toàn để nhận traffic không).
"""

                USER_TASK = f"""
Nhiệm vụ của bạn: Job Jenkins '{job_name}' VỪA DEPLOY THÀNH CÔNG.
1. Gọi `check_system_health` (namespace: 'default') để kiểm tra xem các Pod mới đã khởi động thành công (Running) chưa.
2. Gọi `fetch_metrics` để lấy chỉ số CPU và RAM hiện tại xem có bị quá tải không.
3. Tổng hợp dữ liệu và xuất Final Answer để báo cáo.
"""

                history = ""
                max_steps = 5 
                
                for step in range(max_steps):
                    print(f"\n--- [Vòng lặp Báo Cáo thứ {step + 1}/{max_steps}] ---")
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử:\n{history}\n\nNhiệm vụ: {USER_TASK}\n\nBước tiếp theo là gì?"
                    response = await llm.ainvoke(prompt)
                    print(f"🤖 AI Suy nghĩ:\n{response}\n")
                    
                    if "Final Answer:" in response:
                        final_report = response.split("Final Answer:")[1].strip()
                        alert_msg = f"🎉 **BÁO CÁO DEPLOY THÀNH CÔNG** 🎉\n\n{final_report}"
                        send_discord_alert(alert_msg)
                        break
                        
                    action_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response)
                    input_match = re.search(r"Action Input:\s*(\{.*?\})", response, re.DOTALL)
                    
                    if action_match and input_match:
                        tool_name = action_match.group(1).strip()
                        raw_json = re.sub(r'```json\s*|```', '', input_match.group(1).strip())
                        try:
                            tool_args = json.loads(raw_json)
                            tool_result = await session.call_tool(tool_name, arguments=tool_args)
                            history += f"\nThought: {response}\nObservation: {tool_result.content[0].text}\n"
                        except Exception as e:
                            history += f"\nObservation: LỖI KHI GỌI TOOL: {str(e)}.\n"
                    else:
                        history += "\nObservation: Sai định dạng ReAct. Vui lòng thử lại.\n"
                        
                    if len(history) > MAX_HISTORY_CHARS:
                        history = "...\n" + history[-MAX_HISTORY_CHARS:]

    except Exception as e:
        import traceback
        print(f"❌ Lỗi: {e}")
        traceback.print_exc()      


# ==========================================
# 4. BỘ NÃO SMART CD (TÍCH HỢP VÀO TIẾN TRÌNH CI/CD)
# ==========================================
async def run_smart_cd_approval(k8s_dir: str = "weather-app/k8s"):
    print(f"\n🛑 [SMART CD] AI ĐANG THẨM ĐỊNH RỦI RO TRIỂN KHAI CHO THƯ MỤC: {k8s_dir}")
    server_params = StdioServerParameters(command="python", args=["main.py"])

    try:
        async with intercepted_stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                SYSTEM_PROMPT = """Bạn là một Kỹ sư SecOps/Gatekeeper cấp cao.
Nhiệm vụ của bạn là quyết định xem có cho phép đưa bản cập nhật ứng dụng (Kubernetes Deployment) lên môi trường Production hay không.

QUY TẮC ĐIỀU TRA:
1. THOUGHT: Suy nghĩ NGẮN GỌN (tối đa 4 câu).
2. ACTION: CHỈ GỌI 1 TOOL DUY NHẤT trong mỗi vòng lặp.

Danh sách Tools:
- read_project_file: {"file_path": "đường-dẫn"}
- fetch_metrics: {}
- check_system_health: {"namespace": "default"}

ĐỊNH DẠNG 1 (GỌI TOOL):câu
Thought: [Suy nghĩ]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (QUYẾT ĐỊNH PHÊ DUYỆT):
Final Answer:
#### QUYẾT ĐỊNH: [CHỈ GHI '🟢 APPROVE' HOẶC '🔴 REJECT']
#### 1. Đánh giá rủi ro cấu hình K8s: (Phân tích file deployment.yaml. Có dùng image: latest không? Số lượng replicas có hợp lý không? Có giới hạn tài nguyên resources limit không?)
#### 2. Sức chịu tải K8s: (CPU/RAM hiện tại có an toàn để deploy không?)
#### 3. Lý do: (Giải thích ngắn gọn quyết định của bạn)
"""
                USER_TASK = f"""
Hãy thẩm định rủi ro trước khi deploy:
1. Gọi `fetch_metrics` và `check_system_health` để xem hệ thống có đang quá tải/lỗi không.
2. Gọi `read_project_file` với tham số là '{k8s_dir}/deployment.yaml' để đọc cấu hình bản cập nhật sắp được đưa lên.
3. Đưa ra Quyết định APPROVE (Cho phép) hoặc REJECT (Từ chối).
"""
                history = ""
                max_steps = 5 
                for step in range(max_steps):
                    print(f"\n--- [Vòng lặp Smart CD thứ {step + 1}/{max_steps}] ---")
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử:\n{history}\n\nNhiệm vụ: {USER_TASK}\n\nBước tiếp theo là gì?"
                    response = await asyncio.to_thread(llm.invoke, prompt) # Buff bất tử
                    print(f"🤖 AI Suy nghĩ:\n{response}\n")
                    
                    if "Final Answer:" in response:
                        report = response.split("Final Answer:")[1].strip()
                        send_discord_alert(f"📋 **SMART CD: KẾT QUẢ THẨM ĐỊNH DEPLOY** 📋\n\n{report}")
                        break
                        
                    action_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response)
                    input_match = re.search(r"Action Input:\s*(\{.*?\})", response, re.DOTALL)
                    
                    if action_match and input_match:
                        tool_name = action_match.group(1).strip()
                        try:
                            tool_args = json.loads(re.sub(r'```json\s*|```', '', input_match.group(1).strip()))
                            result = await session.call_tool(tool_name, arguments=tool_args)
                            history += f"\nThought: {response}\nObservation: {result.content[0].text}\n"
                        except Exception as e:
                            history += f"\nObservation: LỖI GỌI TOOL: {str(e)}\n"
                    else:
                        history += "\nObservation: Sai định dạng.\n"
    except Exception as e:
        print(f"❌ Lỗi Smart CD: {e}")

# ==========================================
# CÁC CỔNG NHẬN TÍN HIỆU (WEBHOOKS) & QUẢN LÝ LOCK
# ==========================================
llm_lock = asyncio.Lock()
current_llm_task = ""
prompt_task = None
saved_prompt_text = ""
cli_session = None

async def acquire_llm_lock(task_name: str) -> bool:
    global current_llm_task, prompt_task, saved_prompt_text, cli_session
    if llm_lock.locked():
        print(f"\n[SYSTEM] Hệ thống đang bận: {current_llm_task}. Đang xếp hàng chờ...")
    await llm_lock.acquire()
    current_llm_task = task_name
    if prompt_task and not prompt_task.done():
        if cli_session:
            saved_prompt_text = cli_session.default_buffer.text
        prompt_task.cancel()
    return True

def release_llm_lock():
    global current_llm_task
    current_llm_task = ""
    llm_lock.release()

async def run_investigation_wrapper(job_name):
    await acquire_llm_lock(f"Điều tra lỗi Jenkins (Job: {job_name})")
    try:
        await run_investigation(job_name)
    finally:
        print("✅ AI đã điều tra Jenkins xong. Nhả cờ khóa.")
        print("-" * 60)
        release_llm_lock()
async def run_metrics_investigation_wrapper(alert_name, alert_desc):
    await acquire_llm_lock(f"Điều tra Hạ tầng (Alert: {alert_name})")
    try:
        await run_metrics_investigation(alert_name, alert_desc)
    finally:
        print("✅ AI đã điều tra Hạ tầng xong. Nhả cờ khóa.")
        print("-" * 60)
        release_llm_lock()
async def run_success_report_wrapper(job_name):
    await acquire_llm_lock(f"Báo cáo Deploy (Job: {job_name})")
    try:
        await run_success_report(job_name)
    finally:
        print("✅ AI đã báo cáo Deploy xong. Nhả cờ khóa.")
        print("-" * 60)
        release_llm_lock()
async def run_smart_cd_wrapper(tf_dir):
    await acquire_llm_lock(f"Thẩm định Smart CD ({tf_dir})")
    try: 
        await run_smart_cd_approval(tf_dir)
    finally: 
        print("✅ AI đã thẩm định Smart CD xong. Nhả cờ khóa.")
        print("-" * 60)
        release_llm_lock()
@app.post("/webhook")
async def jenkins_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    job_name = data.get("job_name", "weather-app-pipeline")
    status = data.get("status")
    k8s_dir = data.get("k8s_dir", "weather-app/k8s")

    print(f"\n📥 [JENKINS WEBHOOK] Nhận tín hiệu: Job '{job_name}' - Trạng thái: {status}")

    if status == "FAILURE":
        print("🚨 Phát hiện lỗi Build! Xếp lịch AI chạy ngầm...")
        background_tasks.add_task(run_investigation_wrapper, job_name)
        return {"message": "AI Agent đang xếp lịch điều tra lỗi Build!"}
    
    elif status == "SUCCESS":
        print("💚 Build thành công! Xếp lịch AI kiểm tra sức khỏe hệ thống sau Deploy...")
        background_tasks.add_task(run_success_report_wrapper, job_name)
        return {"message": "AI Agent đang xếp lịch tổng hợp báo cáo sau khi Deploy thành công!"}
    
    elif status == "PENDING_APPROVAL":
        print("🛑 Xếp lịch AI thẩm định Smart CD rủi ro Deploy...")
        background_tasks.add_task(run_smart_cd_wrapper, k8s_dir)
        return {"message": "AI đang xếp lịch thẩm định Smart CD rủi ro Deploy!"}
    
    return {"message": "Trạng thái không xác định."}

@app.post("/prometheus-webhook")
async def prometheus_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        alerts = data.get("alerts", [])
        
        if not alerts:
            return {"message": "Payload trống."}

        first_alert = alerts[0]
        status = first_alert.get("status")
        alert_name = first_alert.get("labels", {}).get("alertname", "Cảnh báo không rõ")
        alert_desc = first_alert.get("annotations", {}).get("description", "Không có mô tả.")

        if status == "firing":
            print(f"\n🔥 [PROMETHEUS WEBHOOK] Nhận cảnh báo: {alert_name} - {alert_desc}")
            print("🚨 Xếp lịch AI điều tra quá tải K3s...")
            background_tasks.add_task(run_metrics_investigation_wrapper, alert_name, alert_desc)
            return {"message": "AI đang xếp lịch điều tra quá tải K3s!"}
        else:
            print(f"\n💚 [PROMETHEUS WEBHOOK] Cảnh báo {alert_name} đã được giải quyết (resolved).")
            return {"message": "Hệ thống K3s đã xanh."}

    except Exception as e:
        return {"message": f"Lỗi xử lý webhook: {str(e)}"}

# ==========================================
# 5. CHATBOT ENGINE
# ==========================================
async def run_chatbot(user_prompt: str):
    await acquire_llm_lock("Tương tác người dùng (Chatbot)")
    try:
        server_params = StdioServerParameters(command="python", args=["main.py"])
        async with intercepted_stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                SYSTEM_PROMPT = """Bạn là AI SRE + Developer Chatbot cấp cao, có khả năng đọc log Jenkins VÀ phân tích mã nguồn trong repo.

=== NGUYÊN TẮC CỐT LÕI ===
1. LUÔN giao tiếp bằng TIẾNG VIỆT. Trả lời trực tiếp, không vòng vo.
2. CHỈ ĐƯỢC GỌI 1 TOOL trong mỗi lượt. Đợi kết quả rồi mới gọi tiếp.
3. QUY TẮC THÉP: Không được dùng 'Final Answer' trong cùng lượt với 'Action'.
4. Thought tối đa 2 câu: câu 1 nêu kết quả vừa nhận, câu 2 nêu tool sẽ gọi tiếp. KHÔNG phân tích dài trong Thought.
5. Ngay khi đã có đủ dữ liệu để trả lời → viết Final Answer ngay, KHÔNG gọi thêm bất kỳ tool nào nữa.

=== DANH SÁCH TOOLS ===
[JENKINS - CI/CD]
- get_build_overview: {"job_name": "tên-job", "build_number": "lastBuild hoặc số nguyên"}
  → Xem bảng tóm tắt tất cả stages (status, thời gian). LUÔN gọi tool này TRƯỚC khi gọi get_jenkins_logs.
  → Nếu người dùng nói số build cụ thể (vd: "build 72") → dùng 72 NGAY, KHÔNG gọi thêm lần nào với lastBuild.
  → Chỉ gọi tool này 1 LẦN DUY NHẤT cho mỗi câu hỏi.
- get_jenkins_logs: {"job_name": "tên-job", "build_number": "lastBuild hoặc số nguyên", "target_stage": "Tên Stage cụ thể"}
  → Lấy log chi tiết. BẮT BUỘC truyền target_stage = tên stage bị FAILED (lấy từ get_build_overview).

[ĐỌC CODE & TÌM LỖI TRONG REPO]
- list_directory: {"directory_path": "đường-dẫn"}
  → Xem danh sách file trong thư mục (như lệnh ls).
- read_project_file: {"file_path": "đường-dẫn-file", "start_line": số (tùy chọn), "end_line": số (tùy chọn)}
  → Đọc file có đánh số dòng. Dùng start_line/end_line để chỉ đọc vùng cần thiết.
- search_in_file: {"file_path": "đường-dẫn-file", "keyword": "từ-khóa", "context_lines": 5}
  → Tìm kiếm từ khóa trong file, trả về các dòng khớp kèm context xung quanh (như grep).
  → Dùng khi biết tên hàm/module/lỗi từ stack trace và muốn tìm trong code.

[KUBERNETES & HẠ TẦNG]
- get_app_logs: {"namespace": "tên", "label_selector": "app=tên"}
- check_system_health: {"namespace": "tên-namespace"}
  → Namespace quan trọng: "default" (weather-app), "staging" (mcp-server-deployment).
  → Nếu người dùng hỏi "tổng thể" hoặc "tất cả" thì GỌI 2 LẦN: một lần cho "default", một lần cho "staging".
- fetch_metrics: {}
- restart_pod: {"pod_name": "tên", "namespace": "tên"}
- rollback: {"deployment_name": "tên", "namespace": "tên"}
- scale_deployment: {"deployment_name": "tên", "replicas": số, "namespace": "tên"}

=== QUY TRÌNH ĐIỀU TRA BUILD LỖI (BẮT BUỘC THEO THỨ TỰ) ===
Khi người dùng yêu cầu điều tra Jenkins build:
  BƯỚC 1: get_build_overview → xác định stage nào FAILED
  BƯỚC 2: get_jenkins_logs với target_stage = tên stage lỗi → đọc error message, tìm: tên exception, tên file, tên module, số dòng lỗi
  BƯỚC 3 (BẮT BUỘC - KHÔNG ĐƯỢC BỎ QUA - xác định loại lỗi rồi làm theo đúng playbook):

  ► LOẠI LỖI: Security Scan (Trivy / Checkov / SonarQube)
    Trivy báo CVE trong OS package (libssl, libgnutls, libc, sqlite, perl, zlib...):
      Chỉ gọi ĐÚNG 2 tool theo thứ tự, không hơn:
      1. read_project_file("weather-app/Jenkinsfile") → tìm flag --ignore-unfixed trong lệnh Trivy
      2. read_project_file("weather-app/Dockerfile") → tìm dòng FROM (base image hiện tại)
      SAU BƯỚC 2: viết Final Answer ngay, KHÔNG gọi list_directory, KHÔNG gọi requirements.txt, KHÔNG gọi tool nào thêm.
      Đối chiếu để kết luận "đã fix chưa":
         - Jenkinsfile có --ignore-unfixed chưa? → Nếu chưa = CHƯA FIX
         - Dockerfile có cập nhật base image chưa? → Nếu vẫn là image cũ = CHƯA FIX
      Fix đúng: Đề xuất thêm --ignore-unfixed vào lệnh Trivy (trong Jenkinsfile) HOẶC cập nhật base image lên phiên bản mới hơn (trong Dockerfile dòng FROM)
    Trivy báo CVE trong pip package (requests, cryptography...):
      1. Đọc requirements.txt để xem phiên bản hiện tại của package đó
      2. Fix: Tăng version của package lên bản đã vá lỗi

  ► LOẠI LỖI: Unit Test (pytest, unittest)
    1. Đọc log để tìm: tên file test, tên hàm test, dòng lỗi, exception type
    2. Gọi search_in_file với tên hàm bị lỗi trong file test đó
    3. Đọc file source code tương ứng (không phải file test) để hiểu logic thực tế
    4. Fix: Chỉ rõ dòng sai trong source code hoặc test

  ► LOẠI LỖI: Build Docker Image
    1. Đọc Dockerfile của project (weather-app/Dockerfile hoặc Dockerfile)
    2. Tìm lệnh COPY/ADD bị lỗi (file not found), lệnh RUN bị lỗi (package không tồn tại)
    3. Fix: Sửa đường dẫn COPY hoặc tên package trong RUN apt-get

  ► LOẠI LỖI: Deploy to K8s / Staging
    1. Gọi check_system_health để xem trạng thái Pod
    2. Nếu CrashLoopBackOff → gọi rollback
    3. Gọi get_app_logs để xem lý do crash

  BƯỚC 4: Final Answer phải bao gồm:
    - Trích dẫn nguyên văn error message từ log
    - Tên file + số dòng cần sửa (dựa vào kết quả tool đọc file)
    - Code block với nội dung CŨ → NỘI DUNG MỚI sau khi sửa
    - Nếu người dùng hỏi "đã fix chưa / code hiện tại có lỗi không": PHẢI kết luận rõ ràng "ĐÃ FIX" hoặc "CHƯA FIX" dựa trên nội dung file đọc được, kèm dẫn chứng cụ thể từ file.

TUYỆT ĐỐI KHÔNG được gọi Final Answer ngay sau khi đọc log mà chưa đọc code.
TUYỆT ĐỐI KHÔNG tìm kiếm tên OS package (libssl, libgnutls...) trong Dockerfile — đó là package hệ thống trong base image, không nằm trong code repo.
TUYỆT ĐỐI KHÔNG tự ý nhắc đến Jenkins build hoặc hỏi về job/build_number nếu người dùng KHÔNG đề cập đến Jenkins. Nếu câu hỏi chỉ liên quan K8s/metrics thì chỉ dùng K8s tools và trả lời đúng chủ đề đó.

=== ĐỊNH DẠNG PHẢN HỒI ===
Khi gọi tool:
Thought: [suy nghĩ ngắn gọn]
Action: [tên-tool]
Action Input: {"key": "value"}

Khi trả lời cuối cùng:
Final Answer: [nội dung]

QUY TẮC BẮT BUỘC CHO FINAL ANSWER:
- LUÔN paste nguyên bảng/số liệu thực tế từ kết quả tool vào câu trả lời.
- KHÔNG được tóm tắt bằng lời chung chung như "tất cả đang ổn", "mọi thứ hoạt động tốt".
- Sau khi paste dữ liệu thô, mới thêm nhận xét ngắn.

Ví dụ ĐÚNG (giám sát K8s):
Final Answer:
**Namespace default:**
NAME                              READY   STATUS    AGE
meteo-hist-deployment-xxx-yyy     1/1     Running   2d
**Namespace staging:**
NAME                              READY   STATUS    AGE
mcp-server-deployment-xxx-yyy     1/1     Running   5h
→ Nhận xét: Tất cả 2 pods đang Running bình thường, không có lỗi.

Ví dụ SAI (không được làm):
Final Answer: Tất cả pods đang hoạt động tốt. Không có vấn đề gì.

=== LƯU Ý ĐƯỜNG DẪN ===
- Dùng đường dẫn tương đối từ thư mục gốc repo: 'weather-app/Dockerfile', 'main.py', 'weather-app/requirements.txt'
- KHÔNG dùng đường dẫn tuyệt đối từ log Jenkins như /var/lib/jenkins/...
- Nếu người dùng không nói rõ tên job: mặc định dùng "weather-app-pipeline"
"""
                history = ""
                max_steps = 10 
                for step in range(max_steps):
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử:\n{history}\n\nNhiệm vụ: {user_prompt}\n\nBước tiếp theo là gì?"
                    
                    async def show_thinking():
                        try:
                            seconds = 0
                            while True:
                                await asyncio.sleep(15)
                                seconds += 15
                                print(f"⏳ (Đã đợi {seconds}s) AI vẫn đang suy nghĩ, vui lòng kiên nhẫn...")
                        except asyncio.CancelledError:
                            pass
                            
                    think_task = asyncio.create_task(show_thinking())
                    try:
                        response = await llm.ainvoke(prompt)
                    finally:
                        think_task.cancel()
                    
                    action_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response)
                    input_match = re.search(r"Action Input:\s*(\{.*?\})", response, re.DOTALL)
                    
                    if action_match and input_match:
                        tool_name = action_match.group(1).strip()
                        try:
                            raw_json = re.sub(r'```json\s*|```', '', input_match.group(1).strip())
                            tool_args = json.loads(raw_json)
                            print(f"🛠️ Đang gọi Tool: [{tool_name}]...")
                            tool_result = await session.call_tool(tool_name, arguments=tool_args)
                            observation = tool_result.content[0].text
                            # Cắt từ ĐẦU (giữ phần đầu chứa error message/line numbers), không cắt đuôi
                            if len(observation) > 8000:
                                observation = observation[:8000] + "\n...[CẮT BỚT - dùng start_line/end_line để đọc phần tiếp theo]..."
                            history += f"\nThought: {response}\nObservation: {observation}\n"
                        except Exception as e:
                            history += f"\nObservation: LỖI GỌI TOOL: {str(e)}\n"
                        
                        # Chống tràn bộ nhớ Context Window của LLM
                        if len(history) > MAX_HISTORY_CHARS:
                            history = "...[LỊCH SỬ CŨ ĐÃ BỊ XÓA BỚT ĐỂ CHỐNG TRÀN RAM]...\n" + history[-MAX_HISTORY_CHARS:]

                    elif "Final Answer:" in response:
                        answer = response.split("Final Answer:")[1].strip()
                        print(f"🤖 Chatbot:\n{answer}\n")
                        break
                    else:
                        print(f"🤖 Chatbot:\n{response}\n")
                        break
    except Exception as e:
        print(f"❌ Lỗi Chatbot: {e}")
    finally:
        print("-" * 60)
        release_llm_lock()

# ==========================================
# MAIN LOOP
# ==========================================
async def chat_loop():
    await asyncio.sleep(2) # Chờ server khởi động
    print("\n" + "="*40)
    print("✨ CHATBOT CLI ĐÃ SẴN SÀNG ✨")
    print("💡 Hướng dẫn thao tác:")
    print("   - Nhấn [Alt + Enter] để xuống dòng khi gõ.")
    print("   - Gõ 'exit' hoặc nhấn [Ctrl + C] 2 lần liên tiếp để thoát.")
    print("   - Gõ yêu cầu của bạn và nhấn [Enter] để gửi.")
    print("="*40 + "\n")
    
    kb = KeyBindings()
    
    @kb.add("enter")
    def _(event):
        # Enter bình thường dùng để Gửi lệnh
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def _(event):
        # Alt+Enter (hoặc Esc -> Enter) dùng để chèn dấu xuống dòng
        event.current_buffer.insert_text("\n")
        
    global prompt_task, saved_prompt_text, cli_session
    session = PromptSession(multiline=True, key_bindings=kb, erase_when_done=True)
    cli_session = session
    
    while True:
        try:
            if llm_lock.locked():
                # Nếu đang bị khóa, đợi cho đến khi rảnh
                await llm_lock.acquire()
                llm_lock.release()
                
            with patch_stdout():
                prompt_task = asyncio.create_task(session.prompt_async("\nBạn: ", default=saved_prompt_text, handle_sigint=False))
                user_input = await prompt_task
                saved_prompt_text = ""
                
            # Khôi phục lá chắn bảo vệ vì prompt_toolkit đã xóa nó sau khi xong
            try:
                asyncio.get_running_loop().add_signal_handler(signal.SIGINT, global_sigint_handler)
            except NotImplementedError:
                pass
                
            if not user_input.strip():
                continue
            
            # In lại câu hỏi của người dùng ra màn hình vì erase_when_done đã xóa nó
            print(f"\nBạn: {user_input.strip()}")
            
            if user_input.strip().lower() in ['exit', 'quit']:
                print("👋 Tạm biệt! Đang dọn dẹp hệ thống...")
                try:
                    ngrok.kill()
                except:
                    pass
                os._exit(0)
                
            await run_chatbot(user_input)
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Tạm biệt! Đang thoát chương trình...")
            try:
                ngrok.kill()
            except:
                pass
            os._exit(0)
            
        except asyncio.CancelledError:
            global cancelled_by_user
            if cancelled_by_user:
                # User bấm Ctrl+C lần 1
                cancelled_by_user = False
                saved_prompt_text = ""
            else:
                # Prompt bị hủy bởi luồng chạy ngầm (Webhook) để tạm ẩn, sẽ tự động mở lại sau
                pass
            continue
        except Exception as e:
            print(f"Lỗi: {e}")

async def tail_mcp_log():
    """Đọc file mcp_server.log liên tục và in ra màn hình an toàn qua patch_stdout"""
    while not os.path.exists("mcp_server.log"):
        await asyncio.sleep(0.5)
        
    try:
        with open("mcp_server.log", "r") as f:
            # Bắt đầu đọc từ cuối file để chỉ lấy log mới
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    await asyncio.sleep(0.2)
                    continue
                
                # Bỏ qua các log rác quá dài hoặc rỗng
                if line.strip():
                    print(f"⚙️ [MCP] {line.strip()}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"⚠️ Lỗi đọc log MCP: {e}")

import time

cancelled_by_user = False
ctrl_c_count = 0
last_ctrl_c_time = 0

def global_sigint_handler():
    global prompt_task, cancelled_by_user, ctrl_c_count, last_ctrl_c_time
    
    current_time = time.time()
    if current_time - last_ctrl_c_time > 3:
        ctrl_c_count = 0
    
    last_ctrl_c_time = current_time
    ctrl_c_count += 1
    
    if ctrl_c_count >= 2:
        print("\n👋 Tạm biệt! Đang thoát chương trình...")
        try:
            ngrok.kill()
        except:
            pass
        os._exit(0)
        
    # Khi AI đang chạy
    if llm_lock.locked():
        print("\n[Hệ thống] 🛡️ AI đang chạy. Nhấn Ctrl+C lần nữa trong 3s để BẮT BUỘC thoát.")
    else:
        print("\n[Hệ thống] Nhấn Ctrl+C lần nữa trong 3s để thoát chương trình.")
        cancelled_by_user = True
        if prompt_task and not prompt_task.done():
            prompt_task.cancel()

async def main():
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, global_sigint_handler)
    except NotImplementedError:
        # Bỏ qua nếu chạy trên Windows (add_signal_handler không hỗ trợ Windows)
        pass
        
    # Khởi chạy luồng theo dõi log MCP ngầm
    log_task = asyncio.create_task(tail_mcp_log())
    
    new_webhook = setup_self_register_webhook()
    if new_webhook:
        print(f"\n✨ AGENT ĐÃ SẴN SÀNG TẠI: {new_webhook}")
    else:
        print("\n⚠️ Cảnh báo: Tự động đăng ký thất bại, bạn có thể phải cập nhật thủ công.")
        
    print("🚀 AIOps Server đang lắng nghe trên cổng 5000...")
    print("👉 Endpoint 1 (Jenkins): /webhook")
    print("👉 Endpoint 2 (Prometheus): /prometheus-webhook")
    
    # Khởi chạy Uvicorn trên một luồng hoàn toàn độc lập (Thread)
    # Điều này giúp Uvicorn có Event Loop riêng và hoàn toàn miễn nhiễm với Ctrl+C (vốn chỉ gửi vào Main Thread)
    def run_uvicorn():
        config = uvicorn.Config(app, host="0.0.0.0", port=5000, log_level="warning")
        server = uvicorn.Server(config)
        import contextlib
        @contextlib.contextmanager
        def noop_capture_signals():
            yield
        server.capture_signals = noop_capture_signals
        server.run()
        
    threading.Thread(target=run_uvicorn, daemon=True).start()
    
    # Khởi chạy Chatbot CLI
    await chat_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nĐã thoát Chatbot.")
