"""
Evoca MCP server — chat-agent tools.

Architecture:
  - Identity comes from HTTP headers only (X-Evoca-Person-Id, X-Evoca-Circle-Id),
    never from tool arguments.
  - get_viewer(ctx, db) reads those headers and delegates the membership check to
    core.services.session_tools.require_member, which raises ValueError on failure.
  - Each tool is a thin wrapper: get viewer → open DB session → call service → return.
  - All business logic lives in core/services/session_tools.py.

Run:
    uvicorn mcp_server.server:app --port 8000
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context

from core.db import SessionLocal, init_db
from core.services.session_tools import (
    get_pending_questions_data,
    get_session_context_data,
    mark_question_asked_data,
    require_member,
)

# Ensure tables exist when the module is imported (harmless if they already do).
init_db()

mcp = MCPServer("Evoca")

# ---------------------------------------------------------------------------
# Identity helper
# ---------------------------------------------------------------------------

def get_viewer(ctx: Context, db: Any) -> tuple[str, str]:
    """Read identity headers and verify membership.

    Returns (person_id, circle_id).
    Raises ValueError (surfaced as a tool error) if headers are absent or the
    person is not a member of the circle.
    """
    request = ctx.request_context.request  # Starlette Request, or None outside HTTP
    if request is None:
        raise ValueError("Tool called outside an HTTP request context.")

    person_id = request.headers.get("x-evoca-person-id", "").strip()
    circle_id = request.headers.get("x-evoca-circle-id", "").strip()

    # Delegate the membership check — raises ValueError with a clear message.
    require_member(db, person_id, circle_id)
    return person_id, circle_id


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_session_context(ctx: Context) -> dict[str, Any]:
    """Return the context the chat agent needs at the start of a session.

    Includes: center person, today's invitation reason (if any), undelivered
    reactions on the center's stories, and summaries of the last 3 finished
    sessions built from the stories the viewer can see.

    Called once at the beginning of every conversation.
    """
    with SessionLocal() as db:
        viewer_id, circle_id = get_viewer(ctx, db)
        result = get_session_context_data(db, viewer_id, circle_id)
        return asdict(result)


@mcp.tool()
def get_pending_questions(ctx: Context, limit: int = 5) -> list[dict[str, Any]]:
    """Return up to `limit` waiting questions for the circle's center person.

    Ordered by source (family first, then follow_up, then gap), then oldest
    first within each source. Questions that match a sensitive topic are
    silently excluded. Each item includes the asker's name and their
    relation_to_center.
    """
    with SessionLocal() as db:
        viewer_id, circle_id = get_viewer(ctx, db)
        items = get_pending_questions_data(db, viewer_id, circle_id, limit)
        return [asdict(item) for item in items]


@mcp.tool()
def mark_question_asked(ctx: Context, question_id: str) -> dict[str, str]:
    """Mark a waiting question as asked.

    Only valid for a question in the viewer's circle that is currently
    'waiting'. Raises an error otherwise.
    """
    with SessionLocal() as db:
        viewer_id, circle_id = get_viewer(ctx, db)
        mark_question_asked_data(db, viewer_id, circle_id, question_id)
        db.commit()
        return {"status": "ok", "question_id": question_id}


# ---------------------------------------------------------------------------
# ASGI app (for uvicorn)
# ---------------------------------------------------------------------------

app = mcp.streamable_http_app()
