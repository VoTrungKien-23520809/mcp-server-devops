import asyncio
import os
import sys
import json
import re
import requests
import uvicorn
import subprocess
from pyngrok import ngrok, conf
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_ollama import OllamaLLM
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
Model_name = "qwen2.5:14b"
llm = OllamaLLM(model=Model_name)
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

app = FastAPI()

def setup_self_register_webhook():
    print("🌐 Đang khởi động hệ thống Tự động đăng ký Webhook (K3s Mode)...")

    auth_token = os.getenv("NGROK_AUTH_TOKEN")
    if not auth_token:
        print("⚠️ LỖI: Thiếu NGROK_AUTH_TOKEN trong .env")
        return None

    try:
        conf.get_default().auth_token = auth_token
        public_url = ngrok.connect(5000).public_url
        webhook_url = f"{public_url}/prometheus-webhook"
        print(f"🚀 Ngrok Tunnel đã mở: {public_url}")
        print(f"🔗 Link Webhook mục tiêu: {webhook_url}")

        azure_ip = os.getenv("AZURE_IP")
        ssh_key = os.getenv("SSH_KEY_PATH")

        bash_script = f"""
        export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
        kubectl get secret alertmanager-prom-stack-kube-prometheus-alertmanager -n monitoring -o jsonpath='{{.data.alertmanager\\.yaml}}' | base64 --decode > /tmp/am.yaml
        sed -i "s|url:.*|url: '{webhook_url}'|g" /tmp/am.yaml
        kubectl create secret generic alertmanager-prom-stack-kube-prometheus-alertmanager -n monitoring --from-file=alertmanager.yaml=/tmp/am.yaml --dry-run=client -o yaml | kubectl apply -f -
        rm /tmp/am.yaml
        """

        full_ssh_cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no", "-i", ssh_key,
            f"azureuser@{azure_ip}", "bash", "-c", bash_script
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
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ Đã kết nối thành công tới MCP Server (CI/CD Mode)!")

                SYSTEM_PROMPT = """Bạn là một Kỹ sư SRE cấp cao.
QUY TẮC ĐIỀU TRA (REACT LOOP):
1. THOUGHT: Suy nghĩ phải NGẮN GỌN (tối đa 4 câu). Phân tích logic vấn đề.
2. ACTION: Bạn CHỈ ĐƯỢC GỌI 1 TOOL DUY NHẤT trong mỗi vòng lặp.

Danh sách Tools:
- get_jenkins_logs: {"job_name": "tên-job", "build_number": "lastBuild", "date_filter": "DD/MM/YYYY (tùy chọn)"}
- get_app_logs: {"namespace": "tên-namespace", "label_selector": "app=tên-app", "since": "DD/MM/YYYY hoặc 1h (tùy chọn)"}
- get_k8s_nodes: {}
- fetch_metrics: {}
- list_directory: {"directory_path": "đường-dẫn"}
- read_project_file: {"file_path": "đường-dẫn-file"}
- check_system_health: {"namespace": "tên-namespace"}
- rollback: {"deployment_name": "tên-deployment", "namespace": "tên-namespace"}
- restart_pod: {"pod_name": "tên-pod", "namespace": "tên-namespace"}

ĐỊNH DẠNG 1 (Khi cần gọi Tool):
Thought: [Suy nghĩ ngắn gọn]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (CHỈ GỌI KHI ĐÃ CÓ ĐỦ DỮ LIỆU):
Thought: Tôi đã thu thập đủ dữ liệu thực tế và sẵn sàng báo cáo.
Final Answer:
#### 1. Tình trạng Hạ Tầng & CI/CD:
#### 2. Đánh giá Hiệu năng:
#### 3. Tình trạng Ứng Dụng:
#### 4. Hành động tự động (Auto-remediation) & Giải pháp:
"""

                USER_TASK = f"""
Nhiệm vụ điều tra bắt buộc:
1. Gọi get_jenkins_logs (job_name: '{job_name}') để ĐỌC LOG của bản build vừa thất bại.
2. Đợi có kết quả log, gọi tiếp fetch_metrics.
3. Đợi kết quả fetch_metrics. Gọi check_system_health để xem bản deploy lỗi này có làm chết Pod trên K8s không.
4. BẮT BUỘC gọi get_app_logs (namespace 'default', app 'meteo-hist').

RẼ NHÁNH ĐIỀU TRA:
- Nếu Jenkins báo SUCCESS: Xuất Final Answer tổng hợp tình hình.
- Nếu Jenkins báo FAILURE: Đọc kỹ log Jenkins để tìm manh mối. Dùng list_directory và read_project_file để đọc file liên quan.

RẼ NHÁNH K8S:
- Nếu thấy K8s có Pod bị CrashLoopBackOff/ImagePullBackOff, BẮT BUỘC gọi tool rollback trước khi xuất Final Answer.
- Nếu Pod K8s vẫn sống, KHÔNG CẦN dùng tool rollback.

⚠️ LƯU Ý VỀ ĐƯỜNG DẪN: Dùng đường dẫn tương đối (ví dụ: 'weather-app/Dockerfile').
"""

                history = ""
                max_steps = 10

                for step in range(max_steps):
                    print(f"\n--- [Vòng lặp CI/CD thứ {step + 1}/{max_steps}] ---")
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử điều tra:\n{history}\n\nNhiệm vụ của bạn: {USER_TASK}\n\nBước tiếp theo của bạn là gì?"
                    response = await asyncio.to_thread(llm.invoke, prompt)
                    print(f"🤖 AI Suy nghĩ & Quyết định:\n{response}\n")

                    if "Final Answer:" in response:
                        final_report = response.split("Final Answer:")[1].strip()
                        print("\n" + "="*40 + "\n👉 BÁO CÁO PHÂN TÍCH HỆ THỐNG\n" + "="*40)
                        print(final_report)
                        send_discord_alert(f"🚨 **BÁO CÁO JENKINS TỪ AI SRE** 🚨\n\n{final_report}")
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
                            if len(observation) > 4000:
                                observation = observation[:4000] + "\n...[ĐÃ CẮT BỚT VÌ LOG QUÁ DÀI]..."
                            print(f"✅ Đã có bằng chứng! ({len(observation)} ký tự)")
                            history += f"\nThought: {response}\nObservation: {observation}\n"
                        except json.JSONDecodeError:
                            history += f"\nThought: {response}\nObservation: LỖI: Action Input không phải JSON hợp lệ.\n"
                        except Exception as e:
                            history += f"\nThought: {response}\nObservation: LỖI KHI GỌI TOOL: {str(e)}.\n"
                    else:
                        history += f"\nThought: {response}\nObservation: LỖI: Bạn BẮT BUỘC phải dùng 'Action:' và 'Action Input:' hoặc 'Final Answer:'.\n"

    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng: {e}")


