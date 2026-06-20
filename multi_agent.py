import asyncio
import json
import re
from typing import TypedDict, Annotated, Literal
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

# Định nghĩa Cấu trúc Dữ liệu cho Graph (State)
class AgentState(TypedDict):
    history: str           # Lịch sử suy luận & Action
    user_prompt: str       # Câu hỏi / Nhiệm vụ gốc của người dùng
    route: str             # "CHAT", "JENKINS", "K8S", "CODE"
    final_answer: str      # Kết quả cuối cùng
    session: any           # Đối tượng ClientSession của MCP để gọi Tool
    llm: any               # Đối tượng LLM truyền vào (ChatOllama)
    step_count: int        # Số bước đếm để tránh lặp vô tận
    stream_output: bool    # In ra console dạng trực tiếp không?
    active_agent: str      # Theo dõi Node đang thực thi để gọi về đúng chỗ
    last_tool_call: str    # Chuỗi chữ ký lệnh trước đó để chống lặp vô tận

# ==========================================
# SYSTEM PROMPTS CHO TỪNG SUB-AGENT
# ==========================================

REACT_FORMAT = """
BẠN CHỈ ĐƯỢC PHẢN HỒI THEO 1 TRONG 2 ĐỊNH DẠNG SAU:

ĐỊNH DẠNG 1 (Khi cần gọi Tool):
Thought: [Suy nghĩ phân tích]
Action: [tên-tool]
Action Input: [JSON]

ĐỊNH DẠNG 2 (CHỈ GỌI KHI ĐÃ TÌM RA LỖI HOẶC HOÀN THÀNH NHIỆM VỤ):
Thought: Tôi đã tìm ra lỗi / hoàn thành xong nhiệm vụ.
Final Answer: [Báo cáo chi tiết cho người dùng]

ĐẶC QUYỀN (HANDOFF):
Nếu bạn phát hiện lỗi thuộc chuyên môn của Agent khác, hãy dùng Tool giả lập sau để chuyển giao quyền:
Action: hand_off
Action Input: {"target_agent": "JENKINS" hoặc "K8S" hoặc "CODE", "reason": "Lý do chuyển giao"}
"""

JENKINS_PROMPT = """Bạn là JENKINS SRE Agent. Nhiệm vụ của bạn là kiểm tra CI/CD, build pipelines.
Danh sách Tools:
- get_build_overview: {"job_name": "tên-job", "build_number": "lastBuild hoặc số"}
- get_jenkins_logs: {"job_name": "tên-job", "build_number": "lastBuild hoặc số", "target_stage": "Tên Stage"}
""" + REACT_FORMAT

K8S_PROMPT = """Bạn là KUBERNETES SRE Agent. Nhiệm vụ của bạn là kiểm tra log app, metrics, và hệ thống K8s.
Danh sách Tools:
- get_app_logs: {"namespace": "tên", "label_selector": "app=tên"}
- check_system_health: {"namespace": "tên"}
- fetch_metrics: {}
- restart_pod: {"pod_name": "tên", "namespace": "tên"}
- rollback: {"deployment_name": "tên", "namespace": "tên"}
- scale_deployment: {"deployment_name": "tên", "replicas": số, "namespace": "tên"}
""" + REACT_FORMAT

CODE_PROMPT = """Bạn là CODE ANALYSIS Agent. Nhiệm vụ của bạn là phân tích file mã nguồn trong repo.
Danh sách Tools:
- list_directory: {"directory_path": "đường-dẫn"}
- read_project_file: {"file_path": "đường-dẫn", "start_line": số, "end_line": số}
- search_in_file: {"file_path": "đường-dẫn", "keyword": "từ-khóa", "context_lines": 5}
""" + REACT_FORMAT


# ==========================================
# CÁC TÁC NHÂN (NODES) CỦA HỆ THỐNG
# ==========================================

async def router_node(state: AgentState):
    """Router Agent: Phân loại sâu hơn vào 4 hướng"""
    if state.get("stream_output", False):
        print("\n[Router Agent] Đang phân loại công việc...")
        
    prompt = f"""Phân loại nhiệm vụ sau thành 1 trong 4 loại:
1. 'CHAT': Hỏi han xã giao, xin chào, không liên quan kỹ thuật.
2. 'JENKINS': Nhiệm vụ CI/CD, lỗi build pipeline, test, scan, webhook báo Jenkins.
3. 'K8S': Nhiệm vụ Kubernetes, webhook Prometheus, pod bị crash, deploy, rollback.
4. 'CODE': Nhiệm vụ chỉ định rõ việc đọc file code, xem repo, kiểm tra source code.
Lưu ý: Nếu lỗi chưa rõ ràng nhưng có nhắc đến 'job' hoặc 'pipeline', chọn JENKINS.
Yêu cầu: {state['user_prompt']}
Chỉ trả về đúng 1 từ: CHAT, JENKINS, K8S, hoặc CODE."""
    
    res = await state["llm"].ainvoke(prompt)
    content = res.content.upper()
    
    route = "CHAT"
    if "JENKINS" in content: route = "JENKINS"
    elif "K8S" in content: route = "K8S"
    elif "CODE" in content: route = "CODE"
    
    if state.get("stream_output", False):
        print(f"[Router Agent] Chuyển hướng tới: {route} Agent")
        
    return {"route": route, "step_count": 0, "history": "", "active_agent": route}


