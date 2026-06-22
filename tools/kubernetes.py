import subprocess
from . import mcp, logger, _run_ssh_kubectl, K8S_NAMESPACE_RE, K8S_LABEL_SELECTOR_RE


@mcp.tool()
def get_k8s_nodes() -> str:
    """Retrieve the current status of all nodes in the K3s cluster."""
    try:
        result = _run_ssh_kubectl(["get", "nodes", "-o", "wide"], timeout=15)
        return f"Dữ liệu từ Cluster:\n{result.stdout.strip()}"
    except Exception as e:
        return f"Lỗi kết nối SSH tới Cluster: {str(e)}"


@mcp.tool()
def get_app_logs(namespace: str = "default", label_selector: str = "app=weather-app") -> str:
    """Fetch the last 50 lines of logs from a specific application pod in Kubernetes."""
    logger.info(f"🔍 Đang kéo log của ứng dụng có nhãn {label_selector} trong namespace '{namespace}'...")
    try:
        if not K8S_NAMESPACE_RE.fullmatch(namespace):
            return "Invalid namespace format."
        if not K8S_LABEL_SELECTOR_RE.fullmatch(label_selector):
            return "Invalid label selector format. Use key=value."

        result = _run_ssh_kubectl(["logs", "-l", label_selector, "-n", namespace, "--tail=50"], timeout=15)
        logs = result.stdout.strip()

        if not logs:
            return "Không có log nào được sinh ra hoặc không tìm thấy pod nào khớp với nhãn này."

        logger.info("✅ Đã lấy được log ứng dụng thành công!")
        return logs

    except Exception as e:
        logger.error(f"❌ Lỗi khi lấy log ứng dụng: {str(e)}")
        return f"Lỗi không thể lấy log ứng dụng: {str(e)}"


@mcp.tool()
def check_system_health(namespace: str = "default") -> str:
    """Kiểm tra tổng quan sức khỏe của các Pods trong K3s."""
    logger.info(f"🏥 AI đang kiểm tra sức khỏe K8s (namespace: {namespace})")
    try:
        result = _run_ssh_kubectl(["get", "pods", "-n", namespace, "-o", "wide"])
        lines = result.stdout.strip().split('\n')

        if len(lines) <= 1:
            return f"⚠️ Không tìm thấy Pod nào trong '{namespace}'."

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


@mcp.tool()
def restart_pod(pod_name: str, namespace: str = "default") -> str:
    """
    Khởi động lại một Pod.
    CẢNH BÁO: CHỈ DÙNG khi Pod bị treo ngẫu nhiên.
    TUYỆT ĐỐI CẤM SỬ DỤNG nếu Pod đang ở trạng thái CrashLoopBackOff, Error, ErrImagePull,
    hoặc ImagePullBackOff. Thay vào đó hãy dùng lệnh rollback!
    """
    logger.info(f"🔄 AI đang RESTART Pod: {pod_name}")
    try:
        result = _run_ssh_kubectl(["delete", "pod", pod_name, "-n", namespace])
        return f"✅ Đã gửi lệnh xóa Pod '{pod_name}' thành công.\nLog: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi restart Pod: {e.stderr}"


@mcp.tool()
def scale_deployment(deployment_name: str, replicas: int, namespace: str = "default") -> str:
    """Tăng/Giảm số lượng Pods của một Deployment (Tối đa 5)."""
    logger.info(f"⚖️ AI đang SCALE Deployment: {deployment_name} -> {replicas}")
    if replicas > 5 or replicas < 1:
        return "❌ TỪ CHỐI LỆNH: Replicas phải nằm trong khoảng từ 1 đến 5."
    try:
        result = _run_ssh_kubectl(
            ["scale", "deployment", deployment_name, f"--replicas={replicas}", "-n", namespace]
        )
        return f"✅ Đã scale Deployment '{deployment_name}' lên {replicas} thành công.\nLog: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi scale: {e.stderr}"


@mcp.tool()
def rollback(deployment_name: str, namespace: str = "default") -> str:
    """
    Khôi phục (Undo/Rollback) Deployment về phiên bản hoạt động trước nếu phát hiện lỗi CRASH.
    BẮT BUỘC PHẢI SỬ DỤNG NGAY LẬP TỨC để Auto-Remediation khi phát hiện các lỗi
    ImagePullBackOff, ErrImagePull, hoặc CrashLoopBackOff lan rộng khiến hệ thống tê liệt.
    """
    logger.info(f"⏪ AI đang ROLLBACK Deployment: {deployment_name}")
    try:
        result = _run_ssh_kubectl(["rollout", "undo", f"deployment/{deployment_name}", "-n", namespace])
        return f"✅ Đã rollback Deployment '{deployment_name}' thành công.\nLog: {result.stdout.strip()}"
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi rollback: {e.stderr}"


@mcp.tool()
def get_pod_metrics(namespace: str = "default") -> str:
    """Liệt kê tài nguyên CPU/RAM đang tiêu thụ của từng Pod trong namespace.
    Hữu ích để tìm xem Pod nào đang làm quá tải Node."""
    logger.info(f"📊 AI đang kiểm tra tài nguyên các Pod (namespace: {namespace})")
    try:
        result = _run_ssh_kubectl(["top", "pods", "-n", namespace])
        return f"--- KẾT QUẢ CPU/RAM CỦA CÁC POD ({namespace}) ---\n" + result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi lấy thông tin tài nguyên Pod: {e.stderr}"


@mcp.tool()
def describe_pod(pod_name: str, namespace: str = "default") -> str:
    """Xem chi tiết trạng thái và các sự kiện (Events) của Pod để tìm nguyên nhân
    tại sao Pod bị Crash, Pending hoặc OOMKilled."""
    logger.info(f"🔎 AI đang chuẩn đoán chuyên sâu Pod: {pod_name}")
    try:
        result = _run_ssh_kubectl(["describe", "pod", pod_name, "-n", namespace])
        # Lấy 40 dòng cuối vì phần Events quan trọng thường nằm ở cuối
        tail_output = "\n".join(result.stdout.strip().split('\n')[-40:])
        return f"--- KẾT QUẢ CHUẨN ĐOÁN (40 dòng cuối) ---\n" + tail_output
    except subprocess.CalledProcessError as e:
        return f"❌ Lỗi truy xuất thông tin Pod: {e.stderr}"