# ==========================================
# 2. BỘ NÃO ĐIỀU TRA HẠ TẦNG (PROMETHEUS ALERTS)
# ==========================================
async def run_metrics_investigation(alert_name: str, alert_desc: str):
    print(f"\n🚨 AI THÁM TỬ ĐÃ THỨC DẬY! Điều tra cảnh báo hạ tầng: {alert_name}")

    server_params = StdioServerParameters(command="python", args=["main.py"])

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                SYSTEM_PROMPT = """Bạn là một Kỹ sư SRE cấp cao.
QUY TẮC ĐIỀU TRA (REACT LOOP):
1. THOUGHT: Suy nghĩ NGẮN GỌN (tối đa 4 câu).
2. ACTION: CHỈ ĐƯỢC GỌI 1 TOOL DUY NHẤT trong mỗi vòng lặp.

Danh sách Tools:
- get_app_logs: {"namespace": "tên-namespace", "label_selector": "app=tên-app", "since": "DD/MM/YYYY hoặc 1h (tùy chọn)"}
- get_k8s_nodes: {}
- fetch_metrics: {}
- check_system_health: {"namespace": "tên-namespace"}
- restart_pod: {"pod_name": "tên-pod", "namespace": "tên-namespace"}
- scale_deployment: {"deployment_name": "tên-deployment", "replicas": số-lượng, "namespace": "tên-namespace"}
- rollback: {"deployment_name": "tên-deployment", "namespace": "tên-namespace"}

ĐỊNH DẠNG 1 (Khi cần gọi Tool):
Thought: [Suy nghĩ ngắn gọn]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (CHỈ GỌI KHI ĐÃ CÓ ĐỦ BẰNG CHỨNG):
Final Answer:
#### 1. Nguyên nhân cảnh báo:
#### 2. Tình trạng thực tế:
#### 3. Phân tích Ứng dụng:
#### 4. Hành động Tự động đã thực hiện (Auto-remediation):

QUY TẮC XỬ LÝ:
1. Nếu Alert là "AppDeadlock": BẮT BUỘC gọi restart_pod ngay.
2. Nếu Pod ở trạng thái CrashLoopBackOff: BẮT BUỘC gọi rollback.
3. TUYỆT ĐỐI KHÔNG suy diễn từ log cũ nếu Pod vẫn Running.
"""

                USER_TASK = f"""
Cảnh báo từ Prometheus: '{alert_name}'
Mô tả chi tiết: '{alert_desc}'

Nhiệm vụ:
1. Tự suy luận tên Ứng dụng, Deployment và Namespace từ mô tả cảnh báo.
2. Gọi fetch_metrics hoặc check_system_health để thu thập dữ liệu thực tế.
3. Gọi get_app_logs (namespace: 'default', label_selector: 'app=meteo-hist').
4. Thực hiện hành động khắc phục phù hợp (scale/restart/rollback).
5. Xuất Final Answer sau khi đã thực thi xong.
"""

                history = ""
                max_steps = 10

                for step in range(max_steps):
                    print(f"\n--- [Vòng lặp Hạ Tầng thứ {step + 1}/{max_steps}] ---")
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử:\n{history}\n\nNhiệm vụ: {USER_TASK}\n\nBước tiếp theo là gì?"
                    response = await asyncio.to_thread(llm.invoke, prompt)
                    print(f"🤖 AI Suy nghĩ:\n{response}\n")

                    if "Final Answer:" in response:
                        final_report = response.split("Final Answer:")[1].strip()
                        send_discord_alert(f"🔥 **BÁO ĐỘNG K3S TỪ AI SRE** 🔥\n\n{final_report}")
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
                            if len(observation) > 4000:
                                observation = observation[:4000] + "\n...[CẮT BỚT]..."
                            history += f"\nThought: {response}\nObservation: {observation}\n"
                        except Exception as e:
                            history += f"\nObservation: LỖI KHI GỌI TOOL: {str(e)}.\n"
                    else:
                        history += "\nObservation: Sai định dạng ReAct. Vui lòng thử lại.\n"

    except Exception as e:
        print(f"❌ Lỗi: {e}")


