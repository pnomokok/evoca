"""
MCP bridge: connects the chat agent to the Evoca MCP server.

MCPBridge opens a persistent httpx2+MCP client (one per ChatAgent lifetime),
converts the server's tool list into a Bedrock toolConfig dict, and dispatches
tool calls returning structured results.

Environment variables
---------------------
EVOCA_MCP_URL   — base URL of the MCP server (default: http://localhost:8000/mcp)
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent


class MCPBridge:
    """Async context manager that wraps the MCP client lifecycle.

    Usage::

        async with MCPBridge(person_id, circle_id) as bridge:
            tool_config = await bridge.bedrock_tool_config()
            result = await bridge.call_tool("get_pending_questions", {"limit": 3})
    """

    def __init__(self, person_id: str, circle_id: str, session_id: str | None = None) -> None:
        self._person_id = person_id
        self._circle_id = circle_id
        self._session_id = session_id   # sent as X-Evoca-Session-Id (needed by mark_private)
        self._url = os.environ.get("EVOCA_MCP_URL", "http://localhost:8000/mcp")
        self._http: httpx2.AsyncClient | None = None
        self._client: Client | None = None
        self._client_ctx = None

    async def __aenter__(self) -> "MCPBridge":
        headers = {
            "X-Evoca-Person-Id": self._person_id,
            "X-Evoca-Circle-Id": self._circle_id,
        }
        if self._session_id:
            headers["X-Evoca-Session-Id"] = self._session_id
        self._http = httpx2.AsyncClient(headers=headers, timeout=30.0)
        transport = streamable_http_client(self._url, http_client=self._http)
        self._client = Client(transport)
        self._client_ctx = self._client.__aenter__
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(*exc_info)
        if self._http is not None:
            await self._http.aclose()

    # ------------------------------------------------------------------
    # Bedrock tool config
    # ------------------------------------------------------------------

    async def bedrock_tool_config(self) -> dict[str, Any]:
        """Return a Bedrock-format toolConfig built from the MCP server's tool list.

        This is called once per session so new MCP tools appear without code changes.
        """
        assert self._client is not None, "MCPBridge not entered"
        result = await self._client.list_tools()
        specs = []
        for tool in result.tools:
            # MCP tool.input_schema is already a JSON-schema dict.
            schema = tool.input_schema if tool.input_schema else {"type": "object", "properties": {}}
            specs.append(
                {
                    "toolSpec": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "inputSchema": {"json": schema},
                    }
                }
            )
        return {"tools": specs}

    # ------------------------------------------------------------------
    # Tool call
    # ------------------------------------------------------------------

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call an MCP tool and return a Python object (parsed JSON or raw text).

        Raises RuntimeError if the tool returns an error.
        """
        assert self._client is not None, "MCPBridge not entered"
        result = await self._client.call_tool(name, arguments)

        if result.is_error:
            # Collect error text from content blocks.
            error_text = " | ".join(
                b.text for b in result.content if isinstance(b, TextContent)
            )
            raise RuntimeError(f"MCP tool '{name}' returned error: {error_text}")

        # Prefer the structured result: it holds the whole return value
        # (a list tool comes back as {"result": [...]}).
        if result.structured_content is not None:
            return result.structured_content

        # Fallback: parse every text block, not just the first one.
        parsed: list[Any] = []
        for block in result.content:
            if isinstance(block, TextContent):
                try:
                    parsed.append(json.loads(block.text))
                except (json.JSONDecodeError, ValueError):
                    parsed.append(block.text)
        if not parsed:
            return None
        if len(parsed) == 1 and isinstance(parsed[0], dict):
            return parsed[0]
        return {"result": parsed}