async def chat_node(state: AgentState):
    if state.get("stream_output", False):
        print("[Chat Agent] Đang trả lời...")
    prompt = f"Bạn là AI SRE Chatbot. Hãy trả lời thân thiện:\n{state['user_prompt']}"
    res = await state["llm"].ainvoke(prompt)
    return {"final_answer": res.content}


async def _think_impl(state: AgentState, system_prompt: str, agent_name: str):
    """Logic ReAct dùng chung cho cả 3 Sub-Agents"""
    prompt = f"{system_prompt}\n\nLịch sử:\n{state.get('history', '')}\n\nNhiệm vụ: {state['user_prompt']}\n\nHãy suy nghĩ và đưa ra hành động (Action) hoặc kết luận (Final Answer)."
    
    async def show_thinking():
        try:
            seconds = 0
            while True:
                await asyncio.sleep(15)
                seconds += 15
                if state.get("stream_output", False):
                    print(f"⏳ (Đã đợi {seconds}s) {agent_name} Agent đang suy nghĩ...")
        except asyncio.CancelledError:
            pass

    think_task = asyncio.create_task(show_thinking())
    try:
        res = await state["llm"].ainvoke(prompt)
        response = res.content
    finally:
        think_task.cancel()
        
    # Cắt bỏ phần nội dung ảo giác (hallucination)
    input_match = re.search(r"(Action Input:\s*\{.*?\})", response, re.DOTALL)
    if input_match:
        response = response[:input_match.end()].strip()
        
    if state.get("stream_output", False):
        print(f"\n🤖 {agent_name} Agent Quyết định:\n{response}\n")

    new_history = state.get('history', '') + f"\n{response}\n"
    return {"history": new_history, "final_answer": response, "step_count": state["step_count"] + 1, "active_agent": agent_name}

# 3 Sub-Agents Nodes
async def jenkins_think_node(state: AgentState): return await _think_impl(state, JENKINS_PROMPT, "JENKINS")
async def k8s_think_node(state: AgentState): return await _think_impl(state, K8S_PROMPT, "K8S")
async def code_think_node(state: AgentState): return await _think_impl(state, CODE_PROMPT, "CODE")


async def sre_tool_node(state: AgentState):
    """Executor dùng chung: Gọi Tool và trả kết quả về đúng Agent đang chạy"""
    response = state["final_answer"]
    action_match = re.search(r"Action:\s*([a-zA-Z0-9_]+)", response)
    input_match = re.search(r"Action Input:\s*(\{.*?\})", response, re.DOTALL)
    
    observation = ""
    current_call_signature = ""
    if action_match and input_match:
        tool_name = action_match.group(1).strip()
        try:
            raw_json = re.sub(r'```json\s*|```', '', input_match.group(1).strip())
            tool_args = json.loads(raw_json)
            
            # CƠ CHẾ HANDOFF AGENT
            if tool_name == "hand_off":
                target_agent = tool_args.get("target_agent", "")
                reason = tool_args.get("reason", "")
                
                if target_agent == state.get("active_agent"):
                    observation = f"LỖI HỆ THỐNG: Bạn hiện tại ĐANG LÀ {target_agent} Agent! Bạn không thể tự chuyển giao quyền cho chính mình. Hãy sử dụng Tool khác hoặc đưa ra Final Answer."
                    if state.get("stream_output", False):
                        print("⚠️ Phát hiện AI tự Handoff cho chính mình! Đang chặn lại...")
                elif target_agent in ["JENKINS", "K8S", "CODE"]:
                    state["active_agent"] = target_agent
                    observation = f"✅ Đã chuyển giao quyền điều khiển thành công sang {target_agent} Agent! Lời nhắn: {reason}"
                    if state.get("stream_output", False):
                        print(f"\n🤝 [HANDOFF] Đã chuyển quyền điều khiển sang {target_agent} Agent!")
                else:
                    observation = f"LỖI: Agent đích '{target_agent}' không hợp lệ. Chỉ chấp nhận: JENKINS, K8S, CODE."
            else:
                # Phát hiện lặp (Loop Detection)
                current_call_signature = f"{tool_name}|{json.dumps(tool_args, sort_keys=True)}"
                if state.get("last_tool_call") == current_call_signature:
                    observation = "LỖI HỆ THỐNG: BẠN VỪA GỌI CHÍNH XÁC LỆNH NÀY Ở BƯỚC TRƯỚC! KẾT QUẢ VẪN NHƯ CŨ. VUI LÒNG KHÔNG LẶP LẠI! Hãy gọi lệnh khác hoặc dùng Final Answer để kết thúc."
                    if state.get("stream_output", False):
                        print("⚠️ Phát hiện AI bị kẹt vòng lặp lệnh cũ! Đang ép bẻ lái...")
                else:
                    if state.get("stream_output", False):
                        print(f"🛠️ Đang gọi Tool: [{tool_name}]...")
                    
                session = state["session"]
                tool_result = await session.call_tool(tool_name, arguments=tool_args)
                observation = tool_result.content[0].text
                
                if len(observation) > 8000:
                    observation = observation[:8000] + "\n...[CẮT BỚT]..."
                
                if state.get("stream_output", False):
                    print(f"✅ Đã có bằng chứng! (Observation: {len(observation)} ký tự).")
                
        except Exception as e:
            observation = f"LỖI GỌI TOOL: {repr(e)}"
            if state.get("stream_output", False): print(f"⚠️ {observation}")
    else:
        observation = "Không tìm thấy định dạng Action / Action Input hợp lệ."
        
    new_history = state.get('history', '') + f"Observation: {observation}\n"
    
    MAX_HISTORY_CHARS = 16000
    if len(new_history) > MAX_HISTORY_CHARS:
        new_history = "...[LỊCH SỬ BỊ XÓA BỚT]...\n" + new_history[-MAX_HISTORY_CHARS:]
        
    return {"history": new_history, "last_tool_call": current_call_signature, "active_agent": state.get("active_agent", "")}


