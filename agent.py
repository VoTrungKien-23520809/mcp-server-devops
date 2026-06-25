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
from multi_agent import process_with_multi_agent
from langchain_ollama import ChatOllama
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
llm = ChatOllama(model=Model_name, num_ctx=OPT_CTX)
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
        #Chuỗi lệnh Bash tự động lấy Secret, sửa URL và apply lại vào K3s
        bash_script = f"""
        export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
        
        kubectl get secret alertmanager-prom-stack-kube-prometheus-alertmanager -n monitoring -o jsonpath="{{.data['alertmanager\\\\.yaml']}}" | base64 --decode > /tmp/am.yaml
        
        if [ ! -s /tmp/am.yaml ] || grep -q '""' /tmp/am.yaml; then
cat <<EOF > /tmp/am.yaml
global:
  resolve_timeout: 5m
route:
  group_by: ['alertname', 'job']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 3h
  receiver: 'mcp-webhook'
receivers:
- name: 'mcp-webhook'
  webhook_configs:
  - url: 'http://localhost:5000/prometheus-webhook'
    send_resolved: true
EOF
        fi
        
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

                USER_TASK = f"Nhiệm vụ: Phân tích nguyên nhân lỗi build của job {job_name}. Hãy tìm stage lỗi và log lỗi tương ứng để phân tích."

                final_answer = await process_with_multi_agent(USER_TASK, session, llm, stream_output=True)
                print("\n" + "="*40 + "\n👉 BÁO CÁO PHÂN TÍCH HỆ THỐNG (AI SRE REPORT)\n" + "="*40)
                print(final_answer)
                print("="*40)
                alert_msg = f"🚨 **BÁO CÁO JENKINS TỪ AI SRE** 🚨\n\n{final_answer}"
                send_discord_alert(alert_msg)
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

                USER_TASK = f"Nhiệm vụ: Phân tích cảnh báo Prometheus: {alert_name} - {alert_desc}. Hãy kiểm tra pod log hoặc hệ thống K8s tương ứng để tìm nguyên nhân và khắc phục."

                final_answer = await process_with_multi_agent(USER_TASK, session, llm, stream_output=True)
                print("\n" + "="*40 + "\n👉 BÁO CÁO TỪ AI SRE\n" + "="*40)
                print(final_answer)
                print("="*40)
                alert_msg = f"🚨 **BÁO CÁO SỰ CỐ TỪ AI SRE** 🚨\n\n{final_answer}"
                send_discord_alert(alert_msg)
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

                USER_TASK = f"Nhiệm vụ: Viết báo cáo sức khỏe hệ thống sau khi job Jenkins {job_name} deploy thành công. (Gợi ý: Kiểm tra K8s health và metrics)."

                final_answer = await process_with_multi_agent(USER_TASK, session, llm, stream_output=True)
                print("\n" + "="*40 + "\n👉 AI SRE REPORT\n" + "="*40)
                print(final_answer)
                print("="*40)
                alert_msg = f"✅ **BÁO CÁO THÀNH CÔNG TỪ AI SRE** ✅\n\n{final_answer}"
                send_discord_alert(alert_msg)
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
                
                USER_TASK = f"Nhiệm vụ: Thẩm định rủi ro Smart CD. Hãy kiểm tra file cấu hình deployment trong thư mục {k8s_dir} xem có rủi ro gì không (ví dụ: dùng latest tag). Đưa ra Quyết định APPROVE (Cho phép) hoặc REJECT (Từ chối)."
                final_answer = await process_with_multi_agent(USER_TASK, session, llm, stream_output=True)
                print("\n" + "="*40 + "\n👉 BÁO CÁO THẨM ĐỊNH (AI GATEKEEPER)\n" + "="*40)
                print(final_answer)
                print("="*40)
                alert_msg = f"🛡️ **SMART CD: YÊU CẦU PHÊ DUYỆT DEPLOY** 🛡️\n\n{final_answer}"
                send_discord_alert(alert_msg)
    except Exception as e:
        print(f"❌ Lỗi Smart CD: {e}")

# ==========================================
# CÁC CỔNG NHẬN TÍN HIỆU (WEBHOOKS) & QUẢN LÝ LOCK
# ==========================================
llm_lock = None
main_loop = None
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
        if main_loop:
            asyncio.run_coroutine_threadsafe(run_investigation_wrapper(job_name), main_loop)
        return {"message": "AI Agent đang xếp lịch điều tra lỗi Build!"}
    
    elif status == "SUCCESS":
        print("💚 Build thành công! Xếp lịch AI kiểm tra sức khỏe hệ thống sau Deploy...")
        if main_loop:
            asyncio.run_coroutine_threadsafe(run_success_report_wrapper(job_name), main_loop)
        return {"message": "AI Agent đang xếp lịch tổng hợp báo cáo sau khi Deploy thành công!"}
    
    elif status == "PENDING_APPROVAL":
        print("🛑 Xếp lịch AI thẩm định Smart CD rủi ro Deploy...")
        if main_loop:
            asyncio.run_coroutine_threadsafe(run_smart_cd_wrapper(k8s_dir), main_loop)
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

        ignore_alerts = ["InfoInhibitor", "Watchdog", "KubeControllerManagerDown", "KubeSchedulerDown", "KubeProxyDown", "AlertmanagerFailedToSendAlerts", "AlertmanagerClusterFailedToSendAlerts"]
        if alert_name in ignore_alerts:
            print(f"🙈 Đã tự động bỏ qua cảnh báo hệ thống mặc định: {alert_name}")
            return {"message": "Ignored noise alert."}

        if status == "firing":
            print(f"\n🔥 [PROMETHEUS WEBHOOK] Nhận cảnh báo: {alert_name} - {alert_desc}")
            print("🚨 Xếp lịch AI điều tra quá tải K3s...")
            if main_loop:
                asyncio.run_coroutine_threadsafe(run_metrics_investigation_wrapper(alert_name, alert_desc), main_loop)
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
                
                final_answer = await process_with_multi_agent(user_prompt, session, llm, stream_output=True)
            print(f"🤖 Chatbot:\n{final_answer}\n")
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
            if llm_lock is None:
                break
                
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
            if isinstance(e, RuntimeError) and "closed" in str(e).lower():
                break
            print(f"Lỗi: {e}")
            await asyncio.sleep(0.1)

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
    global main_loop, llm_lock
    main_loop = asyncio.get_running_loop()
    llm_lock = asyncio.Lock()
    try:
        main_loop.add_signal_handler(signal.SIGINT, global_sigint_handler)
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
