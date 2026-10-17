"""
Business logic for the admin panel endpoints (docs/PROJECT.md "REST uçları").

  require_admin           every admin endpoint
  list_family_topics      GET    /api/admin/sensitive-topics
  add_family_topic        POST   /api/admin/sensitive-topics
  delete_family_topic     DELETE /api/admin/sensitive-topics/{id}
  update_circle_settings  PATCH  /api/admin/circle

Privacy rules applied here:
- Only the circle's admin gets past require_admin; everyone else gets the same
  Forbidden, whatever their role.
- Topics the center refused herself (source "speaker") never leave this module:
  they are not listed, not counted, and their ids raise the same NotFound as a
  missing id. The duplicate check only looks at family topics, so adding a text
  that matches a speaker topic does not reveal it.
- Deleting a topic does not re-evaluate questions it already filtered.

Functions take an open SQLAlchemy session and an explicit viewer_id, like the
other services, and commit their own writes.
"""

from __future__ import annotations

import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session as DbSession

from core.access import role
from core.clock import now_utc
from core.enums import Role, TopicSource
from core.models import Circle, SensitiveTopic
from core.services.session_tools import _meaningful_words

_MAX_TOPIC_CHARS = 200
_CHAT_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

ADMIN_ONLY = "Only an admin of this circle can do this."
TOPIC_NOT_FOUND = "Topic not found."


class NotFound(Exception):
    """Missing, or a topic the admin may not see (the two look the same)."""


class Forbidden(Exception):
    """The viewer is not an admin of the circle."""


def require_admin(db: DbSession, viewer_id: str, circle_id: str) -> None:
    if role(db, viewer_id, circle_id) != Role.admin:
        raise Forbidden(ADMIN_ONLY)


def _family_topics(db: DbSession, circle_id: str):
    return db.query(SensitiveTopic).filter(
        SensitiveTopic.circle_id == circle_id,
        SensitiveTopic.source == TopicSource.family,
    )


def _topic_dict(t: SensitiveTopic) -> dict[str, Any]:
    return {"id": t.id, "text": t.text, "added_by": t.added_by, "created_at": t.created_at}


# ---------------------------------------------------------------------------
# Sensitive topics (family only)
# ---------------------------------------------------------------------------

def list_family_topics(db: DbSession, viewer_id: str, circle_id: str) -> list[dict[str, Any]]:
    """The family's topics, oldest first. Speaker topics are never included."""
    require_admin(db, viewer_id, circle_id)
    return [_topic_dict(t) for t in _family_topics(db, circle_id).order_by(SensitiveTopic.created_at)]


def add_family_topic(db: DbSession, viewer_id: str, circle_id: str, text: str) -> dict[str, Any]:
    """Add a family topic (added_by = the admin). Same text rule as
    add_refused_topic: it must hold a word the matcher can use. A family topic
    with the same text (case-insensitive) is returned instead of a new one."""
    require_admin(db, viewer_id, circle_id)
    topic = " ".join((text or "").split())
    if not topic:
        raise ValueError("Topic text is required.")
    if len(topic) > _MAX_TOPIC_CHARS:
        raise ValueError(f"Topic text must be at most {_MAX_TOPIC_CHARS} characters.")
    if not _meaningful_words(topic):
        # It would filter no question, so saving it would promise what it cannot keep.
        raise ValueError("Topic must name something specific: a name, a place or an event.")

    norm = topic.lower()
    for existing in _family_topics(db, circle_id).all():
        if " ".join(existing.text.lower().split()) == norm:
            return _topic_dict(existing)

    row = SensitiveTopic(
        circle_id=circle_id,
        text=topic,
        source=TopicSource.family,
        added_by=viewer_id,
        created_at=now_utc().isoformat(),
    )
    db.add(row)
    db.commit()
    return _topic_dict(row)


def delete_family_topic(db: DbSession, viewer_id: str, circle_id: str, topic_id: str) -> dict[str, Any]:
    """Delete a family topic. Questions it already filtered stay filtered."""
    require_admin(db, viewer_id, circle_id)
    row = _family_topics(db, circle_id).filter(SensitiveTopic.id == topic_id).first()
    if row is None:
        raise NotFound(TOPIC_NOT_FOUND)
    db.delete(row)
    db.commit()
    return {"id": topic_id, "deleted": True}


# ---------------------------------------------------------------------------
# Circle settings
# ---------------------------------------------------------------------------

def update_circle_settings(
    db: DbSession,
    viewer_id: str,
    circle_id: str,
    chat_time: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Change the chat time ("HH:MM") and/or the IANA timezone. The invitation
    scheduler reads them on its next pass; a day that already has its
    invitation is not changed."""
    require_admin(db, viewer_id, circle_id)
    if chat_time is not None and not _CHAT_TIME.match(chat_time):
        raise ValueError("chat_time must be HH:MM (24-hour).")
    if timezone is not None:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError("timezone must be an IANA name, for example Europe/Istanbul.")

    circle = db.get(Circle, circle_id)
    if chat_time is not None:
        circle.chat_time = chat_time
    if timezone is not None:
        circle.timezone = timezone
    db.commit()
    return {"id": circle.id, "chat_time": circle.chat_time, "timezone": circle.timezone}