# ==========================================
# LUỒNG ĐIỀU HƯỚNG CỦA ĐỒ THỊ (EDGES)
# ==========================================

def route_after_router(state: AgentState) -> Literal["chat_node", "jenkins_think_node", "k8s_think_node", "code_think_node"]:
    if state["route"] == "CHAT": return "chat_node"
    if state["route"] == "JENKINS": return "jenkins_think_node"
    if state["route"] == "K8S": return "k8s_think_node"
    return "code_think_node"

def route_after_think(state: AgentState) -> Literal["sre_tool_node", "END"]:
    if "Action:" in state["final_answer"] and "Action Input:" in state["final_answer"]:
        return "sre_tool_node"
    if "Final Answer:" in state["final_answer"] or state["step_count"] >= 10:
        return "END"
    return "sre_tool_node"

def route_after_tool(state: AgentState) -> Literal["jenkins_think_node", "k8s_think_node", "code_think_node"]:
    """Trả về lại đúng Agent đã gọi lệnh"""
    if state["active_agent"] == "JENKINS": return "jenkins_think_node"
    if state["active_agent"] == "K8S": return "k8s_think_node"
    return "code_think_node"

# ==========================================
# KHỞI TẠO ĐỒ THỊ
# ==========================================

def build_multi_agent_graph():
    graph_builder = StateGraph(AgentState)
    
    graph_builder.add_node("router_node", router_node)
    graph_builder.add_node("chat_node", chat_node)
    graph_builder.add_node("jenkins_think_node", jenkins_think_node)
    graph_builder.add_node("k8s_think_node", k8s_think_node)
    graph_builder.add_node("code_think_node", code_think_node)
    graph_builder.add_node("sre_tool_node", sre_tool_node)
    
    graph_builder.set_entry_point("router_node")
    graph_builder.add_conditional_edges("router_node", route_after_router)
    graph_builder.add_edge("chat_node", END)
    
    # Từ Think rẽ sang Tool hoặc Kết thúc
    for node in ["jenkins_think_node", "k8s_think_node", "code_think_node"]:
        graph_builder.add_conditional_edges(node, route_after_think, {
            "END": END,
            "sre_tool_node": "sre_tool_node"
        })
        
    # Từ Tool rẽ ngược về đúng Think Node
    graph_builder.add_conditional_edges("sre_tool_node", route_after_tool)
    
    return graph_builder.compile()

multi_agent_graph = build_multi_agent_graph()

async def process_with_multi_agent(user_prompt: str, session, llm, stream_output: bool = True) -> str:
    """Hàm chạy LangGraph Multi-Agent, thay thế hoàn toàn vòng lặp ReAct cũ."""
    initial_state = {
        "user_prompt": user_prompt,
        "session": session,
        "llm": llm,
        "stream_output": stream_output,
        "history": "",
        "step_count": 0
    }
    
    try:
        final_state = await multi_agent_graph.ainvoke(initial_state)
        
        if "Final Answer:" in final_state.get("final_answer", ""):
            return final_state["final_answer"].split("Final Answer:")[1].strip()
        else:
            return final_state.get("final_answer", "")
    except Exception as e:
        return f"Lỗi Multi-Agent Graph: {str(e)}"
