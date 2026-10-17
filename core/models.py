"""
SQLAlchemy 2.0 ORM models — exact field names from docs/PROJECT.md "Veri modeli > Varlıklar".

Rules applied:
- All IDs are UUID strings.
- All timestamps are UTC ISO 8601 strings.
- Audio positions are integer milliseconds.
- JSON columns (participant_ids, words, sources, access, answer) use MutableDict /
  MutableList via sqlalchemy.ext.mutable so in-place mutations are tracked and saved.
- Composite primary keys follow the doc's "PK (...)" notation.
"""

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.types import JSON

from core.clock import now_utc

from core.enums import (
    AccessType,
    CircleStatus,
    Emoji,
    InvitationStatus,
    LifePeriod,
    LinkReason,
    LinkSource,
    LinkStatus,
    PeriodSource,
    QuestionSource,
    QuestionStatus,
    Role,
    SessionKind,
    SessionStart,
    StoryKind,
    StoryStatus,
    TopicSource,
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return now_utc().isoformat()


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Person
# ---------------------------------------------------------------------------

class Person(Base):
    __tablename__ = "person"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    birth_year = Column(Integer, nullable=True)
    language = Column(String, nullable=False, default="en")  # "tr" | "en"
    created_at = Column(String, nullable=False, default=_now_iso)

    memberships = relationship("Membership", back_populates="person")


# ---------------------------------------------------------------------------
# Circle
# ---------------------------------------------------------------------------

class Circle(Base):
    __tablename__ = "circle"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    center_person_id = Column(String, ForeignKey("person.id"), nullable=False)
    status = Column(String, nullable=False, default=CircleStatus.active)
    chat_time = Column(String, nullable=False)   # "HH:MM"
    timezone = Column(String, nullable=False)    # e.g. "Europe/Istanbul"
    # The seeded demo family (GET /api/circles/demo); circles made with POST /api/circles are not.
    is_demo = Column(Boolean, nullable=False, default=False, server_default="0")

    memberships = relationship("Membership", back_populates="circle")


# ---------------------------------------------------------------------------
# Membership  — composite PK (person_id, circle_id)
# ---------------------------------------------------------------------------

class Membership(Base):
    __tablename__ = "membership"

    person_id = Column(String, ForeignKey("person.id"), primary_key=True)
    circle_id = Column(String, ForeignKey("circle.id"), primary_key=True)
    role = Column(String, nullable=False)                # Role enum value
    relation_to_center = Column(String, nullable=True)   # e.g. "daughter", "grandson"; None for the center

    person = relationship("Person", back_populates="memberships")
    circle = relationship("Circle", back_populates="memberships")


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class Session(Base):
    __tablename__ = "session"

    id = Column(String, primary_key=True, default=_uuid)
    circle_id = Column(String, ForeignKey("circle.id"), nullable=False)
    kind = Column(String, nullable=False)           # SessionKind
    started_by = Column(String, nullable=False)     # SessionStart
    # JSON list of person_id strings
    participant_ids = Column(MutableList.as_mutable(JSON), nullable=False, default=list)
    audio_path = Column(String, nullable=True)
    started_at = Column(String, nullable=False, default=_now_iso)
    ended_at = Column(String, nullable=True)

    segments = relationship("Segment", back_populates="session")


# ---------------------------------------------------------------------------
# Segment — one person's uninterrupted speech block
# ---------------------------------------------------------------------------

class Segment(Base):
    __tablename__ = "segment"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("session.id"), nullable=False)
    speaker_id = Column(String, ForeignKey("person.id"), nullable=True)  # None = agent
    start_ms = Column(Integer, nullable=False)
    end_ms = Column(Integer, nullable=False)
    transcript = Column(Text, nullable=False, default="")
    # JSON list of {w, start_ms, end_ms} dicts
    words = Column(MutableList.as_mutable(JSON), nullable=False, default=list)
    is_private = Column(Boolean, nullable=False, default=False)

    session = relationship("Session", back_populates="segments")


# ---------------------------------------------------------------------------
# Story
# ---------------------------------------------------------------------------

class Story(Base):
    __tablename__ = "story"

    id = Column(String, primary_key=True, default=_uuid)
    circle_id = Column(String, ForeignKey("circle.id"), nullable=False)
    teller_id = Column(String, ForeignKey("person.id"), nullable=False)
    kind = Column(String, nullable=False)                    # StoryKind
    original_story_id = Column(String, ForeignKey("story.id"), nullable=True)
    title = Column(String, nullable=False)
    ai_summary = Column(Text, nullable=True)
    # JSON list of {session_id, start_ms, end_ms} dicts
    sources = Column(MutableList.as_mutable(JSON), nullable=False, default=list)
    place = Column(String, nullable=True)
    stated_year = Column(Integer, nullable=True)
    # JSON dict: {type: AccessType, person_ids: [id]}
    # Column is named "access" exactly as in the doc.
    access = Column(MutableDict.as_mutable(JSON), nullable=False,
                    default=lambda: {"type": AccessType.circle, "person_ids": []})
    status = Column(String, nullable=False, default=StoryStatus.pending)
    publish_at = Column(String, nullable=False, default=_now_iso)
    created_at = Column(String, nullable=False, default=_now_iso)

    subjects = relationship("StorySubject", back_populates="story")

    # Convenience properties so access-control code reads exactly as the doc's pseudo-code:
    #   story.access.type  and  story.access.person_ids
    class _AccessProxy:
        """Thin wrapper so access.type and access.person_ids work on a plain dict."""
        __slots__ = ("_d",)

        def __init__(self, d: dict[str, Any]) -> None:
            self._d = d

        @property
        def type(self) -> str | None:
            # Return None (not a default type) when the key is absent so that
            # can_see() falls through to "return False" — fail closed.
            return self._d.get("type", None)

        @property
        def person_ids(self) -> list[str]:
            return self._d.get("person_ids", [])

    @property
    def access_proxy(self) -> "_AccessProxy":
        """Use story.access_proxy.type / .person_ids in access-control logic."""
        return Story._AccessProxy(self.access)


