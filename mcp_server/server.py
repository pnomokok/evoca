"""
Evoca MCP server — chat-agent and archivist-agent tools.

Architecture:
  - Identity comes from HTTP headers only (X-Evoca-Person-Id, X-Evoca-Circle-Id),
    never from tool arguments.
  - get_viewer(ctx, db) reads those headers and delegates the membership check to
    core.services.session_tools.require_member, which raises ValueError on failure.
  - Each tool is a thin wrapper: get viewer → open DB session → call service → return.
  - Services raise ValueError for anticipated failures. tool_errors() turns those
    into ToolError so the model sees the message and can correct its call; any
    other exception is a crash and SDK v2 hides its text from the client.
  - All business logic lives in core/services/session_tools.py and
    core/services/archive_tools.py.

Run:
    uvicorn mcp_server.server:app --port 8000
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any, Literal, TypedDict

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from core.db import SessionLocal, init_db
from core.services.archive_tools import (
    add_question_data,
    add_refused_topic_data,
    find_gaps_data,
    link_stories_data,
    get_session_transcript_data,
    mark_question_declined_data,
    record_answer_data,
    reopen_question_data,
    save_story_data,
)
from core.services.chat_tools import (
    mark_private_data,
    mark_reactions_delivered_data,
    search_archive_data,
    set_story_access_data,
)
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
# Error helper
# ---------------------------------------------------------------------------

@contextmanager
def tool_errors() -> Iterator[None]:
    """Report anticipated service failures (ValueError) to the model as ToolError."""
    try:
        yield
    except ValueError as exc:
        raise ToolError(str(exc)) from exc


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


def get_session_id(ctx: Context) -> str:
    """The live session, from the X-Evoca-Session-Id header (set by the
    backend, like identity; never a tool argument the model could choose)."""
    request = ctx.request_context.request
    return request.headers.get("x-evoca-session-id", "").strip() if request else ""


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_session_context(ctx: Context) -> dict[str, Any]:
    """Return the context the chat agent needs at the start of a session.

    Includes: center person, today's invitation reason (if any), undelivered
    reactions on the center's stories, summaries of the last 3 finished
    sessions built from the stories the viewer can see, and avoid_topics:
    topics never to raise in the conversation.

    Called once at the beginning of every conversation.
    """
    with SessionLocal() as db, tool_errors():
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
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        items = get_pending_questions_data(db, viewer_id, circle_id, limit)
        return [asdict(item) for item in items]


@mcp.tool()
def mark_question_asked(ctx: Context, question_id: str) -> dict[str, str]:
    """Mark a waiting question as asked.

    Only valid for a question in the viewer's circle that is currently
    'waiting'. Raises an error otherwise.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        mark_question_asked_data(db, viewer_id, circle_id, question_id)
        db.commit()
        return {"status": "ok", "question_id": question_id}


# ---------------------------------------------------------------------------
# Archivist tools
# ---------------------------------------------------------------------------

# LifePeriod values (core.enums), spelled out so the tool schema lists them.
PeriodValue = Literal[
    "childhood", "youth", "marriage_early_years",
    "raising_children", "midlife", "retirement",
]


class SubjectInput(TypedDict):
    """A person the story is about, with the life period it happened in."""
    person_id: str
    period: PeriodValue


class SourceInput(TypedDict):
    """An audio range of a session where the story is told."""
    session_id: str
    start_ms: int
    end_ms: int


@mcp.tool()
def get_session_transcript(ctx: Context, session_id: str) -> dict[str, Any]:
    """Return a finished session's transcript for archiving.

    Includes the session's non-private segments in order (speaker, start_ms,
    end_ms, transcript, word timestamps; speaker_id is null for the agent) and
    the circle's questions with status 'asked', so answers can be matched.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        result = get_session_transcript_data(db, viewer_id, circle_id, session_id)
        return asdict(result)


@mcp.tool()
def save_story(
    ctx: Context,
    title: str,
    summary: str,
    teller_id: str,
    subjects: list[SubjectInput],
    sources: list[SourceInput],
    place: str | None = None,
    stated_year: int | None = None,
    original_story_id: str | None = None,
) -> dict[str, str]:
    """Save one story extracted from a session. Returns its story_id.

    subjects: people the story is about, each with a period from
    childhood, youth, marriage_early_years, raising_children, midlife, retirement.
    sources: audio ranges {session_id, start_ms, end_ms} where the story is told.
    stated_year only if the teller said the year. original_story_id only for a
    retelling of an existing story. The story starts as pending, visible to the
    circle after 24 hours. When the connection names a session (the archivist's
    X-Evoca-Session-Id), every source must be in that session.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        story_id = save_story_data(
            db, viewer_id, circle_id,
            title=title, summary=summary, teller_id=teller_id,
            subjects=[dict(s) for s in subjects],
            sources=[dict(s) for s in sources],
            place=place, stated_year=stated_year,
            original_story_id=original_story_id,
            session_id=get_session_id(ctx) or None,
        )
        db.commit()
        return {"story_id": story_id}


