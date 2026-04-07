import asyncio
import os
import sys
import json
import re
import requests
import uvicorn
from fastapi import FastAPI, BackgroundTasks, Request
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
# BỘ NÃO THÁM TỬ (REACT LOOP)
# ==========================================
async def run_investigation(job_name: str):
    print(f"\n🕵️ AI THÁM TỬ ĐÃ THỨC DẬY! Bắt đầu điều tra sự cố cho Job: {job_name}")

    server_params = StdioServerParameters(
        command="python",
        args=["main.py"],
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✅ Đã kết nối thành công tới MCP Server!")

                SYSTEM_PROMPT = """Bạn là một Kỹ sư SRE cấp cao. 
QUY TẮC ĐIỀU TRA (REACT LOOP):
1. THOUGHT: Suy nghĩ phải NGẮN GỌN (tối đa 4 câu).
2. ACTION: Bạn CHỈ ĐƯỢC GỌI 1 TOOL DUY NHẤT trong mỗi vòng lặp. Phải đợi có kết quả rồi mới gọi tool tiếp theo.

Danh sách Tools:
- get_jenkins_logs: {"job_name": "tên-job"}
- get_app_logs: {"namespace": "tên-namespace", "label_selector": "app=tên-app"}
- get_k8s_nodes: {}
- fetch_metrics: {}
- list_directory: {"directory_path": "đường-dẫn"}
- read_project_file: {"file_path": "đường-dẫn-file"}

BẠN CHỈ ĐƯỢC PHÉP TRẢ LỜI THEO 1 TRONG 2 ĐỊNH DẠNG SAU:

ĐỊNH DẠNG 1 (Khi cần gọi Tool):
Thought: [Suy nghĩ ngắn gọn xem bước tiếp theo làm gì]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (CHỈ GỌI KHI ĐÃ CÓ ĐỦ DỮ LIỆU TỪ JENKINS, METRICS VÀ K3S LOGS):
Thought: Tôi đã thu thập đủ dữ liệu thực tế và sẵn sàng báo cáo.
Final Answer:
[BẠN BẮT BUỘC PHẢI VIẾT BÁO CÁO SRE TOÀN DIỆN BẰNG TIẾNG VIỆT, SỬ DỤNG MARKDOWN CHUYÊN NGHIỆP VỚI CẤU TRÚC SAU:]
#### 1. Tình trạng Hạ Tầng & CI/CD:
- (Phân tích chi tiết log lỗi từ Jenkins).
#### 2. Đánh giá Hiệu năng:
- (Nêu rõ % CPU, RAM và đánh giá mức độ tải).
#### 3. Tình trạng Ứng Dụng:
- (Trích xuất và phân tích CHUYÊN SÂU các cảnh báo hoặc Exception từ App Logs).
#### 4. Giải pháp & Lệnh thực thi:
- (Đưa ra lời khuyên cụ thể, kèm theo đoạn code hoặc câu lệnh bash/kubectl cần thiết).
"""

                USER_TASK = f"""
Nhiệm vụ điều tra bắt buộc:
1. Gọi get_jenkins_logs (job_name: '{job_name}') để ĐỌC LOG của bản build vừa thất bại. TUYỆT ĐỐI KHÔNG kích hoạt build mới.
2. Đợi có kết quả log, gọi tiếp fetch_metrics.
3. BẮT BUỘC gọi get_app_logs (namespace 'default', app 'meteo-hist').

RẼ NHÁNH ĐIỀU TRA (TƯ DUY ĐỘNG - KHÔNG ĐOÁN MÒ):
- Nếu Jenkins báo SUCCESS: Xuất Final Answer tổng hợp tình hình.
- Nếu Jenkins báo FAILURE: Đọc kỹ log Jenkins để tìm manh mối. Dựa vào manh mối, tự suy luận xem cần dùng `list_directory` và `read_project_file` để đọc file nào (VD: Dockerfile, requirements.txt, .py). 
Chỉ khi TỰ MÌNH tìm thấy dòng code sai sót thì mới được xuất Final Answer.

⚠️ LƯU Ý SỐNG CÒN VỀ ĐƯỜNG DẪN (PATH):
Khi dùng tool đọc file, bạn đang đứng ở thư mục gốc của Repo (./). TUYỆT ĐỐI KHÔNG sử dụng đường dẫn tuyệt đối lấy từ log Jenkins (như /var/lib/jenkins/...). Bạn CHỈ ĐƯỢC phép dùng đường dẫn tương đối để tìm file (Ví dụ: 'weather-app/Dockerfile', 'weather-app/requirements.txt').
"""

                print("\n🧠 Đã tải Hệ điều hành Thám Tử (ReAct) cho Qwen 2.5...")
                print(f"🚀 Bắt đầu giao việc cho AI điều tra lỗi của {job_name}...")

                history = ""
                max_steps = 10 
                
                for step in range(max_steps):
                    print(f"\n--- [Vòng lặp điều tra thứ {step + 1}/{max_steps}] ---")
                    prompt = f"{SYSTEM_PROMPT}\n\nLịch sử điều tra:\n{history}\n\nNhiệm vụ của bạn: {USER_TASK}\n\nBước tiếp theo của bạn là gì?"
                    response = llm.invoke(prompt)
                    print(f"🤖 AI Suy nghĩ & Quyết định:\n{response}\n")
                    
                    if "Final Answer:" in response:
                        final_report = response.split("Final Answer:")[1].strip()
                        print("\n" + "="*40)
                        print("👉 BÁO CÁO PHÂN TÍCH HỆ THỐNG (AI SRE REPORT)")
                        print("="*40)
                        print(final_report)
                        print("="*40)
                        
                        alert_msg = f"🚨 **BÁO CÁO TỪ AI SRE** 🚨\n\n{final_report}"
                        send_discord_alert(alert_msg)
                        break
                        
                    action_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response)
                    input_match = re.search(r"Action Input:\s*(\{.*?\})", response, re.DOTALL)
                    
                    if action_match and input_match:
                        tool_name = action_match.group(1).strip()
                        raw_json = input_match.group(1).strip()
                        raw_json = re.sub(r'```json\s*', '', raw_json)
                        raw_json = re.sub(r'```', '', raw_json)
                        
                        try:
                            tool_args = json.loads(raw_json)
                            print(f"🛠️ MCP Server đang thực thi Tool: [{tool_name}] với tham số {tool_args}")
                            
                            tool_result = await session.call_tool(tool_name, arguments=tool_args)
                            observation = tool_result.content[0].text
                            
                            if len(observation) > 4000:
                                observation = observation[:4000] + "\n...[ĐÃ CẮT BỚT VÌ LOG QUÁ DÀI]..."
                                
                            print(f"✅ Đã có bằng chứng! (Observation: {len(observation)} ký tự). Trả về cho AI phân tích...")
                            history += f"\nThought: {response}\nObservation: {observation}\n"
                            
                        except json.JSONDecodeError:
                            print("⚠️ AI xuất sai định dạng JSON! Bắt nó thử lại...")
                            history += f"\nThought: {response}\nObservation: LỖI: Action Input không phải JSON hợp lệ. Hãy format lại cho chuẩn!\n"
                        except Exception as e:
                            print(f"⚠️ Lỗi máy chủ khi gọi Tool {tool_name}: {e}")
                            history += f"\nThought: {response}\nObservation: LỖI KHI GỌI TOOL: {str(e)}. Hãy thử cách khác.\n"
                    else:
                        print("⚠️ AI đang 'ngáo', không tuân thủ định dạng. Ép nó trả lời lại...")
                        history += f"\nThought: {response}\nObservation: LỖI: Bạn BẮT BUỘC phải dùng từ khóa 'Action:' và 'Action Input:' hoặc 'Final Answer:'. Hãy làm lại ngay!\n"

                else:
                    print("⚠️ AI đã chạy hết 10 vòng lặp mà vẫn chưa tìm ra nguyên nhân!")

    except Exception as e:
        print(f"❌ Lỗi nghiêm trọng: {e}")

