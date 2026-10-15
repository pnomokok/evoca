# Evoca project rules

- The single source of truth is docs/PROJECT.md. Read it before writing code.
- Use the exact names from its "Kavramlar sözlüğü" (glossary) and "Veri modeli" (data model) sections. Do not rename fields or enum values.
- All code, comments, UI text and commit messages are in English.
- Every MCP tool and REST endpoint must filter results with can_see() before returning data. Private segments never reach the LLM.
- Never put API keys in code. Use the .env file.
- If something in the code needs to differ from docs/PROJECT.md, stop and ask first.

## Project structure

- core/: data model, access control (can_see), services, clock. Business logic lives in core/services/.
- mcp_server/: thin MCP tool wrappers. Identity comes from the X-Evoca-Person-Id and X-Evoca-Circle-Id headers, never from tool arguments.
- server/: agents, LLM wrapper, MCP bridge, later the FastAPI backend.
- Use core.clock.now_utc() for "now". Never call datetime.now() directly.
- Tests run with "pytest" from the repo root. Async tests use @pytest.mark.anyio.

## MCP Python SDK v2 (mcp 2.3) — do not use v1 APIs

Older examples online and in model memory are for v1. In this project:

- Server class: `from mcp.server import MCPServer` (not FastMCP). Context: `from mcp.server.mcpserver import Context`.
- HTTP headers inside a tool: `ctx.request_context.request.headers` (request is None outside HTTP).
- HTTP client package is `httpx2` (not httpx): `streamable_http_client(url, http_client=httpx2.AsyncClient(headers=...))`.
- Field names are snake_case: `tool.input_schema`, `result.structured_content`, `result.is_error`, `client.protocol_version`.
- Prefer `result.structured_content` when reading a tool result; a tool that returns a list comes back as `{"result": [...]}`.
- Bedrock's own toolSpec key stays camelCase: `{"toolSpec": {"name", "description", "inputSchema": {"json": ...}}}`.

## Testing against reality

- Fakes are fine for unit tests, but every new MCP tool or bridge change must also be tried against the real server
  (uvicorn mcp_server.server:app --port 8000) before it is called done.
