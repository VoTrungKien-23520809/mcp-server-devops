import json
import requests
from . import mcp, logger, AZURE_IP


@mcp.tool()
def query_prometheus(query_type: str = "cpu") -> str:
    """
    Công cụ truy vấn dữ liệu từ Prometheus. Tham số query_type có thể là:
    - 'cpu': Lấy phần trăm CPU hiện tại.
    - 'ram': Lấy phần trăm RAM hiện tại.
    - 'storage': Lấy phần trăm ổ đĩa hiện tại.
    - 'network': Lấy tốc độ mạng tải xuống hiện tại.
    - Hoặc một câu lệnh PromQL bất kỳ để kiểm tra các metric khác.
    """
    logger.info(f"📈 AI đang truy vấn Prometheus với query_type: {query_type}")

    prometheus_url = f"http://{AZURE_IP}:30003/api/v1/query"

    _MACROS = {
        "cpu":     '100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        "ram":     '100 * (1 - ((avg_over_time(node_memory_MemFree_bytes[5m]) + avg_over_time(node_memory_Cached_bytes[5m]) + avg_over_time(node_memory_Buffers_bytes[5m])) / avg_over_time(node_memory_MemTotal_bytes[5m])))',
        "storage": '100 - (avg(node_filesystem_avail_bytes{mountpoint="/"}) / avg(node_filesystem_size_bytes{mountpoint="/"}) * 100)',
        "network": 'sum(rate(node_network_receive_bytes_total[5m]))',
    }
    promql = _MACROS.get(query_type.lower(), query_type)

    try:
        response = requests.get(prometheus_url, params={'query': promql}, timeout=10)
        data = response.json()

        if data.get('status') != 'success':
            return f"❌ Lỗi truy vấn Prometheus: {data.get('error', 'Unknown Error')}"

        results = data['data']['result']
        if not results:
            return f"Không tìm thấy dữ liệu cho truy vấn này."

        key = query_type.lower()
        if key in ("cpu", "ram", "storage"):
            val = float(results[0]['value'][1])
            return f"🔥 Chỉ số {key.upper()} Usage hiện tại: {val:.2f}%"
        elif key == "network":
            val = float(results[0]['value'][1])
            return f"🔥 Tốc độ mạng tải xuống (Network Receive) hiện tại: {val / (1024*1024):.2f} MB/s"
        else:
            return f"Kết quả PromQL: {json.dumps(results[:5], indent=2)}"

    except Exception as e:
        logger.error(f"Lỗi khi truy vấn Prometheus: {str(e)}")
        return f"❌ Không thể kết nối tới Prometheus: {str(e)}"