# ==========================================
# 3. BỘ NÃO BÁO CÁO SAU DEPLOY (SUCCESS)
# ==========================================
async def run_success_report(job_name: str):
    print(f"\n✅ AI ĐÃ THỨC DẬY! Tổng hợp báo cáo sức khỏe hệ thống sau khi Deploy: {job_name}")

    server_params = StdioServerParameters(command="python", args=["main.py"])

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

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

ĐỊNH DẠNG 2 (CHỈ GỌI KHI ĐÃ LẤY ĐỦ DỮ LIỆU):
Final Answer:
#### 1. Trạng thái CI/CD:
#### 2. Tình trạng Kubernetes:
#### 3. Hiệu năng Hệ thống (Prometheus):
#### 4. Đánh giá chung:
"""

                USER_TASK = f"""
Job Jenkins '{job_name}' VỪA DEPLOY THÀNH CÔNG.
1. Gọi check_system_health (namespace: 'default').
2. Gọi fetch_metrics để lấy chỉ số CPU và RAM.
3. Tổng hợp và xuất Final Answer.
"""

                history = ""
                max_steps = 5

                for step in range(max_steps):
                    print(f"\n--- [Vòng lặp Báo Cáo thứ {step + 1}/{max_steps}] ---")
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử:\n{history}\n\nNhiệm vụ: {USER_TASK}\n\nBước tiếp theo là gì?"
                    response = await asyncio.to_thread(llm.invoke, prompt)
                    print(f"🤖 AI Suy nghĩ:\n{response}\n")

                    if "Final Answer:" in response:
                        final_report = response.split("Final Answer:")[1].strip()
                        send_discord_alert(f"🎉 **BÁO CÁO DEPLOY THÀNH CÔNG** 🎉\n\n{final_report}")
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

    except Exception as e:
        import traceback
        print(f"❌ Lỗi: {e}")
        traceback.print_exc()


# ==========================================
# 4. BỘ NÃO SMART CD
# ==========================================
async def run_smart_cd_approval(k8s_dir: str = "weather-app/k8s"):
    print(f"\n🛑 [SMART CD] AI ĐANG THẨM ĐỊNH RỦI RO TRIỂN KHAI CHO THƯ MỤC: {k8s_dir}")
    server_params = StdioServerParameters(command="python", args=["main.py"])

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                SYSTEM_PROMPT = """Bạn là một Kỹ sư SecOps/Gatekeeper cấp cao.
Nhiệm vụ: quyết định có cho phép deploy lên Production không.

