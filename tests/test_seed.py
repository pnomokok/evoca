"""
Tests for the seed safety check in core.seed.

The seed's engine, session factory and init_db are pointed at a temporary
SQLite file, so data/evoca.db is never touched.

Coverage:
  - seeding an empty database works, and re-seeding a seed-only database works
  - a database with a recorded (non-seed) session is refused, with a message
    naming the session, and nothing is deleted
  - --force wipes it anyway
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.seed as seed
from core.enums import SessionKind, SessionStart
from core.models import Base, Segment, Session as OrmSession


@pytest.fixture
def seed_db(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path / 'seed_test.db'}")
    Sess = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(seed, "engine", eng)
    monkeypatch.setattr(seed, "SessionLocal", Sess)
    monkeypatch.setattr(seed, "init_db", lambda: Base.metadata.create_all(bind=eng))
    yield Sess
    eng.dispose()


def _add_recorded_session(Sess) -> str:
    with Sess() as db:
        circle_id = db.query(OrmSession).first().circle_id
        sess = OrmSession(circle_id=circle_id, kind=SessionKind.solo,
                          started_by=SessionStart.spontaneous, participant_ids=[],
                          audio_path=None, started_at="2026-10-15T19:03:12+00:00",
                          ended_at="2026-10-15T19:03:48+00:00")
        db.add(sess)
        db.flush()
        db.add(Segment(session_id=sess.id, speaker_id=None, start_ms=0, end_ms=100,
                       transcript="A real conversation."))
        db.commit()
        return sess.id


def test_seed_empty_database_and_reseed(seed_db):
    assert seed.main([]) == 0
    assert seed.find_recorded_sessions() == []
    assert seed.main([]) == 0  # only the seed's own session exists
    with seed_db() as db:
        assert db.query(OrmSession).count() == 1


def test_seed_refuses_when_recorded_session_exists(seed_db, capsys):
    seed.main([])
    recorded_id = _add_recorded_session(seed_db)

    assert seed.main([]) == 1
    out = capsys.readouterr().out
    assert "Refusing to seed" in out
    assert recorded_id in out
    assert "(1 segments)" in out
    assert "--force" in out
    with seed_db() as db:
        assert db.get(OrmSession, recorded_id) is not None

    with pytest.raises(seed.SeedRefused):
        seed.reset_and_seed()


def test_seed_force_wipes_recorded_session(seed_db):
    seed.main([])
    recorded_id = _add_recorded_session(seed_db)

    assert seed.main(["--force"]) == 0
    with seed_db() as db:
        assert db.get(OrmSession, recorded_id) is None
        assert db.query(OrmSession).count() == 1
