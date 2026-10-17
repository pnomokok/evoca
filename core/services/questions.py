"""
Family questions from the panel (POST /api/questions, GET /api/questions/mine).

A family member who sends the same question twice (a double click, or the
same question with "Grandma," in front) gets the first one back instead of a
second copy, so the center is never asked it twice.

my_questions shows the asker only "waiting" or "answered": a declined, asked
or speaker-filtered question looks unanswered, and an unanswered question
that matches a family topic is not listed (it is never asked; the asker of a
new one is told it was not sent).
"""

from __future__ import annotations

import re

from typing import Any

from sqlalchemy.orm import Session as DbSession

from core.access import can_see
from core.enums import QuestionSource, QuestionStatus, TopicSource
from core.models import Question, SensitiveTopic, Story
from core.services.session_tools import _matches_sensitive_topic

_ADDRESS = re.compile(r"^\s*(?:grandma|grandpa)\s*,", re.IGNORECASE)
_PUNCTUATION = re.compile(r"[^\w\s]")
_OPEN = (QuestionStatus.waiting, QuestionStatus.asked, QuestionStatus.declined, QuestionStatus.filtered)


def normalize_question_text(text: str) -> str:
    """Lowercase, without a leading "Grandma,"/"Grandpa,", punctuation or extra spaces."""
    text = _ADDRESS.sub("", text)
    return " ".join(_PUNCTUATION.sub(" ", text.lower()).split())


def _family_topic_texts(db: DbSession, circle_id: str) -> list[str]:
    return [
        t.text for t in db.query(SensitiveTopic).filter(SensitiveTopic.circle_id == circle_id)
        if t.source != TopicSource.speaker
    ]


def find_duplicate(
    db: DbSession, circle_id: str, asker_id: str, target_person_id: str, text: str
) -> Question | None:
    """The asker's open family question to the same person with the same text, if any.

    Open means unanswered as the asker sees it: waiting, asked, declined, or
    filtered only by a topic the center refused herself (the panel shows all
    of these as waiting). Returning the same question for all of them keeps a
    second send from telling the asker which one it is. An open question that
    matches a current family topic is never returned, whatever its status, so
    the new send gets the "not sent" answer; skipping only the filtered ones
    would tell a waiting question from a speaker-filtered one once the family
    adds a topic.
    """
    key = normalize_question_text(text)
    family_topics = _family_topic_texts(db, circle_id)
    candidates = (
        db.query(Question)
        .filter(
            Question.circle_id == circle_id,
            Question.asker_id == asker_id,
            Question.target_person_id == target_person_id,
            Question.source == QuestionSource.family,
            Question.status.in_(_OPEN),
        )
        .order_by(Question.created_at)
        .all()
    )
    for q in candidates:
        if normalize_question_text(q.text) != key:
            continue
        if any(_matches_sensitive_topic(q.text, t) for t in family_topics):
            continue
        return q
    return None


def my_questions(db: DbSession, viewer_id: str, circle_id: str) -> list[dict[str, Any]]:
    """The viewer's own family questions in the circle, newest first.

    status is "answered" (with answer_story_id) only once the viewer can_see()
    the answer's story, like the feed's answer card; everything else is
    "waiting". An unanswered question that matches a current family topic is
    left out whatever its status (the same rule as find_duplicate), so a
    question filtered only by a topic the center refused herself looks exactly
    like a waiting one, before and after the family adds a topic.
    """
    family_topics = _family_topic_texts(db, circle_id)
    rows = (
        db.query(Question)
        .filter(
            Question.circle_id == circle_id,
            Question.asker_id == viewer_id,
            Question.source == QuestionSource.family,
        )
        .order_by(Question.created_at.desc(), Question.id)
        .all()
    )
    items: list[dict[str, Any]] = []
    for q in rows:
        if q.status != QuestionStatus.answered and any(
                _matches_sensitive_topic(q.text, t) for t in family_topics):
            continue
        status, story_id = QuestionStatus.waiting.value, None
        if q.status == QuestionStatus.answered and q.answer:
            story = db.get(Story, q.answer.get("story_id"))
            if story is not None and can_see(db, viewer_id, story):
                status, story_id = QuestionStatus.answered.value, story.id
        items.append({
            "id": q.id,
            "text": q.text,
            "target_person_id": q.target_person_id,
            "period": q.period,
            "status": status,
            "created_at": q.created_at,
            "answer_story_id": story_id,
        })
    return items
