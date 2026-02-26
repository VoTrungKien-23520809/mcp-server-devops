import subprocess
from mcp.server.fastmcp import FastMCP

# Khởi tạo MCP Server
mcp = FastMCP("DevOps_System_Monitor")

# Tool này sẽ gọi thẳng vào cụm K3s của bạn
@mcp.tool()
def get_k8s_nodes() -> str:
    """Lấy trạng thái thực tế của các node trong cụm Kubernetes/K3s"""
    try:
        # Thực thi lệnh 'kubectl get nodes'
        result = subprocess.run(
            ['kubectl', 'get', 'nodes'], 
            capture_output=True, 
            text=True, 
            check=True
        )
        return f"Dữ liệu thực tế từ cluster:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Lỗi khi gọi kubectl: {e.stderr}"

if __name__ == "__main__":
    print("Khởi động MCP Server K8s thành công. Đang lắng nghe yêu cầu...")
    mcp.run(transport='stdio')
