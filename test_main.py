# Import hàm từ file main.py
from main import ping_server

def test_ping_server():
    """Test the ping_server tool output."""
    # Đổi chữ 'on K3s.' thành 'and secured.'
    expected_output = "Pong! The DevOps MCP Server is fully operational and secured."
    assert ping_server() == expected_output