@mcp.tool()
def record_answer(
    ctx: Context,
    question_id: str,
    story_id: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    """Record that an asked question was answered in a saved story.

    start_ms / end_ms is the audio range of the answer in the story's session.
    The question's status becomes 'answered'.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        answer = record_answer_data(
            db, viewer_id, circle_id, question_id, story_id, start_ms, end_ms
        )
        db.commit()
        return {"status": "ok", "question_id": question_id, "answer": answer}


@mcp.tool()
def add_question(
    ctx: Context,
    text: str,
    source: Literal["follow_up", "gap"],
    period: PeriodValue | None = None,
) -> dict[str, str]:
    """Add a question for the center person to be asked in a later session.

    source: 'follow_up' or 'gap'. period: optional life period. Questions that
    touch a sensitive topic are kept with status 'filtered' and never asked.
    Returns {question_id, status}.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        result = add_question_data(db, viewer_id, circle_id, text, source, period)
        db.commit()
        return result


@mcp.tool()
def mark_question_declined(
    ctx: Context,
    question_id: str,
    session_id: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, str]:
    """Record that the speaker declined to answer an asked question.

    Only when the speaker clearly refused to talk about it ("I'd rather not
    talk about that"). start_ms / end_ms is where they decline. The question
    is never offered again. When unsure, do not call this.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        mark_question_declined_data(
            db, viewer_id, circle_id, question_id, session_id, start_ms, end_ms
        )
        db.commit()
        return {"status": "ok", "question_id": question_id}


@mcp.tool()
def reopen_question(ctx: Context, question_id: str) -> dict[str, str]:
    """Return an asked but unanswered question to 'waiting' so it is asked again.

    Called by the archivist's own code at the end of a session, not by the model.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        reopen_question_data(db, viewer_id, circle_id, question_id)
        db.commit()
        return {"status": "ok", "question_id": question_id}


@mcp.tool()
def add_refused_topic(ctx: Context, text: str, start_ms: int, end_ms: int) -> dict[str, Any]:
    """Remember a topic the speaker clearly refused to talk about on her own.

    Only for a clear refusal of a topic ("I don't want to talk about Hatice"),
    not for a declined question (use mark_question_declined for that). text
    names the topic by its own name, place or event, e.g. "Hatice". start_ms / end_ms
    is where the speaker refuses, in the session being archived. The topic is
    never asked about again. When unsure, do not call this.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        result = add_refused_topic_data(
            db, viewer_id, circle_id, get_session_id(ctx), text, start_ms, end_ms
        )
        db.commit()
        return {"status": "ok", **result}


@mcp.tool()
def link_stories(
    ctx: Context,
    from_story_id: str,
    to_story_id: str,
    reason: Literal["same_place", "same_event", "continuation"],
) -> dict[str, Any]:
    """Suggest a link between a story saved in this session and a related story.

    from_story_id: a story you saved in the session being archived. to_story_id:
    a story found with search_archive. reason: same_place, same_event or
    continuation. Only for a clear connection; when unsure, do not link. A
    retelling of an existing story is not a link: save it with
    original_story_id instead. At most 3 links per story. Returns {link_id, added}.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        result = link_stories_data(
            db, viewer_id, circle_id, get_session_id(ctx), from_story_id, to_story_id, reason
        )
        db.commit()
        return {"status": "ok", **result}


@mcp.tool()
def find_gaps(ctx: Context, person_id: str) -> list[str]:
    """Return the life periods of the center person that have no story yet.

    person_id must be the center person of the circle. Periods she is too
    young to have lived are left out. Use one to add at most one gap question
    (add_question with source 'gap' and that period).
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        return find_gaps_data(db, viewer_id, circle_id, person_id)


# ---------------------------------------------------------------------------
# Chat-agent tools: privacy, reactions, story access, archive search
# ---------------------------------------------------------------------------

@mcp.tool()
def mark_private(ctx: Context, start_ms: int, end_ms: int) -> dict[str, Any]:
    """Hide a range of the live session: its segments become private.

    "Don't let anyone hear that." The session comes from the X-Evoca-Session-Id
    header. Called by the chat agent's code with exact segment boundaries.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        ids = mark_private_data(db, viewer_id, circle_id, get_session_id(ctx), start_ms, end_ms)
        db.commit()
        return {"status": "ok", "segments_marked": len(ids)}


@mcp.tool()
def mark_reactions_delivered(ctx: Context, story_ids: list[str]) -> dict[str, Any]:
    """Record that the reactions on these stories were told to the center person."""
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        count = mark_reactions_delivered_data(db, viewer_id, circle_id, story_ids)
        db.commit()
        return {"status": "ok", "reactions_marked": count}


@mcp.tool()
def set_story_access(
    ctx: Context,
    story_id: str,
    type: Literal["private", "circle"],
) -> dict[str, str]:
    """Change who can hear one of the speaker's own stories.

    "private": only the speaker. "circle": the whole family circle again.
    Only the person who told the story can change it. Find the story_id with
    search_archive.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        set_story_access_data(db, viewer_id, circle_id, story_id, type)
        db.commit()
        return {"status": "ok", "story_id": story_id, "access": type}


@mcp.tool()
def search_archive(
    ctx: Context,
    query: str,
    person_id: str | None = None,
    period: PeriodValue | None = None,
) -> list[dict[str, Any]]:
    """Find stories in the family archive by keywords (at most 5).

    Returns story_id, title, AI summary, place, periods and audio sources of
    stories the viewer is allowed to see. Use it when the person asks about
    something they may have told before, or to find a story's id.
    """
    with SessionLocal() as db, tool_errors():
        viewer_id, circle_id = get_viewer(ctx, db)
        return search_archive_data(db, viewer_id, circle_id, query, person_id, period)


# ---------------------------------------------------------------------------
# ASGI app (for uvicorn)
# ---------------------------------------------------------------------------

app = mcp.streamable_http_app()