# ==========================================
# CỔNG NHẬN TÍN HIỆU TỪ JENKINS (WEBHOOK)
# ==========================================
is_investigating = False  # Cờ đánh dấu AI đang bận

async def run_investigation_wrapper(job_name):
    """Hàm bọc để nhả cờ khóa sau khi AI điều tra xong"""
    global is_investigating
    try:
        await run_investigation(job_name)
    finally:
        is_investigating = False
        print("✅ AI đã điều tra xong. Mở khóa Webhook cho các lần sau.")

@app.post("/webhook")
async def jenkins_webhook(request: Request, background_tasks: BackgroundTasks):
    global is_investigating
    data = await request.json()
    job_name = data.get("job_name", "weather-app-pipeline")
    status = data.get("status")

    print(f"\n📥 [WEBHOOK] Nhận tín hiệu từ Jenkins: Job '{job_name}' - Trạng thái: {status}")

    if status == "FAILURE":
        if is_investigating:
            print("🛑 AI đang bận điều tra một vụ án rồi, bỏ qua Webhook bị spam này!")
            return {"message": "AI đang bận, bỏ qua."}
            
        print("🚨 Phát hiện lỗi! Đang khóa Webhook và đánh thức AI chạy ngầm...")
        is_investigating = True
        background_tasks.add_task(run_investigation_wrapper, job_name)
        return {"message": "AI Agent đã tiếp nhận yêu cầu và đang tiến hành điều tra!"}
    
    return {"message": "Hệ thống xanh, AI tiếp tục ngủ ngon."}

if __name__ == "__main__":
    print("🚀 AIOps Server đang lắng nghe trên cổng 5000...")
    uvicorn.run(app, host="0.0.0.0", port=5000)