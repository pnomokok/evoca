"""
Circles: picking the viewer's circle, the people of one circle, and creating a
new circle (docs/PROJECT.md "REST uçları").

  viewer_membership  every panel and device endpoint (optional X-Circle-Id)
  people_in_circle   GET  /api/people?circle_id=
  demo_circle        GET  /api/circles/demo
  create_circle      POST /api/circles

There is no authentication in the preview (Bilinen sınırlar): a circle id acts
as an unlisted link. people_in_circle returns names, roles and birth years of
that one circle only, never story data, and never anyone from another circle.

Functions take an open SQLAlchemy session and commit their own writes.
"""

from __future__ import annotations

import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session as DbSession

from core.clock import now_utc
from core.enums import CircleStatus, Role
from core.models import Circle, Membership, Person

MAX_NAME_CHARS = 60
MIN_BIRTH_YEAR = 1900
_CHAT_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class NotFound(Exception):
    """No such circle."""


def viewer_membership(db: DbSession, person_id: str, circle_id: str | None = None) -> Membership | None:
    """The membership a request acts in: the one in circle_id when given, else
    the person's first membership. None when the person is not a member there."""
    if not person_id:
        return None
    q = db.query(Membership).filter(Membership.person_id == person_id)
    if circle_id:
        q = q.filter(Membership.circle_id == circle_id)
    return q.order_by(Membership.circle_id).first()


def people_in_circle(db: DbSession, circle_id: str) -> list[dict[str, Any]]:
    """The circle's people, by name. Raises NotFound for an unknown circle."""
    if not circle_id or db.get(Circle, circle_id) is None:
        raise NotFound("Circle not found.")
    rows = (
        db.query(Person, Membership)
        .join(Membership, Membership.person_id == Person.id)
        .filter(Membership.circle_id == circle_id)
        .order_by(Person.name, Person.id)
        .all()
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "role": m.role,
            "relation_to_center": m.relation_to_center,
            "birth_year": p.birth_year,
        }
        for p, m in rows
    ]


def demo_circle(db: DbSession) -> dict[str, Any]:
    """{id, name} of the seeded demo circle. Raises NotFound if there is none."""
    circle = db.query(Circle).filter(Circle.is_demo.is_(True)).order_by(Circle.id).first()
    if circle is None:
        raise NotFound("No demo circle.")
    return {"id": circle.id, "name": circle.name}


# ---------------------------------------------------------------------------
# Validation (ValueError -> 400 in the routers)
# ---------------------------------------------------------------------------

def clean_name(value: Any, field: str) -> str:
    """A name or relation of 1-60 characters, inner whitespace collapsed."""
    if not isinstance(value, str):
        raise ValueError(f"{field} is required.")
    text = " ".join(value.split())
    if not text:
        raise ValueError(f"{field} is required.")
    if len(text) > MAX_NAME_CHARS:
        raise ValueError(f"{field} must be at most {MAX_NAME_CHARS} characters.")
    return text


def clean_birth_year(value: Any, field: str) -> int:
    this_year = now_utc().year
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_BIRTH_YEAR <= value <= this_year:
        raise ValueError(f"{field} must be a year between {MIN_BIRTH_YEAR} and {this_year}.")
    return value


def clean_timezone(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("timezone must be an IANA name, for example Europe/Istanbul.")
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError("timezone must be an IANA name, for example Europe/Istanbul.")
    return value


def clean_chat_time(value: Any) -> str:
    if not isinstance(value, str) or not _CHAT_TIME.match(value):
        raise ValueError("chat_time must be HH:MM (24-hour).")
    return value


def _section(body: dict[str, Any], key: str) -> dict[str, Any]:
    value = body.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} is required.")
    return value


# ---------------------------------------------------------------------------
# POST /api/circles
# ---------------------------------------------------------------------------

def create_circle(db: DbSession, body: Any) -> dict[str, str]:
    """Create a circle with its center (role center) and its creator (role admin).

    body: {circle_name, timezone, chat_time, center: {name, birth_year},
           creator: {name, birth_year, relation_to_center}}.
    Everything is validated before anything is written.
    """
    if not isinstance(body, dict):
        raise ValueError("A JSON object is required.")
    circle_name = clean_name(body.get("circle_name"), "circle_name")
    timezone = clean_timezone(body.get("timezone"))
    chat_time = clean_chat_time(body.get("chat_time"))
    center = _section(body, "center")
    creator = _section(body, "creator")
    center_name = clean_name(center.get("name"), "center.name")
    center_year = clean_birth_year(center.get("birth_year"), "center.birth_year")
    creator_name = clean_name(creator.get("name"), "creator.name")
    creator_year = clean_birth_year(creator.get("birth_year"), "creator.birth_year")
    creator_relation = clean_name(creator.get("relation_to_center"), "creator.relation_to_center")

    center_p = Person(name=center_name, birth_year=center_year)
    creator_p = Person(name=creator_name, birth_year=creator_year)
    db.add_all([center_p, creator_p])
    db.flush()
    circle = Circle(
        name=circle_name,
        center_person_id=center_p.id,
        status=CircleStatus.active,
        chat_time=chat_time,
        timezone=timezone,
        is_demo=False,
    )
    db.add(circle)
    db.flush()
    db.add_all([
        Membership(person_id=center_p.id, circle_id=circle.id, role=Role.center, relation_to_center=None),
        Membership(person_id=creator_p.id, circle_id=circle.id, role=Role.admin,
                   relation_to_center=creator_relation),
    ])
    db.commit()
    return {"circle_id": circle.id, "center_id": center_p.id, "creator_id": creator_p.id}
