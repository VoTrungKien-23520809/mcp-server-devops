import logging
import os
import subprocess
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("k8s_mcp_server")

KUBECTL_TIMEOUT_SECONDS = int(os.getenv("KUBECTL_TIMEOUT_SECONDS", "15"))
MAX_K8S_OUTPUT_LENGTH = int(os.getenv("MAX_K8S_OUTPUT_LENGTH", "8000"))

# Initialize MCP Server
mcp = FastMCP("DevOps_System_Monitor")

# Tool to query the cluster through kubectl.
@mcp.tool()
def get_k8s_nodes() -> str:
    """Retrieve the current status of the nodes in the Kubernetes/K3s cluster."""
    try:
        env = os.environ.copy()
        result = subprocess.run(
            ["kubectl", "get", "nodes", "-o", "wide"],
            capture_output=True,
            text=True,
            check=True,
            timeout=KUBECTL_TIMEOUT_SECONDS,
            env=env,
        )

        output = result.stdout.strip()
        if len(output) > MAX_K8S_OUTPUT_LENGTH:
            output = output[:MAX_K8S_OUTPUT_LENGTH] + "\n...[OUTPUT TRUNCATED]..."
        return f"Raw data from the cluster:\n{output}"
    except subprocess.CalledProcessError as e:
        logger.error("kubectl command failed: %s", e.stderr)
        return f"Error calling kubectl: {e.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: kubectl command timed out."
    except FileNotFoundError:
        return "Error: kubectl is not installed or not in PATH."

if __name__ == "__main__":
    print("MCP Server for K8s initialized successfully. Listening for requests...")
    mcp.run(transport='stdio')