ĐỊNH DẠNG 1 (GỌI TOOL):
Thought: [Suy nghĩ]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (QUYẾT ĐỊNH PHÊ DUYỆT):
Final Answer:
#### QUYẾT ĐỊNH: [CHỈ GHI '🟢 APPROVE' HOẶC '🔴 REJECT']
#### 1. Đánh giá rủi ro cấu hình K8s:
#### 2. Sức chịu tải K8s:
#### 3. Lý do:
"""
                USER_TASK = f"""
1. Gọi fetch_metrics và check_system_health để xem hệ thống có đang quá tải không.
2. Gọi read_project_file với '{k8s_dir}/deployment.yaml'.
3. Đưa ra Quyết định APPROVE hoặc REJECT.
"""
                history = ""
                max_steps = 5
                for step in range(max_steps):
                    print(f"\n--- [Vòng lặp Smart CD thứ {step + 1}/{max_steps}] ---")
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử:\n{history}\n\nNhiệm vụ: {USER_TASK}\n\nBước tiếp theo là gì?"
                    response = await asyncio.to_thread(llm.invoke, prompt)
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
# 5. BỘ NÃO CHAT - TƯƠNG TÁC VỚI NGƯỜI DÙNG (MỚI)
# ==========================================
async def run_chat_agent(user_message: str, chat_history: list) -> str:
    """
    Bộ não xử lý câu hỏi trực tiếp từ người dùng.
    Hỗ trợ hỏi đáp tự nhiên, truy vấn log theo ngày, kiểm tra hệ thống theo yêu cầu.
    """
    print(f"\n💬 CHAT AGENT: Nhận câu hỏi: {user_message}")

    server_params = StdioServerParameters(command="python", args=["main.py"])

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                SYSTEM_PROMPT = """Bạn là AI SRE Assistant thông minh, hỗ trợ người dùng truy vấn và giám sát hệ thống theo yêu cầu.

Bạn có thể:
- Lấy log Jenkins theo ngày cụ thể hoặc build number
- Lấy log ứng dụng K8s theo ngày hoặc khoảng thời gian
- Kiểm tra trạng thái Pod, Node, CPU, RAM
- Đọc file cấu hình, code trong dự án
- Thực hiện rollback, restart, scale theo yêu cầu

Danh sách Tools:
- get_jenkins_logs: {"job_name": "tên-job", "build_number": "lastBuild", "date_filter": "DD/MM/YYYY (tùy chọn)"}
- get_app_logs: {"namespace": "default", "label_selector": "app=meteo-hist", "since": "DD/MM/YYYY hoặc 1h (tùy chọn)", "tail": 50}
- get_k8s_nodes: {}
- fetch_metrics: {}
- check_system_health: {"namespace": "default"}
- list_directory: {"directory_path": "đường-dẫn"}
- read_project_file: {"file_path": "đường-dẫn-file"}
- rollback: {"deployment_name": "tên-deployment", "namespace": "default"}
- restart_pod: {"pod_name": "tên-pod", "namespace": "default"}
- scale_deployment: {"deployment_name": "tên-deployment", "replicas": số, "namespace": "default"}

