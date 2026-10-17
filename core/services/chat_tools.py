"""
Business logic for the remaining chat-agent MCP tools (docs/PROJECT.md tool table).

  mark_private              — "don't let anyone hear that": the segments of a
                              session range become is_private (called by the
                              chat agent's code, never by the model)
  mark_reactions_delivered  — reactions on these stories were told to the center
                              (called by the chat agent's code after it said them)
  set_story_access          — the teller makes a story private, or shares it
                              with the circle again ("selected" comes later)
  search_archive            — stories the viewer can_see(), by keyword

All functions are pure (no MCP imports) and take an open SQLAlchemy session
plus explicit viewer_id / circle_id, like core/services/session_tools.py.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session as DbSession

from core.access import can_see
from core.enums import AccessType
from core.models import Reaction, Segment, Session as OrmSession, Story, StorySubject
from core.services.session_tools import _meaningful_words

SEARCH_LIMIT = 5
_SETTABLE_ACCESS = {AccessType.private.value, AccessType.circle.value}


# ---------------------------------------------------------------------------
# mark_private
# ---------------------------------------------------------------------------

def mark_private_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    session_id: str,
    start_ms: int,
    end_ms: int,
) -> list[str]:
    """Mark every segment of the session that overlaps [start_ms, end_ms) private.

    Only a participant of the session (the speaker) may do this. Returns the ids
    of the segments now private. Raises ValueError if nothing is in that range,
    so the caller never believes a mark succeeded when it did not.
    """
    if not session_id:
        raise ValueError("X-Evoca-Session-Id header is missing; no session to mark.")
    sess: OrmSession | None = db.get(OrmSession, session_id)
    if sess is None or sess.circle_id != circle_id:
        raise ValueError(f"Session '{session_id}' not found in this circle.")
    if viewer_id not in (sess.participant_ids or []):
        raise ValueError("Only a participant of the session can mark part of it private.")
    if start_ms >= end_ms:
        raise ValueError(f"Invalid range {start_ms}-{end_ms} ms.")

    segments = (
        db.query(Segment)
        .filter(
            Segment.session_id == session_id,
            Segment.start_ms < end_ms,
            Segment.end_ms > start_ms,
        )
        .all()
    )
    if not segments:
        raise ValueError(f"No speech in {start_ms}-{end_ms} ms of session '{session_id}'.")
    for seg in segments:
        seg.is_private = True
    db.flush()
    return [seg.id for seg in segments]


# ---------------------------------------------------------------------------
# mark_reactions_delivered
# ---------------------------------------------------------------------------

def mark_reactions_delivered_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    story_ids: list[str],
) -> int:
    """Set delivered_to_center on the undelivered reactions of these stories.

    Only stories of this circle that the viewer can see. Returns how many
    reactions were marked.
    """
    count = 0
    for story_id in story_ids:
        story: Story | None = db.get(Story, story_id)
        if story is None or story.circle_id != circle_id or not can_see(db, viewer_id, story):
            raise ValueError(f"Story '{story_id}' not found in this circle.")
        for reaction in (
            db.query(Reaction)
            .filter(Reaction.story_id == story_id, Reaction.delivered_to_center == False)  # noqa: E712
            .all()
        ):
            reaction.delivered_to_center = True
            count += 1
    db.flush()
    return count


# ---------------------------------------------------------------------------
# set_story_access
# ---------------------------------------------------------------------------

def set_story_access_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    story_id: str,
    access_type: str,
) -> None:
    """Change who can see a story. Only its teller may; only "private" and
    "circle" for now ("selected" needs member ids and comes later)."""
    story: Story | None = db.get(Story, story_id)
    if story is None or story.circle_id != circle_id or not can_see(db, viewer_id, story):
        raise ValueError(f"Story '{story_id}' not found in this circle.")
    if story.teller_id != viewer_id:
        raise ValueError("Only the person who told the story can change who hears it.")
    if access_type not in _SETTABLE_ACCESS:
        raise ValueError("Access can be set to 'private' or 'circle'.")
    story.access = {"type": access_type, "person_ids": []}
    db.flush()


# ---------------------------------------------------------------------------
# search_archive
# ---------------------------------------------------------------------------

def search_archive_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    query: str,
    person_id: str | None = None,
    period: str | None = None,
) -> list[dict[str, Any]]:
    """Stories the viewer can_see(), best keyword match first (at most 5).

    Matches query words against title, summary and place. Returns the story's
    id, title, AI summary, place, subject periods, audio sources, teller,
    access type and status; never transcript text. (The archivist narrows and
    trims these before its model sees them.)
    """
    words = _meaningful_words(query)
    results: list[tuple[int, str, dict[str, Any]]] = []
    for story in db.query(Story).filter(Story.circle_id == circle_id).all():
        if not can_see(db, viewer_id, story):
            continue
        subjects = db.query(StorySubject).filter(StorySubject.story_id == story.id).all()
        if person_id and person_id not in {s.person_id for s in subjects}:
            continue
        if period and period not in {s.period for s in subjects}:
            continue
        haystack = " ".join(filter(None, [story.title, story.ai_summary, story.place]))
        score = len(words & _meaningful_words(haystack)) if words else 0
        if words and score == 0:
            continue
        results.append((score, story.created_at, {
            "story_id": story.id,
            "title": story.title,
            "ai_summary": story.ai_summary,
            "place": story.place,
            "periods": [{"person_id": s.person_id, "period": s.period} for s in subjects],
            "sources": list(story.sources or []),
            "teller_id": story.teller_id,
            "access": (story.access or {}).get("type"),
            "status": story.status,
        }))
    results.sort(key=lambda r: (r[0], r[1]), reverse=True)
    return [r[2] for r in results[:SEARCH_LIMIT]]
