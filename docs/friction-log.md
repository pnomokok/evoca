## 1. Old FastMCP tutorials break on MCP Python SDK v2
- Task: Create a minimal MCP server over Streamable HTTP.
- Expected: Tutorials using `from mcp.server.fastmcp import FastMCP` would work.
- Actual: In v2, FastMCP was renamed to `MCPServer`; the old import path no longer exists.
- Severity: Medium (costs time for anyone following older guides).
- Workaround: Used `from mcp.server import MCPServer` from the v2 docs.
- Suggestion: Link the v2 migration guide from Amazon's hackathon resources page.