"""
Family questions from the panel (POST /api/questions).

A family member who sends the same question twice (a double click, or the
same question with "Grandma," in front) gets the first one back instead of a
second copy, so the center is never asked it twice.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session as DbSession

from core.enums import QuestionSource, QuestionStatus, TopicSource
from core.models import Question, SensitiveTopic
from core.services.session_tools import _matches_sensitive_topic

_ADDRESS = re.compile(r"^\s*(?:grandma|grandpa)\s*,", re.IGNORECASE)
_PUNCTUATION = re.compile(r"[^\w\s]")
_OPEN = (QuestionStatus.waiting, QuestionStatus.asked, QuestionStatus.declined, QuestionStatus.filtered)


def normalize_question_text(text: str) -> str:
    """Lowercase, without a leading "Grandma,"/"Grandpa,", punctuation or extra spaces."""
    text = _ADDRESS.sub("", text)
    return " ".join(_PUNCTUATION.sub(" ", text.lower()).split())


def find_duplicate(
    db: DbSession, circle_id: str, asker_id: str, target_person_id: str, text: str
) -> Question | None:
    """The asker's open family question to the same person with the same text, if any.

    Open means unanswered as the asker sees it: waiting, asked, declined, or
    filtered only by a topic the center refused herself (the panel shows all
    of these as waiting). Returning the same question for all of them keeps a
    second send from telling the asker which one it is.
    """
    key = normalize_question_text(text)
    family_topics = [
        t.text for t in db.query(SensitiveTopic).filter(SensitiveTopic.circle_id == circle_id)
        if t.source != TopicSource.speaker
    ]
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
        if q.status == QuestionStatus.filtered and any(
                _matches_sensitive_topic(q.text, t) for t in family_topics):
            continue
        return q
    return None
