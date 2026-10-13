from mcp.server import MCPServer

mcp = MCPServer("Evoca")


@mcp.tool()
def hello(name: str) -> str:
    """Say hello. Used only to check that the Evoca MCP server is running."""
    return f"Hello, {name}! The Evoca MCP server is running."