# ---------------------------------------------------------------------------
# StorySubject  — composite PK (story_id, person_id)
# ---------------------------------------------------------------------------

class StorySubject(Base):
    __tablename__ = "story_subject"

    story_id = Column(String, ForeignKey("story.id"), primary_key=True)
    person_id = Column(String, ForeignKey("person.id"), primary_key=True)
    period = Column(String, nullable=False)           # LifePeriod
    period_source = Column(String, nullable=False, default=PeriodSource.ai)
    corrected_by = Column(String, nullable=True)      # person_id who corrected

    story = relationship("Story", back_populates="subjects")


# ---------------------------------------------------------------------------
# StoryPhoto  — one per story for now (a new upload replaces the old one)
# ---------------------------------------------------------------------------

class StoryPhoto(Base):
    __tablename__ = "story_photo"

    id = Column(String, primary_key=True, default=_uuid)
    story_id = Column(String, ForeignKey("story.id"), nullable=False, index=True)
    path = Column(String, nullable=False)          # data/photos/<uuid>.jpg, never a client name
    caption = Column(String, nullable=True)        # at most 120 characters
    uploaded_by = Column(String, ForeignKey("person.id"), nullable=False)
    created_at = Column(String, nullable=False, default=_now_iso)


# ---------------------------------------------------------------------------
# StoryLink
# ---------------------------------------------------------------------------

class StoryLink(Base):
    __tablename__ = "story_link"

    id = Column(String, primary_key=True, default=_uuid)
    from_story_id = Column(String, ForeignKey("story.id"), nullable=False)
    to_story_id = Column(String, ForeignKey("story.id"), nullable=False)
    reason = Column(String, nullable=False)    # LinkReason
    source = Column(String, nullable=False)    # LinkSource
    status = Column(String, nullable=False, default=LinkStatus.suggested)


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------

class Question(Base):
    __tablename__ = "question"

    id = Column(String, primary_key=True, default=_uuid)
    circle_id = Column(String, ForeignKey("circle.id"), nullable=False)
    target_person_id = Column(String, ForeignKey("person.id"), nullable=False)
    asker_id = Column(String, ForeignKey("person.id"), nullable=True)  # None = agent
    text = Column(Text, nullable=False)
    source = Column(String, nullable=False)             # QuestionSource
    period = Column(String, nullable=True)              # LifePeriod | None
    status = Column(String, nullable=False, default=QuestionStatus.waiting)
    # JSON dict: {story_id, session_id, start_ms, end_ms} | None stored as null
    answer = Column(MutableDict.as_mutable(JSON), nullable=True)
    created_at = Column(String, nullable=False, default=_now_iso)


# ---------------------------------------------------------------------------
# SensitiveTopic
# ---------------------------------------------------------------------------

class SensitiveTopic(Base):
    __tablename__ = "sensitive_topic"

    id = Column(String, primary_key=True, default=_uuid)
    circle_id = Column(String, ForeignKey("circle.id"), nullable=False)
    text = Column(Text, nullable=False)
    # "speaker" topics are never returned by a panel endpoint (docs/PROJECT.md).
    source = Column(String, nullable=False, default=TopicSource.family,
                    server_default=TopicSource.family.value)
    added_by = Column(String, ForeignKey("person.id"), nullable=False)
    created_at = Column(String, nullable=False, default=_now_iso)


# ---------------------------------------------------------------------------
# Reaction  — composite PK (story_id, person_id, emoji)
# ---------------------------------------------------------------------------

class Reaction(Base):
    __tablename__ = "reaction"

    story_id = Column(String, ForeignKey("story.id"), primary_key=True)
    person_id = Column(String, ForeignKey("person.id"), primary_key=True)
    emoji = Column(String, primary_key=True)     # Emoji enum value
    delivered_to_center = Column(Boolean, nullable=False, default=False)
    created_at = Column(String, nullable=False, default=_now_iso)


# ---------------------------------------------------------------------------
# Invitation
# ---------------------------------------------------------------------------

class Invitation(Base):
    __tablename__ = "invitation"

    id = Column(String, primary_key=True, default=_uuid)
    circle_id = Column(String, ForeignKey("circle.id"), nullable=False)
    person_id = Column(String, ForeignKey("person.id"), nullable=False)
    date = Column(String, nullable=False)       # "YYYY-MM-DD"
    reason = Column(Text, nullable=False)
    status = Column(String, nullable=False, default=InvitationStatus.sent)

    # At most one invitation per circle per local date, also under concurrent
    # scheduler passes (core/services/invitations.py).
    __table_args__ = (
        Index("uq_invitation_circle_date", "circle_id", "date", unique=True),
    )


# ---------------------------------------------------------------------------
# DemoClock (demo mode only; not part of the family's data)
# ---------------------------------------------------------------------------

class DemoClock(Base):
    """The demo clock's offset, one row (id 1). Kept in the database so the API
    and the MCP server, two processes, agree on now_utc() (core/clock.py)."""
    __tablename__ = "demo_clock"

    id = Column(Integer, primary_key=True)
    offset_seconds = Column(Integer, nullable=False, default=0)
