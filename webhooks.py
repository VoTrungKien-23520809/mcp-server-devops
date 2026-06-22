import asyncio
import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks, Request
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import state
from multi_agent import process_with_multi_agent
from notifications import send_discord_alert

app = FastAPI()


@asynccontextmanager
async def _mcp_client(server_params):
    """Kết nối tới MCP Server qua stdio và hiển thị log nội bộ của nó."""
    r, w = os.pipe()
    wf = os.fdopen(w, "w")

    async def _pipe_reader():
        f = os.fdopen(r, "r")
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, f.readline)
                if not line:
                    break
                if line.strip():
                    print(f"⚙️ [MCP] {line.strip()}")
            except Exception:
                break

    reader = asyncio.create_task(_pipe_reader())
    try:
        async with stdio_client(server_params, errlog=wf) as (read, write):
            yield (read, write)
    finally:
        try:
            wf.close()
        except Exception:
            pass
        await asyncio.sleep(0.1)
        reader.cancel()


async def _run_agent(task: str, mode_label: str) -> str:
    """Khởi tạo MCP session và chạy multi-agent với nhiệm vụ cho sẵn."""
    server_params = StdioServerParameters(command="python", args=["main.py"])
    async with _mcp_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()
            print(f"✅ Đã kết nối MCP Server ({mode_label})!")
            return await process_with_multi_agent(task, mcp_session, state.llm, stream_output=True)


# ==========================================
# CÁC TÁC VỤ ĐIỀU TRA AI
# ==========================================

async def run_investigation(job_name: str):
    print(f"\n🕵️ AI THÁM TỬ ĐÃ THỨC DẬY! Bắt đầu điều tra sự cố cho Job: {job_name}")
    try:
        task = f"Nhiệm vụ: Phân tích nguyên nhân lỗi build của job {job_name}. Hãy tìm stage lỗi và log lỗi tương ứng để phân tích."
        answer = await _run_agent(task, "CI/CD Mode")
        print("\n" + "="*40 + "\n👉 BÁO CÁO PHÂN TÍCH HỆ THỐNG (AI SRE REPORT)\n" + "="*40)
        print(answer)
        print("="*40)
        send_discord_alert(f"🚨 **BÁO CÁO JENKINS TỪ AI SRE** 🚨\n\n{answer}")
    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng: {e}")


async def run_metrics_investigation(alert_name: str, alert_desc: str):
    print(f"\n🚨 AI THÁM TỬ ĐÃ THỨC DẬY! Điều tra cảnh báo hạ tầng: {alert_name}")
    try:
        task = f"Nhiệm vụ: Phân tích cảnh báo Prometheus: {alert_name} - {alert_desc}. Hãy kiểm tra pod log hoặc hệ thống K8s tương ứng để tìm nguyên nhân và khắc phục."
        answer = await _run_agent(task, "Infra Mode")
        print("\n" + "="*40 + "\n👉 BÁO CÁO TỪ AI SRE\n" + "="*40)
        print(answer)
        print("="*40)
        send_discord_alert(f"🚨 **BÁO CÁO SỰ CỐ TỪ AI SRE** 🚨\n\n{answer}")
    except Exception as e:
        print(f"❌ Lỗi: {e}")


async def run_success_report(job_name: str):
    print(f"\n✅ AI ĐÃ THỨC DẬY! Tổng hợp báo cáo sau khi Deploy: {job_name}")
    try:
        task = f"Nhiệm vụ: Viết báo cáo sức khỏe hệ thống sau khi job Jenkins {job_name} deploy thành công. (Gợi ý: Kiểm tra K8s health và metrics)."
        answer = await _run_agent(task, "Report Mode")
        print("\n" + "="*40 + "\n👉 AI SRE REPORT\n" + "="*40)
        print(answer)
        print("="*40)
        send_discord_alert(f"✅ **BÁO CÁO THÀNH CÔNG TỪ AI SRE** ✅\n\n{answer}")
    except Exception as e:
        print(f"❌ Lỗi: {e}")
        traceback.print_exc()


