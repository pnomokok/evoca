"""
Business logic for the admin panel endpoints (docs/ARCHITECTURE.md "REST API").

  require_admin           every admin endpoint
  list_family_topics      GET    /api/admin/sensitive-topics
  add_family_topic        POST   /api/admin/sensitive-topics
  delete_family_topic     DELETE /api/admin/sensitive-topics/{id}
  update_circle_settings  PATCH  /api/admin/circle
  add_member              POST   /api/admin/members
  update_member           PATCH  /api/admin/members/{person_id}
  remove_member           DELETE /api/admin/members/{person_id}

Privacy rules applied here:
- Only the circle's admin gets past require_admin; everyone else gets the same
  Forbidden, whatever their role.
- Topics the center refused herself (source "speaker") never leave this module:
  they are not listed, not counted, and their ids raise the same NotFound as a
  missing id. The duplicate check only looks at family topics, so adding a text
  that matches a speaker topic does not reveal it.
- Deleting a topic does not re-evaluate questions it already filtered.
- Removing a member deletes only the membership: the person and their stories
  stay, and can_see() decides access as before (they are no longer a member).
  The center cannot be removed or changed; the last admin cannot be removed
  or demoted. Removing a member also revokes their invite link and sessions.

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
from core.models import Circle, Membership, Person, SensitiveTopic
from core.services.circles import clean_birth_year, clean_name
from core.services.session_tools import _meaningful_words

_MAX_TOPIC_CHARS = 200
_CHAT_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

ADMIN_ONLY = "Only an admin of this circle can do this."
TOPIC_NOT_FOUND = "Topic not found."
MEMBER_NOT_FOUND = "Member not found."
_MEMBER_ROLES = {Role.member.value, Role.admin.value}


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


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------

def _member_dict(db: DbSession, m: Membership) -> dict[str, Any]:
    p = db.get(Person, m.person_id)
    return {"id": m.person_id, "name": p.name if p else None, "birth_year": p.birth_year if p else None,
            "role": m.role, "relation_to_center": m.relation_to_center}


def _clean_role(value: Any) -> str:
    if value not in _MEMBER_ROLES:
        raise ValueError("role must be 'member' or 'admin'.")
    return value


def _membership(db: DbSession, circle_id: str, person_id: str) -> Membership:
    m = db.get(Membership, (person_id, circle_id))
    if m is None:
        raise NotFound(MEMBER_NOT_FOUND)
    return m


def _admin_count(db: DbSession, circle_id: str) -> int:
    return db.query(Membership).filter(Membership.circle_id == circle_id,
                                       Membership.role == Role.admin).count()


def _guard(db: DbSession, m: Membership, losing_admin: bool) -> None:
    if m.role == Role.center:
        raise ValueError("The center of the circle cannot be removed or changed.")
    if losing_admin and m.role == Role.admin and _admin_count(db, m.circle_id) <= 1:
        raise ValueError("The circle needs at least one admin.")


def add_member(
    db: DbSession, viewer_id: str, circle_id: str,
    name: Any, birth_year: Any, relation_to_center: Any, role_: Any,
) -> dict[str, Any]:
    """Add a new person to the circle as a member or an admin."""
    require_admin(db, viewer_id, circle_id)
    name = clean_name(name, "name")
    # Optional for a member: empty means unknown; a given year is still checked.
    birth_year = None if birth_year in (None, "") else clean_birth_year(birth_year, "birth_year")
    relation = clean_name(relation_to_center, "relation_to_center")
    role_ = _clean_role(role_)
    person = Person(name=name, birth_year=birth_year)
    db.add(person)
    db.flush()
    m = Membership(person_id=person.id, circle_id=circle_id, role=role_, relation_to_center=relation)
    db.add(m)
    db.commit()
    return _member_dict(db, m)


def update_member(
    db: DbSession, viewer_id: str, circle_id: str, person_id: str,
    relation_to_center: Any = None, role_: Any = None,
) -> dict[str, Any]:
    """Change a member's relation_to_center and/or role (member | admin)."""
    require_admin(db, viewer_id, circle_id)
    m = _membership(db, circle_id, person_id)
    relation = clean_name(relation_to_center, "relation_to_center") if relation_to_center is not None else None
    new_role = _clean_role(role_) if role_ is not None else None
    _guard(db, m, losing_admin=new_role == Role.member)
    if relation is not None:
        m.relation_to_center = relation
    if new_role is not None:
        m.role = new_role
    db.commit()
    return _member_dict(db, m)


def remove_member(db: DbSession, viewer_id: str, circle_id: str, person_id: str) -> dict[str, Any]:
    """Remove the membership only; the person and their stories stay."""
    require_admin(db, viewer_id, circle_id)
    m = _membership(db, circle_id, person_id)
    _guard(db, m, losing_admin=True)
    from core.services.auth import revoke_person_links   # auth imports this module
    revoke_person_links(db, circle_id, person_id)
    db.delete(m)
    db.commit()
    return {"id": person_id, "removed": True}
