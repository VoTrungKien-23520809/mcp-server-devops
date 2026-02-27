from mcp.server.fastmcp import FastMCP

# Khởi tạo MCP server
mcp = FastMCP("devops-mcp-server")

# Tạo tool kiểm tra trạng thái
@mcp.tool()
def ping_server() -> str:
    """Check if the MCP server is alive and responding."""
    return "Pong! The DevOps MCP Server is fully operational on K3s."

# Chạy server qua stdio
if __name__ == "__main__":
    mcp.run(transport='stdio')