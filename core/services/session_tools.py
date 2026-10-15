"""
Business logic for the chat-agent MCP tools.

All functions are pure (no MCP imports) and receive an open SQLAlchemy session
plus explicit viewer_id / circle_id so they can be called from tests without
an MCP context.

Tool table from docs/PROJECT.md:
  get_session_context      — session start, one call
  get_pending_questions    — ordered waiting questions
  mark_question_asked      — flip status to "asked"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session as DbSession

from core.access import can_see
from core.clock import now_utc
from core.enums import (
    InvitationStatus,
    QuestionSource,
    QuestionStatus,
    Role,
    StoryStatus,
)
from core.models import (
    Circle,
    Invitation,
    Membership,
    Person,
    Question,
    Reaction,
    SensitiveTopic,
    Session as OrmSession,
    Story,
)

# ---------------------------------------------------------------------------
# Identity / membership guard
# ---------------------------------------------------------------------------

def require_member(db: DbSession, person_id: str, circle_id: str) -> Membership:
    """Return the Membership row for (person_id, circle_id).

    Raises ValueError with a descriptive message when:
    - either id is empty / None
    - no membership exists (person is not in the circle)

    This is the canonical identity check used by every tool. The MCP layer
    (get_viewer in server.py) calls this after reading the HTTP headers.
    """
    if not person_id or not person_id.strip():
        raise ValueError("X-Evoca-Person-Id header is missing or empty.")
    if not circle_id or not circle_id.strip():
        raise ValueError("X-Evoca-Circle-Id header is missing or empty.")

    m = (
        db.query(Membership)
        .filter(
            Membership.person_id == person_id,
            Membership.circle_id == circle_id,
        )
        .first()
    )
    if m is None:
        raise ValueError(
            f"Person '{person_id}' is not a member of circle '{circle_id}'."
        )
    return m


# ---------------------------------------------------------------------------
# get_session_context
# ---------------------------------------------------------------------------

@dataclass
class ReactionItem:
    person_name: str
    story_title: str
    emoji: str


@dataclass
class SessionSummaryItem:
    session_id: str
    started_at: str
    story_summaries: list[str]


@dataclass
class SessionContextResult:
    center_person_id: str
    center_person_name: str
    invitation_reason: str | None               # today's invitation reason, or None
    undelivered_reactions: list[ReactionItem]
    recent_session_summaries: list[SessionSummaryItem]


def get_session_context_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
) -> SessionContextResult:
    """Return context the chat agent needs at the start of a session.

    - Center person identity
    - Today's Invitation reason (if any, using the circle's timezone)
    - Reactions on the center's stories where delivered_to_center = False
    - Summaries of the last 3 finished Sessions (stories the viewer can see)
    """
    circle: Circle | None = db.get(Circle, circle_id)
    if circle is None:
        raise ValueError(f"Circle '{circle_id}' not found.")

    center_person: Person | None = db.get(Person, circle.center_person_id)
    if center_person is None:
        raise ValueError(f"Center person for circle '{circle_id}' not found.")

    # --- today's invitation ------------------------------------------------
    tz = ZoneInfo(circle.timezone)
    today_str = now_utc().astimezone(tz).strftime("%Y-%m-%d")

    invitation = (
        db.query(Invitation)
        .filter(
            Invitation.circle_id == circle_id,
            Invitation.date == today_str,
            Invitation.status == InvitationStatus.sent,
        )
        .first()
    )
    invitation_reason = invitation.reason if invitation else None

    # --- undelivered reactions on the center's stories ---------------------
    center_stories = (
        db.query(Story)
        .filter(
            Story.circle_id == circle_id,
            Story.teller_id == center_person.id,
        )
        .all()
    )
    center_story_ids = {s.id for s in center_stories}

    raw_reactions = (
        db.query(Reaction)
        .filter(
            Reaction.story_id.in_(center_story_ids),
            Reaction.delivered_to_center == False,  # noqa: E712
        )
        .all()
    )

    # Build a story-id → title lookup (filtered by can_see)
    visible_story_map: dict[str, str] = {}
    for s in center_stories:
        if can_see(db, viewer_id, s):
            visible_story_map[s.id] = s.title

    # Build a person-id → name lookup for reactors
    reactor_ids = {r.person_id for r in raw_reactions}
    reactor_map: dict[str, str] = {}
    for pid in reactor_ids:
        p = db.get(Person, pid)
        if p:
            reactor_map[pid] = p.name

    undelivered: list[ReactionItem] = []
    for r in raw_reactions:
        if r.story_id not in visible_story_map:
            # Viewer can't see this story; skip.
            continue
        undelivered.append(
            ReactionItem(
                person_name=reactor_map.get(r.person_id, r.person_id),
                story_title=visible_story_map[r.story_id],
                emoji=r.emoji,
            )
        )

    # --- last 3 finished sessions ------------------------------------------
    finished_sessions = (
        db.query(OrmSession)
        .filter(
            OrmSession.circle_id == circle_id,
            OrmSession.ended_at.isnot(None),
        )
        .order_by(OrmSession.started_at.desc())
        .limit(3)
        .all()
    )

    # All stories in this circle that the viewer can see, indexed by session_id.
    # A story belongs to a session if any of its sources entries names that session_id.
    all_circle_stories = (
        db.query(Story)
        .filter(Story.circle_id == circle_id)
        .all()
    )
    visible_by_session: dict[str, list[str]] = {}  # session_id → [ai_summary, ...]
    for story in all_circle_stories:
        if not can_see(db, viewer_id, story):
            continue
        if not story.ai_summary:
            continue
        for src in (story.sources or []):
            sid = src.get("session_id")
            if sid:
                visible_by_session.setdefault(sid, []).append(story.ai_summary)

    recent_summaries: list[SessionSummaryItem] = []
    for sess in finished_sessions:
        recent_summaries.append(
            SessionSummaryItem(
                session_id=sess.id,
                started_at=sess.started_at,
                story_summaries=visible_by_session.get(sess.id, []),
            )
        )

    return SessionContextResult(
        center_person_id=center_person.id,
        center_person_name=center_person.name,
        invitation_reason=invitation_reason,
        undelivered_reactions=undelivered,
        recent_session_summaries=recent_summaries,
    )


# ---------------------------------------------------------------------------
# get_pending_questions
# ---------------------------------------------------------------------------

# Source ordering: family=0 (first), follow_up=1, gap=2
_SOURCE_ORDER = {
    QuestionSource.family: 0,
    QuestionSource.follow_up: 1,
    QuestionSource.gap: 2,
}


def _words_4plus(text: str) -> set[str]:
    """Return the set of lowercase words with 4 or more letters in text."""
    return {w.lower() for w in re.findall(r"[a-zA-Z]{4,}", text)}


def _matches_sensitive_topic(question_text: str, topic_text: str) -> bool:
    """True if question and topic share at least one word of 4+ letters."""
    return bool(_words_4plus(question_text) & _words_4plus(topic_text))


@dataclass
class QuestionItem:
    question_id: str
    text: str
    source: str
    period: str | None
    asker_name: str | None          # None when asker_id is None (agent)
    asker_relation_to_center: str | None
    created_at: str


def get_pending_questions_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    limit: int = 5,
) -> list[QuestionItem]:
    """Return up to `limit` waiting questions for the circle's center person.

    Ordering:  family → follow_up → gap, then oldest-first within each source.
    Questions that match a SensitiveTopic are silently excluded (no status change).
    """
    circle: Circle | None = db.get(Circle, circle_id)
    if circle is None:
        raise ValueError(f"Circle '{circle_id}' not found.")

    sensitive_topics = (
        db.query(SensitiveTopic)
        .filter(SensitiveTopic.circle_id == circle_id)
        .all()
    )
    topic_texts = [t.text for t in sensitive_topics]

    # Load all waiting questions targeting the center person in this circle.
    waiting = (
        db.query(Question)
        .filter(
            Question.circle_id == circle_id,
            Question.target_person_id == circle.center_person_id,
            Question.status == QuestionStatus.waiting,
        )
        .all()
    )

    # Sensitive-topic filter (no DB write).
    def _is_sensitive(q: Question) -> bool:
        return any(_matches_sensitive_topic(q.text, t) for t in topic_texts)

    filtered = [q for q in waiting if not _is_sensitive(q)]

    # Sort: source order first, then oldest created_at.
    filtered.sort(
        key=lambda q: (
            _SOURCE_ORDER.get(q.source, 99),
            q.created_at,
        )
    )

    # Trim to limit.
    filtered = filtered[:limit]

    # Build asker lookup.
    asker_ids = {q.asker_id for q in filtered if q.asker_id}
    asker_map: dict[str, tuple[str, str | None]] = {}  # person_id → (name, relation)
    for aid in asker_ids:
        p = db.get(Person, aid)
        m = (
            db.query(Membership)
            .filter(
                Membership.person_id == aid,
                Membership.circle_id == circle_id,
            )
            .first()
        )
        if p:
            asker_map[aid] = (p.name, m.relation_to_center if m else None)

    result: list[QuestionItem] = []
    for q in filtered:
        if q.asker_id and q.asker_id in asker_map:
            asker_name, asker_rel = asker_map[q.asker_id]
        else:
            asker_name, asker_rel = None, None

        result.append(
            QuestionItem(
                question_id=q.id,
                text=q.text,
                source=q.source,
                period=q.period,
                asker_name=asker_name,
                asker_relation_to_center=asker_rel,
                created_at=q.created_at,
            )
        )

    return result


# ---------------------------------------------------------------------------
# mark_question_asked
# ---------------------------------------------------------------------------

def mark_question_asked_data(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    question_id: str,
) -> None:
    """Set Question.status to 'asked'.

    Raises ValueError if:
    - the question does not exist
    - the question belongs to a different circle
    - the question is not currently 'waiting'
    """
    q: Question | None = db.get(Question, question_id)
    if q is None:
        raise ValueError(f"Question '{question_id}' not found.")
    if q.circle_id != circle_id:
        raise ValueError(
            f"Question '{question_id}' does not belong to circle '{circle_id}'."
        )
    if q.status != QuestionStatus.waiting:
        raise ValueError(
            f"Question '{question_id}' has status '{q.status}', expected 'waiting'."
        )

    q.status = QuestionStatus.asked
    db.flush()