async def run_smart_cd_approval(k8s_dir: str = "weather-app/k8s"):
    print(f"\n🛑 [SMART CD] AI ĐANG THẨM ĐỊNH RỦI RO TRIỂN KHAI: {k8s_dir}")
    try:
        task = f"Nhiệm vụ: Thẩm định rủi ro Smart CD. Hãy kiểm tra file cấu hình deployment trong thư mục {k8s_dir} xem có rủi ro gì không (ví dụ: dùng latest tag). Đưa ra Quyết định APPROVE (Cho phép) hoặc REJECT (Từ chối)."
        answer = await _run_agent(task, "Smart CD Mode")
        print("\n" + "="*40 + "\n👉 BÁO CÁO THẨM ĐỊNH (AI GATEKEEPER)\n" + "="*40)
        print(answer)
        print("="*40)
        send_discord_alert(f"🛡️ **SMART CD: YÊU CẦU PHÊ DUYỆT DEPLOY** 🛡️\n\n{answer}")
    except Exception as e:
        print(f"❌ Lỗi Smart CD: {e}")


async def run_chatbot(user_prompt: str):
    await state.acquire_llm_lock("Tương tác người dùng (Chatbot)")
    try:
        task = user_prompt
        answer = await _run_agent(task, "Chatbot Mode")
        print(f"🤖 Chatbot:\n{answer}\n")
    except Exception as e:
        print(f"❌ Lỗi Chatbot: {e}")
    finally:
        print("-" * 60)
        state.release_llm_lock()


# ==========================================
# WRAPPER FUNCTIONS (LẤY LOCK TRƯỚC KHI CHẠY)
# ==========================================

async def _wrap(coro, lock_name: str, done_msg: str):
    await state.acquire_llm_lock(lock_name)
    try:
        await coro
    finally:
        print(f"✅ {done_msg} Nhả cờ khóa.")
        print("-" * 60)
        state.release_llm_lock()


async def run_investigation_wrapper(job_name):
    await _wrap(run_investigation(job_name), f"Điều tra lỗi Jenkins (Job: {job_name})", "AI đã điều tra Jenkins xong.")

async def run_metrics_investigation_wrapper(alert_name, alert_desc):
    await _wrap(run_metrics_investigation(alert_name, alert_desc), f"Điều tra Hạ tầng (Alert: {alert_name})", "AI đã điều tra Hạ tầng xong.")

async def run_success_report_wrapper(job_name):
    await _wrap(run_success_report(job_name), f"Báo cáo Deploy (Job: {job_name})", "AI đã báo cáo Deploy xong.")

async def run_smart_cd_wrapper(tf_dir):
    await _wrap(run_smart_cd_approval(tf_dir), f"Thẩm định Smart CD ({tf_dir})", "AI đã thẩm định Smart CD xong.")


# ==========================================
# FASTAPI WEBHOOK ENDPOINTS
# ==========================================

@app.post("/webhook")
async def jenkins_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    job_name = data.get("job_name", "weather-app-pipeline")
    status = data.get("status")
    k8s_dir = data.get("k8s_dir", "weather-app/k8s")

    print(f"\n📥 [JENKINS WEBHOOK] Nhận tín hiệu: Job '{job_name}' - Trạng thái: {status}")

    if status == "FAILURE":
        background_tasks.add_task(run_investigation_wrapper, job_name)
        return {"message": "AI Agent đang xếp lịch điều tra lỗi Build!"}
    elif status == "SUCCESS":
        background_tasks.add_task(run_success_report_wrapper, job_name)
        return {"message": "AI Agent đang xếp lịch tổng hợp báo cáo sau khi Deploy thành công!"}
    elif status == "PENDING_APPROVAL":
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
            background_tasks.add_task(run_metrics_investigation_wrapper, alert_name, alert_desc)
            return {"message": "AI đang xếp lịch điều tra quá tải K3s!"}
        else:
            print(f"\n💚 [PROMETHEUS WEBHOOK] Cảnh báo {alert_name} đã được giải quyết.")
            return {"message": "Hệ thống K3s đã xanh."}

    except Exception as e:
        return {"message": f"Lỗi xử lý webhook: {str(e)}"}
