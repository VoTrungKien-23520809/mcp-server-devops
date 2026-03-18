import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("devops_mcp_server")

# Initialize MCP Server
mcp = FastMCP("devops-mcp-server")


# Runtime configuration
WORKSPACE_ROOT = Path(
    os.getenv("WORKSPACE_ROOT", str(Path(__file__).resolve().parent))
).resolve()
JENKINS_URL = os.getenv("JENKINS_URL", "").strip()
JENKINS_USER = os.getenv("JENKINS_USER", "").strip()
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN", "").strip()
REQUEST_TIMEOUT_SECONDS = int(os.getenv("HTTP_TIMEOUT_SECONDS", "10"))
TERRAFORM_TIMEOUT_SECONDS = int(os.getenv("TERRAFORM_TIMEOUT_SECONDS", "120"))
MAX_LOG_LENGTH = int(os.getenv("MAX_JENKINS_LOG_LENGTH", "5000"))
MAX_FILE_LENGTH = int(os.getenv("MAX_CODE_CONTEXT_LENGTH", "10000"))


def _build_http_session() -> requests.Session:
    session = requests.Session()
    retry_config = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    adapter = HTTPAdapter(max_retries=retry_config)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


_HTTP_SESSION = _build_http_session()


def _resolve_path_in_workspace(raw_path: str) -> Optional[Path]:
    if not raw_path:
        return None

    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = (WORKSPACE_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(WORKSPACE_ROOT)
    except ValueError:
        return None
    return candidate

# Tool 1: Test Server
@mcp.tool()
def ping_server() -> str:
    """Check MCP Server connection status."""
    return "Pong! The DevOps MCP Server is fully operational."

# Tool 2: Fetch Jenkins Logs
@mcp.tool()
def get_jenkins_logs(job_name: str, build_number: str) -> str:
    """
    Fetch the console log of a Jenkins build for error analysis.
    """
    if not JENKINS_URL or not JENKINS_USER or not JENKINS_TOKEN:
        return (
            "Error: Jenkins is not configured. "
            "Set JENKINS_URL, JENKINS_USER, and JENKINS_TOKEN environment variables."
        )

    if not job_name or not job_name.strip():
        return "Error: job_name must not be empty."

    # Default to lastBuild when build_number is empty.
    if not build_number:
        build_number = "lastBuild"

    try:
        url = f"{JENKINS_URL.rstrip('/')}/job/{job_name.strip()}/{build_number.strip()}/consoleText"
        response = _HTTP_SESSION.get(
            url,
            auth=(JENKINS_USER, JENKINS_TOKEN),
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        logs = response.text
        if len(logs) > MAX_LOG_LENGTH:
            logger.info("Truncated Jenkins log output", extra={"max_length": MAX_LOG_LENGTH})
            return "...[LOG TRUNCATED]...\n" + logs[-MAX_LOG_LENGTH:]
        return logs

    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch Jenkins logs: %s", e)
        return f"Error fetching logs from Jenkins: {str(e)}"

# Tool 3: Read Terraform Plan
@mcp.tool()
def get_terraform_plan(tf_directory: str) -> str:
    """
    Run 'terraform plan' in the specified directory and return the output.
    Allows AI to evaluate infrastructure changes and potential risks.
    """
    safe_tf_directory = _resolve_path_in_workspace(tf_directory)
    if safe_tf_directory is None:
        return (
            "Error: tf_directory is outside of WORKSPACE_ROOT. "
            "Only workspace-local paths are allowed."
        )

    if not safe_tf_directory.is_dir():
        return f"Error: Directory '{safe_tf_directory}' does not exist."

    try:
        # Run terraform plan without color codes for easier AI parsing.
        result = subprocess.run(
            ["terraform", "plan", "-no-color", "-input=false"],
            cwd=str(safe_tf_directory),
            capture_output=True,
            text=True,
            check=True,
            timeout=TERRAFORM_TIMEOUT_SECONDS,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        logger.error("Terraform plan failed: %s", e.stderr)
        return f"Terraform plan failed:\n{e.stderr}"
    except FileNotFoundError:
        return "Error: Terraform is not installed or not in PATH."
    except subprocess.TimeoutExpired:
        return "Error: Terraform plan timed out."
    except Exception as e:
        logger.exception("Unexpected error while running terraform plan")
        return f"Unexpected error: {str(e)}"

# Tool 4: Read Code Context
@mcp.tool()
def read_code_context(file_path: str) -> str:
    """
    Read the content of a specific source code, script, or configuration file.
    Helps the AI understand the project context to suggest fixes.
    """
    safe_file_path = _resolve_path_in_workspace(file_path)
    if safe_file_path is None:
        return (
            "Error: file_path is outside of WORKSPACE_ROOT. "
            "Only workspace-local paths are allowed."
        )

    if safe_file_path.is_symlink():
        return "Error: Symbolic links are not allowed for read_code_context."

    if not safe_file_path.is_file():
        return f"Error: File '{safe_file_path}' does not exist."

    try:
        with open(safe_file_path, "r", encoding="utf-8") as f:
            content = f.read()
            if len(content) > MAX_FILE_LENGTH:
                logger.info("Truncated file context", extra={"max_length": MAX_FILE_LENGTH})
                return content[:MAX_FILE_LENGTH] + "\n...[FILE TRUNCATED]..."
            return content
    except Exception as e:
        logger.exception("Error reading file context")
        return f"Error reading file '{safe_file_path}': {str(e)}"

if __name__ == "__main__":
    mcp.run()


