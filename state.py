import asyncio

# LLM instance — được gán bởi agent.py lúc khởi động
llm = None

# Async lock để đảm bảo chỉ 1 tác vụ AI chạy tại 1 thời điểm
llm_lock = asyncio.Lock()
current_llm_task = ""

# Tham chiếu tới prompt đang chạy của chatbot CLI
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
