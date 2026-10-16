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
                     unanswered one (docs/PROJECT.md "Hassas konular").
  story_published    A published story in the viewer's circle that the viewer
                     can_see().

Everything is filtered by can_see() before it leaves this function.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session as DbSession

from core.access import can_see
from core.enums import QuestionStatus, StoryStatus
from core.models import Membership, Person, Question, Story, StorySubject

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


def _answer_card(db: DbSession, q: Question, story: Story) -> dict[str, Any]:
    ans = q.answer
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
            "audio_url": (
                f"/api/audio/{ans['session_id']}?start={ans['start_ms']}&end={ans['end_ms']}"
            ),
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