QUY TẮC:
1. Phân tích câu hỏi để xác định tool phù hợp nhất.
2. Nếu người dùng hỏi về ngày cụ thể (ví dụ "ngày 1/5", "hôm qua"), dùng tham số date_filter hoặc since.
3. Nếu không cần tool (câu hỏi kiến thức chung), trả lời trực tiếp bằng Final Answer.
4. Trả lời bằng tiếng Việt, ngắn gọn, dễ hiểu.
5. Sau khi có kết quả, LUÔN phân tích và giải thích ý nghĩa cho người dùng.

ĐỊNH DẠNG 1 (Khi cần gọi Tool):
Thought: [Phân tích câu hỏi, xác định cần tool nào]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (Khi đã có đủ thông tin):
Final Answer: [Câu trả lời đầy đủ, rõ ràng bằng tiếng Việt]
"""

                # Xây dựng lịch sử hội thoại để AI có ngữ cảnh
                history_text = ""
                for msg in chat_history[-6:]:  # Chỉ lấy 6 tin nhắn gần nhất để tránh tràn context
                    role = "Người dùng" if msg["role"] == "user" else "AI"
                    history_text += f"{role}: {msg['content']}\n"

                history = ""
                max_steps = 8
                final_answer = "Xin lỗi, tôi không thể xử lý yêu cầu này. Vui lòng thử lại."

                for step in range(max_steps):
                    print(f"\n--- [Chat Step {step + 1}/{max_steps}] ---")

                    prompt = f"""{SYSTEM_PROMPT}

Lịch sử hội thoại gần đây:
{history_text}

Lịch sử điều tra trong phiên này:
{history}

Câu hỏi hiện tại của người dùng: {user_message}

