"""
Quick smoke-test client.  Run while the server is up:

    uvicorn mcp_server.server:app --port 8000
    python mcp_server/check_client.py
"""

import anyio
import httpx2

from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

# Replace these with real IDs after running python -m core.seed.
_PERSON_ID = "replace-with-real-person-uuid"
_CIRCLE_ID = "replace-with-real-circle-uuid"


async def main() -> None:
    http = httpx2.AsyncClient(
        headers={
            "X-Evoca-Person-Id": _PERSON_ID,
            "X-Evoca-Circle-Id": _CIRCLE_ID,
        }
    )
    async with Client(
        streamable_http_client("http://localhost:8000/mcp", http_client=http)
    ) as client:
        print("Protocol version:", client.protocol_version)

        tools = await client.list_tools()
        print("Tools:", [tool.name for tool in tools.tools])

        result = await client.call_tool("get_pending_questions", {"limit": 3})
        for block in result.content:
            if isinstance(block, TextContent):
                print("Pending questions:", block.text)
        print("Error:", result.is_error)


if __name__ == "__main__":
    anyio.run(main)
