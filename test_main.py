# Import hàm từ file main.py
from main import ping_server

def test_ping_server():
    """Test the ping_server tool output."""
    expected_output = "Pong! The DevOps MCP Server is fully operational on K3s."
    # Kiểm tra xem kết quả trả về có khớp không
    assert ping_server() == expected_output
