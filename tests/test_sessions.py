"""
Tests for core.services.sessions — start_session, add_segment, end_session.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from core.models import Base, Circle, Membership, Person, Segment
from core.models import Session as OrmSession
from core.enums import (
    CircleStatus, Role, SessionKind, SessionStart,
)
from core.services.sessions import add_segment, end_session, start_session


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------

def _enable_fk(dbapi_conn, _record):
    c = dbapi_conn.cursor()
    c.execute("PRAGMA foreign_keys=ON")
    c.close()


@pytest.fixture(scope="function")
def db():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    event.listen(eng, "connect", _enable_fk)
    Base.metadata.create_all(bind=eng)
    Sess = sessionmaker(bind=eng, autocommit=False, autoflush=False, expire_on_commit=False)
    session = Sess()
    yield session
    session.close()
    Base.metadata.drop_all(bind=eng)


@pytest.fixture(scope="function")
def circle_and_person(db):
    person = Person(name="Fatma", birth_year=1948, language="en")
    db.add(person)
    db.flush()
    circle = Circle(
        name="Test Circle",
        center_person_id=person.id,
        status=CircleStatus.active,
        chat_time="10:00",
        timezone="Europe/Istanbul",
    )
    db.add(circle)
    db.flush()
    db.add(Membership(person_id=person.id, circle_id=circle.id, role=Role.center))
    db.commit()
    return circle, person


# ---------------------------------------------------------------------------
# start_session
# ---------------------------------------------------------------------------

class TestStartSession:
    def test_creates_session_row(self, db, circle_and_person):
        circle, person = circle_and_person
        sess = start_session(db, circle.id, SessionStart.spontaneous, [person.id])
        db.commit()

        row = db.get(OrmSession, sess.id)
        assert row is not None
        assert row.circle_id == circle.id
        assert row.started_by == SessionStart.spontaneous
        assert row.ended_at is None
        assert person.id in row.participant_ids

    def test_session_kind_is_solo(self, db, circle_and_person):
        circle, person = circle_and_person
        sess = start_session(db, circle.id, SessionStart.invitation, [person.id])
        db.commit()
        assert sess.kind == SessionKind.solo

    def test_participant_ids_copied(self, db, circle_and_person):
        circle, person = circle_and_person
        ids = [person.id, "fake-id-2"]
        sess = start_session(db, circle.id, SessionStart.spontaneous, ids)
        db.commit()
        assert set(sess.participant_ids) == set(ids)


# ---------------------------------------------------------------------------
# add_segment
# ---------------------------------------------------------------------------

class TestAddSegment:
    def test_creates_segment_row(self, db, circle_and_person):
        circle, person = circle_and_person
        sess = start_session(db, circle.id, SessionStart.spontaneous, [person.id])
        db.commit()

        seg = add_segment(db, sess.id, person.id, "Hello there.", 0, 2000)
        db.commit()

        row = db.get(Segment, seg.id)
        assert row.transcript == "Hello there."
        assert row.start_ms == 0
        assert row.end_ms == 2000
        assert row.is_private is False
        assert row.words == []

    def test_agent_segment_has_none_speaker(self, db, circle_and_person):
        circle, person = circle_and_person
        sess = start_session(db, circle.id, SessionStart.spontaneous, [person.id])
        db.commit()

        seg = add_segment(db, sess.id, None, "Agent reply.", 2100, 4000)
        db.commit()

        row = db.get(Segment, seg.id)
        assert row.speaker_id is None

    def test_words_stored(self, db, circle_and_person):
        circle, person = circle_and_person
        sess = start_session(db, circle.id, SessionStart.spontaneous, [person.id])
        db.commit()

        words = [{"w": "Hello", "start_ms": 0, "end_ms": 500}]
        seg = add_segment(db, sess.id, person.id, "Hello.", 0, 600, words=words)
        db.commit()

        row = db.get(Segment, seg.id)
        assert row.words == words

    def test_private_flag(self, db, circle_and_person):
        circle, person = circle_and_person
        sess = start_session(db, circle.id, SessionStart.spontaneous, [person.id])
        db.commit()

        seg = add_segment(
            db, sess.id, person.id, "Private memory.", 0, 1000, is_private=True
        )
        db.commit()

        row = db.get(Segment, seg.id)
        assert row.is_private is True


# ---------------------------------------------------------------------------
# end_session
# ---------------------------------------------------------------------------

class TestEndSession:
    def test_sets_ended_at(self, db, circle_and_person):
        circle, person = circle_and_person
        sess = start_session(db, circle.id, SessionStart.spontaneous, [person.id])
        db.commit()
        assert sess.ended_at is None

        end_session(db, sess.id)
        db.commit()

        row = db.get(OrmSession, sess.id)
        assert row.ended_at is not None

    def test_nonexistent_session_raises(self, db, circle_and_person):
        with pytest.raises(ValueError, match="not found"):
            end_session(db, "00000000-0000-0000-0000-000000000000")
