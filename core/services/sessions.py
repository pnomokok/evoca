"""
Conversation storage helpers.

These functions create and update Session and Segment rows.
All callers must commit the transaction themselves after calling these.
"""

from __future__ import annotations

from sqlalchemy.orm import Session as DbSession

from core.clock import now_utc
from core.enums import SessionKind, SessionStart
from core.models import Segment, Session as OrmSession


def start_session(
    db: DbSession,
    circle_id: str,
    started_by: SessionStart,
    participant_ids: list[str],
) -> OrmSession:
    """Create a new open Session row and flush it (no commit).

    The caller must commit when ready.
    """
    sess = OrmSession(
        circle_id=circle_id,
        kind=SessionKind.solo,
        started_by=started_by,
        participant_ids=list(participant_ids),
        started_at=now_utc().isoformat(),
        ended_at=None,
    )
    db.add(sess)
    db.flush()
    return sess


def add_segment(
    db: DbSession,
    session_id: str,
    speaker_id: str | None,
    transcript: str,
    start_ms: int,
    end_ms: int,
    words: list[dict] | None = None,
    is_private: bool = False,
) -> Segment:
    """Append a Segment to an existing Session and flush it (no commit).

    speaker_id=None means the agent spoke this segment.
    words defaults to an empty list (text turns have no word timestamps).
    """
    seg = Segment(
        session_id=session_id,
        speaker_id=speaker_id,
        transcript=transcript,
        start_ms=start_ms,
        end_ms=end_ms,
        words=words if words is not None else [],
        is_private=is_private,
    )
    db.add(seg)
    db.flush()
    return seg


def end_session(db: DbSession, session_id: str) -> None:
    """Set ended_at on the Session row and flush it (no commit)."""
    sess: OrmSession | None = db.get(OrmSession, session_id)
    if sess is None:
        raise ValueError(f"Session '{session_id}' not found.")
    sess.ended_at = now_utc().isoformat()
    db.flush()
