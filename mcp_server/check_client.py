"""
Quick smoke-test client.  Run while the MCP server is up:

    uvicorn mcp_server.server:app --port 8000
    python mcp_server/check_client.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import anyio
import httpx2

from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import SessionLocal, init_db
from core.models import Circle


def _get_ids() -> tuple[str, str]:
    """Read the first circle's center-person ID from the database."""
    init_db()
    with SessionLocal() as db:
        circle = db.query(Circle).first()
        if circle is None:
            print("No circle found. Run: python -m core.seed")
            sys.exit(1)
        return circle.center_person_id, circle.id


async def main() -> None:
    person_id, circle_id = _get_ids()
    print(f"Using person_id={person_id}  circle_id={circle_id}")

    http = httpx2.AsyncClient(
        headers={
            "X-Evoca-Person-Id": person_id,
            "X-Evoca-Circle-Id": circle_id,
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
