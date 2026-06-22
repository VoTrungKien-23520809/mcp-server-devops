import re
import time
import requests
from . import mcp, session, logger, JENKINS_URL, JENKINS_USER, JENKINS_TOKEN


@mcp.tool()
def ping_server() -> str:
    """Check MCP Server connection status."""
    logger.info("Ping tool được gọi.")
    return "Pong! The DevOps MCP Server is fully operational and secured."


@mcp.tool()
def get_build_overview(job_name: str, build_number: str = "lastBuild") -> str:
    """Get an overview of all stages in a Jenkins build, including their status and duration."""
    logger.info(f"Đang kéo tổng quan build cho job: {job_name}, build: {build_number}")

    if not JENKINS_URL or not JENKINS_USER or not JENKINS_TOKEN:
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
            duration_sec = stage.get("durationMillis", 0) / 1000.0
            overview += f"| {name} | {status} | {duration_sec:.2f}s |\n"

        return overview
    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi khi gọi API wfapi: {str(e)}")
        return f"Error fetching build overview: {str(e)}"


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
    MAX_LOG_CHARS = 8000

    # Layer 1: wfapi — log chính xác theo từng node/step
    if target_stage:
        try:
            wfapi_url = f"{base_url}/job/{job_name}/{build_number}/wfapi/describe"
            stages = session.get(wfapi_url, auth=auth, timeout=10).json().get("stages", [])

            target_lower = target_stage.strip().lower()
            matched_stage = next(
                (s for s in stages if s.get("name", "").strip().lower() == target_lower), None
            ) or next(
                (s for s in stages if target_lower in s.get("name", "").strip().lower()), None
            )

            if matched_stage:
                stage_id = matched_stage["id"]
                stage_name = matched_stage.get("name", target_stage)
                stage_status = matched_stage.get("status", "UNKNOWN")

                node_desc_url = f"{base_url}/job/{job_name}/{build_number}/execution/node/{stage_id}/wfapi/describe"
                flow_nodes = session.get(node_desc_url, auth=auth, timeout=10).json().get("stageFlowNodes", [])

                if flow_nodes:
                    parts = [f"=== LOG STAGE: '{stage_name}' | Status: {stage_status} ==="]
                    total_chars = len(parts[0])

                    for node in flow_nodes:
                        log_href = node.get("_links", {}).get("log", {}).get("href", "")
                        if not log_href:
                            continue
                        log_url = f"{base_url}{log_href}" if log_href.startswith("/") else log_href
                        node_text = session.get(log_url, auth=auth, timeout=10).json().get("text", "").strip()
                        if not node_text:
                            continue

                        node_id = node.get("id")
                        node_name = node.get("name", "Step")
                        node_status = node.get("status", "")
                        header = f"\n--- [{node_status}] {node_name} (node {node_id}) ---\n"
                        chunk = header + node_text

                        if total_chars + len(chunk) > MAX_LOG_CHARS:
                            remaining = MAX_LOG_CHARS - total_chars
                            if remaining > len(header) + 100:
                                parts.append(chunk[:remaining] + "\n...[CẮT BỚT]...")
                            parts.append("\n⚠️ Log đã đạt giới hạn. Các step sau bị bỏ qua.")
                            break

                        parts.append(chunk)
                        total_chars += len(chunk)

                    logger.info(f"✅ Layer 1 thành công: stage='{stage_name}', {total_chars} ký tự.")
                    return "\n".join(parts)
                else:
                    logger.warning(f"Stage '{stage_name}' không có stageFlowNodes → sang Layer 2.")
            else:
                logger.warning(f"Không tìm thấy stage '{target_stage}' trong wfapi → sang Layer 2.")

        except Exception as e:
            logger.warning(f"Layer 1 thất bại ({e}) → sang Layer 2.")

    # Layer 2 & 3: raw console log
    try:
        raw_url = f"{base_url}/job/{job_name}/{build_number}/consoleText"
        raw_logs = session.get(raw_url, auth=auth, timeout=15).text

        if target_stage:
            pattern = re.compile(
                rf"\[Pipeline\] \{{ \({re.escape(target_stage)}\)(.*?)(?=\[Pipeline\] \{{ \(|\Z)",
                re.DOTALL | re.IGNORECASE,
            )
            match = pattern.search(raw_logs)
            if match:
                stage_log = match.group(1).strip()
                if len(stage_log) > MAX_LOG_CHARS:
                    stage_log = stage_log[:MAX_LOG_CHARS] + "\n...[CẮT BỚT - phần cuối stage bị lược bỏ]..."
                logger.info(f"✅ Layer 2 thành công: stage='{target_stage}' qua regex.")
                return f"--- LOG STAGE (regex): {target_stage} ---\n{stage_log}"
            else:
                logger.warning(f"Layer 2 không tìm thấy stage '{target_stage}' → trả về raw log.")

        # Layer 3: cắt từ đầu để bảo toàn error message
        if len(raw_logs) > MAX_LOG_CHARS:
            logger.warning("Layer 3: Raw log quá dài, cắt từ đầu.")
            return raw_logs[:MAX_LOG_CHARS] + "\n...[CẮT BỚT - phần sau bị lược bỏ để bảo toàn thông tin lỗi]..."

        logger.info("✅ Layer 3: Trả về toàn bộ raw log.")
        return raw_logs

    except requests.exceptions.RequestException as e:
        logger.error(f"Lỗi kéo log Jenkins: {e}")
        return f"Error fetching logs from Jenkins: {str(e)}"


@mcp.tool()
def trigger_jenkins_and_wait(job_name: str) -> str:
    """Kích hoạt Jenkins build, đợi chạy xong và trả về Log của bản build đó."""
    logger.info(f"🚀 AI ĐANG HÀNH ĐỘNG: Yêu cầu kích hoạt Jenkins Job: {job_name}")

    if not JENKINS_URL or not JENKINS_USER or not JENKINS_TOKEN:
        return "Error: Thiếu cấu hình Jenkins trong .env"

    base_url = JENKINS_URL.rstrip('/')

    try:
        res = session.post(f"{base_url}/job/{job_name}/build", auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10)
        res.raise_for_status()
        logger.info("✅ Kích hoạt Build thành công! AI đang đợi Jenkins chạy...")

        time.sleep(10)

        info_url = f"{base_url}/job/{job_name}/lastBuild/api/json"
        while True:
            info_data = session.get(info_url, auth=(JENKINS_USER, JENKINS_TOKEN), timeout=10).json()
            if not info_data.get('building', False):
                result_status = info_data.get('result', 'UNKNOWN')
                logger.info(f"🎯 Jenkins đã chạy xong với trạng thái: {result_status}")
                break
            logger.info("⏳ Jenkins vẫn đang chạy... AI tiếp tục đợi thêm 10 giây...")
            time.sleep(10)

        log_content = get_jenkins_logs(job_name, "lastBuild")
        return f"Trạng thái Build: {result_status}\n\n=== LOG CHI TIẾT ===\n{log_content}"

    except Exception as e:
        logger.error(f"❌ Lỗi khi điều khiển Jenkins: {str(e)}")
        return f"Lỗi không thể chạy Jenkins: {str(e)}"
