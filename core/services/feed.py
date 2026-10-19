"""
The family panel's feed (GET /api/feed), shaped like docs/api-samples/GET_feed.json.

Two kinds of items, newest first:

  question_answered  The viewer's own question was answered (A3, step 6). Shown
                     only to the asker, and only once the asker can_see() the
                     answer's story (the same rule as GET /api/audio), so a
                     pending, hidden or private story keeps the answer back.
                     created_at is the story's publish_at: when the answer
                     becomes visible. Questions in any other status never
                     appear, so a declined question looks exactly like an
                     unanswered one (docs/ARCHITECTURE.md "Design principles and rules").
                     audio is the answer as pieces: the answer story's own
                     pieces in that session, like the story page, so the
                     agent's turns, private parts and anything outside the
                     story are skipped.
                     duration_ms is their total; audio_url is the first piece
                     (kept for older clients). audio is [] and audio_url null
                     when the answer's session has no audio file (e.g. a
                     text-only session), instead of URLs that 404.
                     photo_url / photo_caption / photo_added_by are the answer story's photo.
  story_published    A published story in the viewer's circle that the viewer
                     can_see(), with its photo_url / photo_caption / photo_added_by (or nulls).

Everything is filtered by can_see() before it leaves this function.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session as DbSession

from core.access import can_see
from core.enums import QuestionStatus, StoryStatus
from core.models import Membership, Person, Question, Story, StorySubject
from core.models import Session as OrmSession
from core.services.photo_view import photo_fields

FEED_LIMIT = 50


def _sort_key(item: dict[str, Any]) -> datetime:
    dt = datetime.fromisoformat(item["created_at"])
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _teller(db: DbSession, person_id: str, circle_id: str) -> dict[str, Any]:
    person = db.get(Person, person_id)
    membership = db.get(Membership, (person_id, circle_id))
    return {
        "id": person_id,
        "name": person.name if person else None,
        "relation_to_center": membership.relation_to_center if membership else None,
    }


def _answer_audio(db: DbSession, ans: dict[str, Any], story: Story) -> list[dict[str, Any]]:
    """The answer's audio pieces, or [] if its session has no audio file.

    The answer is its story: every piece of the story in the answer's session,
    private parts cut (the story page's audio), so the agent's turns in between
    and anything outside the story are skipped. The asker can_see() the story,
    so GET /api/audio lets them hear each piece.
    """
    from core.services.stories import _audio_ranges  # stories imports this module

    session_id = ans["session_id"]
    sess = db.get(OrmSession, session_id)
    if sess is None or not sess.audio_path or not Path(sess.audio_path).exists():
        return []
    return [r for r in _audio_ranges(db, story) if r["session_id"] == session_id]


def _answer_card(db: DbSession, q: Question, story: Story) -> dict[str, Any]:
    ans = q.answer
    audio = _answer_audio(db, ans, story)
    return {
        "type": "question_answered",
        "created_at": story.publish_at,
        "question": {"id": q.id, "text": q.text, "asker_id": q.asker_id},
        "answer": {
            "story_id": story.id,
            "story_title": story.title,
            "teller": _teller(db, story.teller_id, story.circle_id),
            "session_id": ans["session_id"],
            "start_ms": ans["start_ms"],
            "end_ms": ans["end_ms"],
            "audio_url": audio[0]["url"] if audio else None,
            "audio": audio,
            "duration_ms": sum(p["end_ms"] - p["start_ms"] for p in audio),
            **photo_fields(db, story),
        },
    }


def _story_card(db: DbSession, story: Story) -> dict[str, Any]:
    subjects = db.query(StorySubject).filter(StorySubject.story_id == story.id).all()
    return {
        "type": "story_published",
        "created_at": story.publish_at,
        "story": {
            "id": story.id,
            "title": story.title,
            "ai_summary": story.ai_summary,
            "teller": _teller(db, story.teller_id, story.circle_id),
            "subjects": [
                {"person_id": s.person_id, "period": s.period, "period_source": s.period_source}
                for s in subjects
            ],
            "duration_ms": sum(
                max(0, src.get("end_ms", 0) - src.get("start_ms", 0)) for src in story.sources or []
            ),
            **photo_fields(db, story),
        },
    }


def build_feed(db: DbSession, viewer_id: str, circle_id: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    answered = (
        db.query(Question)
        .filter(
            Question.circle_id == circle_id,
            Question.asker_id == viewer_id,
            Question.status == QuestionStatus.answered,
        )
        .all()
    )
    for q in answered:
        if not q.answer:
            continue
        story = db.get(Story, q.answer.get("story_id"))
        if story is not None and can_see(db, viewer_id, story):
            items.append(_answer_card(db, q, story))

    published = (
        db.query(Story)
        .filter(Story.circle_id == circle_id, Story.status == StoryStatus.published)
        .all()
    )
    for story in published:
        if can_see(db, viewer_id, story):
            items.append(_story_card(db, story))

    items.sort(key=_sort_key, reverse=True)
    return {"items": items[:FEED_LIMIT]}
