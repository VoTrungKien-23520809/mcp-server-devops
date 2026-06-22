import os
import logging
import subprocess
import re
import sys
import requests
from mcp.server.fastmcp import FastMCP
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger("devops_mcp_server")

mcp = FastMCP("devops-mcp-server")

JENKINS_URL = os.getenv("JENKINS_URL")
JENKINS_USER = os.getenv("JENKINS_USER")
JENKINS_TOKEN = os.getenv("JENKINS_TOKEN")

AZURE_IP = os.getenv("AZURE_IP")
SSH_KEY_PATH = os.getenv("SSH_KEY_PATH")
SSH_KNOWN_HOSTS_PATH = os.path.expanduser(os.getenv("SSH_KNOWN_HOSTS_PATH", "~/.ssh/known_hosts"))

session = requests.Session()
_retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "OPTIONS"],
)
_adapter = HTTPAdapter(max_retries=_retry)
session.mount("http://", _adapter)
session.mount("https://", _adapter)

K8S_NAMESPACE_RE = re.compile(r"^[a-z0-9]([-.a-z0-9]*[a-z0-9])?$")
K8S_LABEL_SELECTOR_RE = re.compile(r"^[A-Za-z0-9_.-]+=[A-Za-z0-9_.-]+$")


def _run_ssh_kubectl(kubectl_args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    if not AZURE_IP or not SSH_KEY_PATH:
        raise ValueError("Missing AZURE_IP or SSH_KEY_PATH in environment.")

    ssh_cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={SSH_KNOWN_HOSTS_PATH}",
        "-i", SSH_KEY_PATH,
        f"azureuser@{AZURE_IP}",
        "sudo",
        "KUBECONFIG=/etc/rancher/k3s/k3s.yaml",
        "kubectl",
    ] + kubectl_args

    return subprocess.run(
        ssh_cmd,
        capture_output=True,
        text=True,
        check=True,
        timeout=timeout,
    )