Bước tiếp theo của bạn là gì?"""

                    response = await asyncio.to_thread(llm.invoke, prompt)
                    print(f"🤖 Chat AI:\n{response}\n")

                    if "Final Answer:" in response:
                        final_answer = response.split("Final Answer:")[1].strip()
                        break

                    action_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response)
                    input_match = re.search(r"Action Input:\s*(\{.*?\})", response, re.DOTALL)

                    if action_match and input_match:
                        tool_name = action_match.group(1).strip()
                        raw_json = re.sub(r'```json\s*|```', '', input_match.group(1).strip())
                        try:
                            tool_args = json.loads(raw_json)
                            print(f"🛠️ Chat Agent gọi Tool: [{tool_name}] với {tool_args}")
                            tool_result = await session.call_tool(tool_name, arguments=tool_args)
                            observation = tool_result.content[0].text
                            if len(observation) > 3000:
                                observation = observation[:3000] + "\n...[ĐÃ CẮT BỚT]..."
                            history += f"\nThought: {response}\nObservation: {observation}\n"
                        except json.JSONDecodeError:
                            history += f"\nObservation: LỖI: JSON không hợp lệ. Thử lại.\n"
                        except Exception as e:
                            history += f"\nObservation: LỖI GỌI TOOL [{tool_name}]: {str(e)}\n"
                    else:
                        # AI không gọi tool, cũng không có Final Answer → ép kết thúc
                        if response.strip():
                            final_answer = response.strip()
                        break

                return final_answer

    except Exception as e:
        print(f"❌ Lỗi Chat Agent: {e}")
        return f"Đã xảy ra lỗi khi xử lý yêu cầu: {str(e)}"


# ==========================================
# CÁC CỔNG NHẬN TÍN HIỆU (WEBHOOKS) & CHAT
# ==========================================
is_investigating = False
is_metrics_investigating = False
is_reporting = False
is_cd_approving = False


async def run_investigation_wrapper(job_name):
    global is_investigating
    try:
        await run_investigation(job_name)
    finally:
        is_investigating = False
        print("✅ AI đã điều tra Jenkins xong. Nhả cờ khóa.")


async def run_metrics_investigation_wrapper(alert_name, alert_desc):
    global is_metrics_investigating
    try:
        await run_metrics_investigation(alert_name, alert_desc)
    finally:
        is_metrics_investigating = False
        print("✅ AI đã điều tra Hạ tầng xong. Nhả cờ khóa.")


async def run_success_report_wrapper(job_name):
    global is_reporting
    try:
        await run_success_report(job_name)
    finally:
        is_reporting = False
        print("✅ AI đã tổng hợp báo cáo Deploy xong. Nhả cờ khóa.")


async def run_smart_cd_wrapper(tf_dir):
    global is_cd_approving
    try:
        await run_smart_cd_approval(tf_dir)
    finally:
        is_cd_approving = False
        print("✅ AI đã thẩm định Deploy xong. Nhả cờ khóa.")


# ── Endpoint giao diện Chat ──────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def chat_ui():
    """Trả về giao diện chat HTML."""
    with open("chat_ui.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/chat")
async def chat_endpoint(request: Request):
    """
    Nhận câu hỏi từ người dùng và trả về câu trả lời từ AI.
    Body JSON: {"message": "câu hỏi", "history": [...]}
    """
    data = await request.json()
    user_message = data.get("message", "").strip()
    chat_history = data.get("history", [])

    if not user_message:
        return {"response": "Vui lòng nhập câu hỏi."}

    print(f"\n💬 [CHAT] Người dùng hỏi: {user_message}")
    answer = await run_chat_agent(user_message, chat_history)
    return {"response": answer}


# ── Webhook Jenkins ──────────────────────────────────────────────
@app.post("/webhook")
async def jenkins_webhook(request: Request, background_tasks: BackgroundTasks):
    global is_investigating, is_reporting, is_cd_approving
    data = await request.json()
    job_name = data.get("job_name", "weather-app-pipeline")
    status = data.get("status")
    k8s_dir = data.get("k8s_dir", data.get("k8s", "weather-app/k8s"))  # Sửa bug key mismatch

    print(f"\n📥 [JENKINS WEBHOOK] Nhận tín hiệu: Job '{job_name}' - Trạng thái: {status}")

    if status == "FAILURE":
        if is_investigating:
            return {"message": "AI đang bận điều tra CI/CD, bỏ qua."}
        is_investigating = True
        background_tasks.add_task(run_investigation_wrapper, job_name)
        return {"message": "AI Agent đang tiến hành điều tra lỗi Build!"}

    elif status == "SUCCESS":
        if is_reporting:
            return {"message": "AI đang bận viết báo cáo, bỏ qua."}
        is_reporting = True
        background_tasks.add_task(run_success_report_wrapper, job_name)
        return {"message": "AI Agent đang tổng hợp báo cáo sau khi Deploy thành công!"}

    elif status == "PENDING_APPROVAL":
        if is_cd_approving:
            return {"message": "AI đang bận thẩm định, bỏ qua."}
        is_cd_approving = True
        background_tasks.add_task(run_smart_cd_wrapper, k8s_dir)
        return {"message": "AI đang tiến hành thẩm định Smart CD rủi ro Deploy!"}

    return {"message": "Trạng thái không xác định."}


# ── Webhook Prometheus ───────────────────────────────────────────
@app.post("/prometheus-webhook")
async def prometheus_webhook(request: Request, background_tasks: BackgroundTasks):
    global is_metrics_investigating
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
            if is_metrics_investigating:
                return {"message": "AI đang bận."}
            is_metrics_investigating = True
            background_tasks.add_task(run_metrics_investigation_wrapper, alert_name, alert_desc)
            return {"message": "AI đang điều tra quá tải K3s!"}
        else:
            print(f"\n💚 [PROMETHEUS WEBHOOK] Cảnh báo {alert_name} đã được giải quyết.")
            return {"message": "Hệ thống K3s đã xanh."}

    except Exception as e:
        return {"message": f"Lỗi xử lý webhook: {str(e)}"}


if __name__ == "__main__":
    new_webhook = setup_self_register_webhook()

    if new_webhook:
        print(f"\n✨ AGENT ĐÃ SẴN SÀNG TẠI: {new_webhook}")
    else:
        print("\n⚠️ Cảnh báo: Tự động đăng ký thất bại.")

    print("🚀 AIOps Server đang lắng nghe trên cổng 5000...")
    print("👉 Endpoint Chat:       GET  /")
    print("👉 Endpoint Chat API:   POST /chat")
    print("👉 Endpoint Jenkins:    POST /webhook")
    print("👉 Endpoint Prometheus: POST /prometheus-webhook")
    uvicorn.run(app, host="0.0.0.0", port=5000)