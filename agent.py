import asyncio
import contextlib
import os
import signal
import subprocess
import threading
import time

import psutil
import uvicorn
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from pyngrok import conf, ngrok
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout

import state
from webhooks import app, run_chatbot

load_dotenv()


def analyze_system_hardware() -> tuple[int, int]:
    ram_gb = psutil.virtual_memory().total / (1024**3)
    vram_gb = 0
    gpu_name = "N/A"
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            text=True,
        )
        if out.strip():
            parts = out.strip().split(',')
            gpu_name = parts[0].strip()
            vram_gb = float(parts[1].strip()) / 1024
    except Exception:
        pass

    print(f"💻 Thông số phần cứng: RAM {ram_gb:.1f}GB | VRAM {vram_gb:.1f}GB ({gpu_name})")

    if ram_gb > 31 or vram_gb >= 16:
        print("🚀 Kích hoạt cấu hình: MAX SETTINGS (Context: 16k tokens)")
        return 16384, 60000
    elif ram_gb > 15 or vram_gb >= 8:
        print("⚖️ Kích hoạt cấu hình: TIÊU CHUẨN (Context: 8k tokens)")
        return 8192, 30000
    else:
        print("🛡️ Kích hoạt cấu hình: AN TOÀN (Context: 4k tokens)")
        return 4096, 15000


def setup_self_register_webhook() -> str | None:
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
        kubectl get secret alertmanager-prom-stack-kube-prometheus-alertmanager -n monitoring \\
            -o jsonpath='{{{{.data.alertmanager\\.yaml}}}}' | base64 --decode > /tmp/am.yaml
        sed -i "s|url:.*|url: '{webhook_url}'|g" /tmp/am.yaml
        kubectl create secret generic alertmanager-prom-stack-kube-prometheus-alertmanager \\
            -n monitoring --from-file=alertmanager.yaml=/tmp/am.yaml --dry-run=client -o yaml \\
            | kubectl apply -f -
        rm /tmp/am.yaml
        """

        result = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-i", ssh_key, f"azureuser@{azure_ip}", "bash", "-c", bash_script],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print("✅ Alertmanager (K3s) đã được cập nhật link Webhook mới tự động!")
            return webhook_url
        else:
            print(f"❌ Lỗi khi cập nhật cấu hình K3s: {result.stderr}")
            return None

    except Exception as e:
        print(f"❌ Lỗi trong quá trình tự đăng ký: {str(e)}")
        return None


async def tail_mcp_log():
    while not os.path.exists("mcp_server.log"):
        await asyncio.sleep(0.5)
    try:
        with open("mcp_server.log", "r") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if not line:
                    await asyncio.sleep(0.2)
                    continue
                if line.strip():
                    print(f"⚙️ [MCP] {line.strip()}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"⚠️ Lỗi đọc log MCP: {e}")


_cancelled_by_user = False
_ctrl_c_count = 0
_last_ctrl_c_time = 0.0


def _sigint_handler():
    global _cancelled_by_user, _ctrl_c_count, _last_ctrl_c_time

    now = time.time()
    if now - _last_ctrl_c_time > 3:
        _ctrl_c_count = 0
    _last_ctrl_c_time = now
    _ctrl_c_count += 1

    if _ctrl_c_count >= 2:
        print("\n👋 Tạm biệt! Đang thoát chương trình...")
        try:
            ngrok.kill()
        except Exception:
            pass
        os._exit(0)

    if state.llm_lock.locked():
        print("\n[Hệ thống] 🛡️ AI đang chạy. Nhấn Ctrl+C lần nữa trong 3s để BẮT BUỘC thoát.")
    else:
        print("\n[Hệ thống] Nhấn Ctrl+C lần nữa trong 3s để thoát chương trình.")
        _cancelled_by_user = True
        if state.prompt_task and not state.prompt_task.done():
            state.prompt_task.cancel()


async def chat_loop():
    await asyncio.sleep(2)
    print("\n" + "="*40)
    print("✨ CHATBOT CLI ĐÃ SẴN SÀNG ✨")
    print("   - Nhấn [Alt + Enter] để xuống dòng khi gõ.")
    print("   - Gõ 'exit' hoặc nhấn [Ctrl + C] 2 lần liên tiếp để thoát.")
    print("="*40 + "\n")

    kb = KeyBindings()

    @kb.add("enter")
    def _(event):
        event.current_buffer.validate_and_handle()

    @kb.add("escape", "enter")
    def _(event):
        event.current_buffer.insert_text("\n")

    prompt_session = PromptSession(multiline=True, key_bindings=kb, erase_when_done=True)
    state.cli_session = prompt_session

    while True:
        try:
            if state.llm_lock.locked():
                await state.llm_lock.acquire()
                state.llm_lock.release()

            with patch_stdout():
                state.prompt_task = asyncio.create_task(
                    prompt_session.prompt_async("\nBạn: ", default=state.saved_prompt_text, handle_sigint=False)
                )
                user_input = await state.prompt_task
                state.saved_prompt_text = ""

            try:
                asyncio.get_running_loop().add_signal_handler(signal.SIGINT, _sigint_handler)
            except NotImplementedError:
                pass

            if not user_input.strip():
                continue

            print(f"\nBạn: {user_input.strip()}")

            if user_input.strip().lower() in ('exit', 'quit'):
                print("👋 Tạm biệt! Đang dọn dẹp hệ thống...")
                try:
                    ngrok.kill()
                except Exception:
                    pass
                os._exit(0)

            await run_chatbot(user_input)

        except (KeyboardInterrupt, EOFError):
            print("\n👋 Tạm biệt!")
            try:
                ngrok.kill()
            except Exception:
                pass
            os._exit(0)

        except asyncio.CancelledError:
            global _cancelled_by_user
            if _cancelled_by_user:
                _cancelled_by_user = False
                state.saved_prompt_text = ""
            continue

        except Exception as e:
            print(f"Lỗi: {e}")


async def main():
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, _sigint_handler)
    except NotImplementedError:
        pass

    asyncio.create_task(tail_mcp_log())

    new_webhook = setup_self_register_webhook()
    if new_webhook:
        print(f"\n✨ AGENT ĐÃ SẴN SÀNG TẠI: {new_webhook}")
    else:
        print("\n⚠️ Cảnh báo: Tự động đăng ký thất bại, cập nhật thủ công nếu cần.")

    print("🚀 AIOps Server đang lắng nghe trên cổng 5000...")
    print("👉 Endpoint 1 (Jenkins): /webhook")
    print("👉 Endpoint 2 (Prometheus): /prometheus-webhook")

    def _run_uvicorn():
        config = uvicorn.Config(app, host="0.0.0.0", port=5000, log_level="warning")
        server = uvicorn.Server(config)

        @contextlib.contextmanager
        def _noop():
            yield
        server.capture_signals = _noop
        server.run()

    threading.Thread(target=_run_uvicorn, daemon=True).start()
    await chat_loop()


if __name__ == "__main__":
    opt_ctx, _ = analyze_system_hardware()
    state.llm = ChatOllama(model="qwen2.5:14b", num_ctx=opt_ctx)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nĐã thoát Chatbot.")
