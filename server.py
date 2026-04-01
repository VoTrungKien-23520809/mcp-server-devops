import subprocess
from mcp.server.fastmcp import FastMCP

# Khởi tạo MCP Server
mcp = FastMCP("DevOps_System_Monitor")

# Tool sẽ gọi thẳng vào cụm K3s
@mcp.tool()
def get_k8s_nodes() -> str:
    """Retrieve the current status of the nodes in the Kubernetes/K3s cluster."""
    try:
        # Thực thi lệnh 'kubectl get nodes'
        result = subprocess.run(
            ['kubectl', 'get', 'nodes'], 
            capture_output=True, 
            text=True, 
            check=True
        )
        return f"Raw data from the cluster:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        return f"Error calling kubectl: {e.stderr}"

if __name__ == "__main__":
    print("MCP Server for K8s initialized successfully. Listening for requests...")
    mcp.run(transport='stdio')
