"""
Tests for the demo controls (server/routers/demo.py, core/services/demo.py, core/clock.py).

Each test runs on the real seed in a temp-file database with the working
directory in tmp_path (so the seed's audio and the deleted files stay there).

Coverage:
  without EVOCA_DEMO_MODE=1 every endpoint is a 404 and the clock has no offset
  advance        moves now_utc(), also in another process reading the same
                 database (like the MCP server); publishes the pending seed
                 story after 24 h and creates the next day's invitation;
                 hours outside 1-72 are a 400
  clock          {now, offset_hours}
  reset          restores the seed, clears the offset, ends live sessions,
                 deletes the files of non-seed sessions and photos, keeps the
                 seed audio; refuses every database but data/demo.db
  loop timeline  question, next morning, answer, +1 day publish, reaction,
                 next morning: that morning's reason is the reaction, ahead of
                 the archivist's waiting gap question
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import core.db as cdb
import core.seed as seed
from core import clock
from core.enums import (
    InvitationStatus, QuestionSource, QuestionStatus, SessionKind, SessionStart, StoryKind, StoryStatus,
)
from core.models import (
    Base, Circle, DemoClock, Invitation, Person, Question, Reaction, Session as OrmSession, Story, StoryPhoto,
)
from core.services.archive_tools import record_answer_data
from core.services.invitations import REASON_AGENT_QUESTION
from core.services import demo as demo_svc
from server.session_store import SessionStore

REPO = Path(__file__).resolve().parent.parent
BASE_NOW = "2026-10-20T05:00:00+00:00"      # 08:00 in Istanbul, before the 10:00 chat time


def _fk(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


@pytest.fixture
def demo(tmp_path, monkeypatch):
    """The seed in tmp_path/demo.db, demo mode on, the app wired to it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVOCA_DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_NOW", BASE_NOW)
    monkeypatch.setattr(clock, "OFFSET_CACHE_S", 0.0)   # always read the database; no wait
    clock.clear_offset_cache()

    db_path = tmp_path / "demo.db"
    eng = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    event.listen(eng, "connect", _fk)
    Session = sessionmaker(bind=eng, autocommit=False, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(cdb, "engine", eng)
    monkeypatch.setattr(cdb, "SessionLocal", Session)
    monkeypatch.setattr(cdb, "_abs_path", db_path)
    monkeypatch.setattr(cdb, "_in_memory", False)
    monkeypatch.setattr(demo_svc, "DEMO_DB", db_path)      # stands in for data/demo.db
    monkeypatch.setattr(seed, "engine", eng)
    monkeypatch.setattr(seed, "SessionLocal", Session)
    import server.routers.demo as demo_r
    import server.routers.device as dev_r
    import server.routers.panel as pan_r
    for mod in (demo_r, pan_r):
        monkeypatch.setattr(mod, "SessionLocal", Session)

    seed.reset_and_seed(force=True)

    from server.app import app
    store = SessionStore()
    app.dependency_overrides[dev_r._get_store] = lambda: store
    yield app, Session, store, db_path
    app.dependency_overrides.clear()
    clock.clear_offset_cache()
    eng.dispose()


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _base() -> datetime:
    return datetime.fromisoformat(BASE_NOW)


# ---------------------------------------------------------------------------
# Demo mode off
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_endpoints_are_404_without_demo_mode(demo, monkeypatch):
    app, Session, *_ = demo
    monkeypatch.delenv("EVOCA_DEMO_MODE")
    async with _client(app) as c:
        assert (await c.get("/api/demo/clock")).status_code == 404
        assert (await c.post("/api/demo/advance", json={"hours": 24})).status_code == 404
        assert (await c.post("/api/demo/reset")).status_code == 404
        assert (await c.get("/api/demo/status")).status_code == 404
    with Session() as db:
        assert db.get(DemoClock, 1) is None
        assert db.query(Person).count() == 4


def test_a_failed_offset_read_is_not_cached(demo, monkeypatch):
    # With a 2 s cache, a failed first read must not stick as offset 0.
    _, Session, *_ = demo
    monkeypatch.setattr(clock, "OFFSET_CACHE_S", 60.0)
    with Session() as db:
        db.add(DemoClock(id=1, offset_seconds=24 * 3600))
        db.commit()
    clock.set_cached_offset(0)
    clock.clear_offset_cache()

    def broken():
        raise RuntimeError("database is locked")
    monkeypatch.setattr(cdb, "SessionLocal", broken)
    assert clock.now_utc() == _base()                    # last value, not cached
    monkeypatch.setattr(cdb, "SessionLocal", Session)
    assert clock.now_utc() == _base() + timedelta(hours=24)


def test_no_offset_without_demo_mode(demo, monkeypatch):
    _, Session, *_ = demo
    with Session() as db:
        db.add(DemoClock(id=1, offset_seconds=48 * 3600))
        db.commit()
    assert clock.now_utc() == _base() + timedelta(hours=48)
    monkeypatch.delenv("EVOCA_DEMO_MODE")
    assert clock.now_utc() == _base()


# ---------------------------------------------------------------------------
# Advance and clock
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_advance_publishes_and_invites_and_moves_the_clock(demo):
    app, Session, _, db_path = demo
    with Session() as db:
        pending = db.query(Story).filter(Story.status == StoryStatus.pending).one()  # publish_at = +23 h

    async with _client(app) as c:
        body = (await c.post("/api/demo/advance", json={"hours": 24})).json()
        clock_body = (await c.get("/api/demo/clock")).json()
    expected = _base() + timedelta(hours=24)
    assert datetime.fromisoformat(body["now"]) == expected
    assert body == {"now": expected.isoformat(), "offset_hours": 24.0, "archive_wait": "none"}
    assert clock_body == {"now": expected.isoformat(), "offset_hours": 24.0}

    with Session() as db:
        assert db.get(Story, pending.id).status == StoryStatus.published
        # 2026-10-21 08:00 in Istanbul is before the chat time: no invitation yet.
        assert db.query(Invitation).filter(Invitation.date == "2026-10-21").count() == 0

    async with _client(app) as c:
        body = (await c.post("/api/demo/advance", json={"hours": 3})).json()   # 11:00 in Istanbul
    assert body["offset_hours"] == 27.0
    with Session() as db:
        inv = db.query(Invitation).filter(Invitation.date == "2026-10-21").one()
        assert inv.status == InvitationStatus.sent

    # Another process on the same database (like the MCP server) sees the new time.
    env = {**os.environ, "EVOCA_DB_PATH": str(db_path), "EVOCA_DEMO_MODE": "1", "DEMO_NOW": BASE_NOW,
           "PYTHONPATH": str(REPO)}
    out = subprocess.run(
        [sys.executable, "-c", "from core.clock import now_utc; print(now_utc().isoformat())"],
        env=env, cwd=REPO, capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert datetime.fromisoformat(out.stdout.strip()) == _base() + timedelta(hours=27)


@pytest.mark.anyio
async def test_advance_offset_is_read_from_the_database(demo):
    # A process that did not make the advance itself (fresh cache) gets the offset.
    app, Session, *_ = demo
    async with _client(app) as c:
        await c.post("/api/demo/advance", json={"hours": 5})
    clock.set_cached_offset(0)
    clock.clear_offset_cache()
    assert clock.now_utc() == _base() + timedelta(hours=5)


@pytest.mark.anyio
@pytest.mark.parametrize("hours", [0, 0.5, 73, -1])
async def test_advance_rejects_hours_out_of_range(demo, hours):
    app, Session, *_ = demo
    async with _client(app) as c:
        r = await c.post("/api/demo/advance", json={"hours": hours})
    assert r.status_code == 400
    assert clock.now_utc() == _base()


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

class _Live:
    def __init__(self, session_id):
        self.session_id = session_id
        self.closed = False
        self.db = self

    def close(self):
        self.closed = True


@pytest.mark.anyio
async def test_fathers_workshop_plays_for_ayse_and_is_hidden_from_elif_and_can(demo, monkeypatch):
    app, Session, _, _ = demo
    import server.routers.audio as audio_r
    monkeypatch.setattr(audio_r, "SessionLocal", Session)
    with Session() as db:
        people = {p.name.split()[0]: p.id for p in db.query(Person).all()}
        story = db.query(Story).filter(Story.title == "Father's Workshop").one()
    (src,) = story.sources
    audio = f"/api/audio/{src['session_id']}?start={src['start_ms']}&end={src['end_ms']}"
    async with _client(app) as c:
        r = await c.get(f"/api/stories/{story.id}", headers={"x-person-id": people["Ayşe"]})
        assert r.status_code == 200 and r.json()["audio"]
        r = await c.get(audio, headers={"x-person-id": people["Ayşe"]})
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
        for who in ("Elif", "Can"):
            r = await c.get(f"/api/stories/{story.id}", headers={"x-person-id": people[who]})
            assert r.status_code == 404, who
            r = await c.get(audio, headers={"x-person-id": people[who]})
            assert r.status_code == 403, who


@pytest.mark.anyio
async def test_reset_restores_the_seed_and_deletes_recorded_files(demo, tmp_path):
    app, Session, store, _ = demo
    seed_audio = [Path("data") / "audio" / f"{sid}.wav" for sid in seed.SEED_SESSION_IDS]
    assert all(f.exists() for f in seed_audio)

    # A recorded session with audio, a TTS reply and a photo on a seed story.
    with Session() as db:
        fatma = db.query(Person).filter(Person.name == "Fatma Yilmaz").one()
        circle_id = db.get(OrmSession, seed.SEED_SESSION_ID).circle_id
        sess = OrmSession(circle_id=circle_id, kind=SessionKind.solo, started_by=SessionStart.spontaneous,
                          participant_ids=[fatma.id], audio_path="data/audio/recorded.wav",
                          started_at=BASE_NOW, ended_at=BASE_NOW)
        db.add(sess); db.flush()
        story = db.query(Story).first()
        Path("data/photos-demo").mkdir(parents=True, exist_ok=True)
        db.add(StoryPhoto(story_id=story.id, path="data/photos-demo/p1.jpg", uploaded_by=fatma.id))
        # Paths outside data/audio, data/tts and data/photos-demo are never deleted.
        db.add(OrmSession(circle_id=circle_id, kind=SessionKind.solo, started_by=SessionStart.spontaneous,
                          participant_ids=[fatma.id], audio_path="data/audio/../keep.db",
                          started_at=BASE_NOW, ended_at=BASE_NOW))
        db.add(StoryPhoto(story_id=story.id, path=str(tmp_path / "keep.txt"), uploaded_by=fatma.id))
        db.commit()
        files = [Path("data/audio/recorded.wav"), Path(f"data/tts/{sess.id}_1.mp3"), Path("data/photos-demo/p1.jpg")]
    Path("data/tts").mkdir(parents=True, exist_ok=True)
    for f in files:
        f.write_bytes(b"x")
    outside = tmp_path / "keep.txt"
    outside.write_bytes(b"x")
    outside_db = Path("data/keep.db")
    outside_db.write_bytes(b"x")
    live = _Live(sess.id)
    store.put(live)

    async with _client(app) as c:
        await c.post("/api/demo/advance", json={"hours": 30})
        r = await c.post("/api/demo/reset")
        clock_body = (await c.get("/api/demo/clock")).json()
    assert r.status_code == 200, r.text
    names = sorted(p["name"] for p in r.json())
    assert names == ["Ayşe Yilmaz", "Can Yilmaz", "Elif Yilmaz", "Fatma Yilmaz"]
    assert clock_body["offset_hours"] == 0
    assert datetime.fromisoformat(clock_body["now"]) == _base()

    assert len(store) == 0 and live.closed
    assert not any(f.exists() for f in files)
    assert all(f.exists() for f in seed_audio) and outside.exists() and outside_db.exists()
    with Session() as db:
        assert sorted(s.id for s in db.query(OrmSession).all()) == sorted(seed.SEED_SESSION_IDS)
        # Only the seed's own photos are back, and their files are there.
        photos = db.query(StoryPhoto).all()
        assert sorted(p.caption for p in photos) == sorted(c for *_, c in seed.SEED_PHOTOS)
        assert all(Path(p.path).exists() for p in photos)
        assert db.query(Story).filter(Story.status == StoryStatus.pending).count() == 1


@pytest.mark.anyio
@pytest.mark.parametrize("other", ["evoca.db", "browser.db", "demo_copy.db"])
async def test_reset_refuses_any_database_but_demo_db(demo, monkeypatch, other):
    app, Session, store, _ = demo
    monkeypatch.setattr(cdb, "_abs_path", REPO / "data" / other)
    live = _Live("s1")
    store.put(live)
    with Session() as db:
        people_before = db.query(Person).count()
        db.add(DemoClock(id=1, offset_seconds=3600))
        db.commit()

    async with _client(app) as c:
        r = await c.post("/api/demo/reset")
    assert r.status_code == 400
    assert other in r.json()["detail"] and "data/demo.db" in r.json()["detail"]
    assert len(store) == 1 and not live.closed
    with Session() as db:
        assert db.query(Person).count() == people_before
        assert db.get(DemoClock, 1).offset_seconds == 3600
    with pytest.raises(demo_svc.ResetRefused):
        demo_svc.reset()


# ---------------------------------------------------------------------------
# The demo loop, day by day (the stage walkthrough)
# ---------------------------------------------------------------------------

def _invitation_on(Session, date: str) -> Invitation:
    with Session() as db:
        return db.query(Invitation).filter(Invitation.date == date).one()


@pytest.mark.anyio
async def test_reaction_is_the_reason_the_morning_after_it_in_the_demo_loop(demo, monkeypatch):
    """Question, next morning, answer, +1 day publish, reaction, next morning: the
    reaction comes first even with the archivist's gap question still waiting."""
    app, Session, *_ = demo
    import server.routers.device as dev_r
    monkeypatch.setattr(dev_r, "SessionLocal", Session)
    with Session() as db:
        circle = db.query(Circle).one()
        fatma_id = circle.center_person_id
        elif_id = db.query(Person).filter(Person.name.like("Elif%")).one().id

    async with _client(app) as c:
        # Tuesday 08:00: Elif asks. Next morning: Wednesday 10:00 (the web's "Next morning").
        r = await c.post("/api/questions", headers={"X-Person-Id": elif_id},
                         json={"target_person_id": fatma_id, "text": "What games did you play as a child?"})
        assert r.status_code == 200, r.text
        question_id = r.json()["question"]["id"]
        await c.post("/api/demo/advance", json={"hours": 26})

    # Wednesday's chat, as the device and the archivist leave it: the seed reaction was told,
    # the question answered by a new pending story, and a gap question added.
    now = clock.now_utc()
    with Session() as db:
        for reaction in db.query(Reaction).all():
            reaction.delivered_to_center = True
        sess = OrmSession(circle_id=circle.id, kind=SessionKind.solo, started_by=SessionStart.invitation,
                          participant_ids=[fatma_id], started_at=now.isoformat(),
                          ended_at=(now + timedelta(minutes=5)).isoformat())
        db.add(sess); db.flush()
        story = Story(circle_id=circle.id, teller_id=fatma_id, kind=StoryKind.original,
                      title="Five Stones Under the Walnut Tree",
                      sources=[{"session_id": sess.id, "start_ms": 0, "end_ms": 20000}],
                      status=StoryStatus.pending, publish_at=(now + timedelta(hours=24)).isoformat(),
                      created_at=now.isoformat())
        db.add(story); db.flush()
        db.get(Question, question_id).status = QuestionStatus.asked
        record_answer_data(db, fatma_id, circle.id, question_id, story.id, 0, 20000)
        db.add(Question(circle_id=circle.id, target_person_id=fatma_id, asker_id=None,
                        text="What do you remember about your early married years?",
                        source=QuestionSource.gap, status=QuestionStatus.waiting))
        db.commit()
        story_id = story.id

    async with _client(app) as c:
        # +1 day: Thursday 10:00, the story is published; nothing new from the family yet.
        await c.post("/api/demo/advance", json={"hours": 24})
        assert _invitation_on(Session, "2026-10-22").reason == REASON_AGENT_QUESTION

        # Elif reacts on Thursday; next morning is Friday 10:00.
        r = await c.post(f"/api/stories/{story_id}/reactions", headers={"X-Person-Id": elif_id},
                         json={"emoji": "heart", "action": "add"})
        assert r.status_code == 200, r.text
        await c.post("/api/demo/advance", json={"hours": 24})

        friday = _invitation_on(Session, "2026-10-23")
        assert friday.status == InvitationStatus.sent
        assert friday.reason == "Elif reacted to your story"
        light = (await c.get("/api/device/invitation", headers={"X-Person-Id": fatma_id})).json()
        assert light["active"] is True
        assert light["invitation"]["reason"] == "Elif reacted to your story"



@pytest.mark.anyio
async def test_seed_reaction_is_history_not_news(demo, monkeypatch):
    """Elif's laugh on The Mulberry Tree was told before the demo starts: nothing is
    undelivered, the opening's context has no reaction lines, and the device's
    invitation reason reads as a plain invitation, not "Elif reacted to your story"."""
    app, Session, *_ = demo
    import server.routers.device as dev_r
    monkeypatch.setattr(dev_r, "SessionLocal", Session)
    from core.services.invitations import REASON_DEFAULT
    from core.services.session_tools import get_session_context_data
    with Session() as db:
        assert [r.delivered_to_center for r in db.query(Reaction).all()] == [True]
        circle = db.query(Circle).one()
        ctx = get_session_context_data(db, circle.center_person_id, circle.id)
        assert ctx.undelivered_reactions == [] and ctx.reaction_lines == []
        invitation = db.query(Invitation).one()
        fatma_id = circle.center_person_id
    assert invitation.reason == REASON_DEFAULT == "Would you like to chat today?"
    async with _client(app) as c:
        light = (await c.get("/api/device/invitation", headers={"X-Person-Id": fatma_id})).json()
    assert light["active"] is True
    assert light["invitation"]["reason"] == REASON_DEFAULT


# ---------------------------------------------------------------------------
# Photos: one folder per database
# ---------------------------------------------------------------------------

def test_photo_folder_follows_the_database():
    from core.db import _default_path
    from core.services.photos import photo_dir_for
    assert photo_dir_for(_default_path) == Path("data") / "photos"
    assert photo_dir_for(Path("data") / "demo.db") == Path("data") / "photos-demo"
    assert photo_dir_for(Path("data") / "browser.db") == Path("data") / "photos-browser"


@pytest.mark.anyio
async def test_reseeding_demo_keeps_other_databases_photos_and_still_serves_its_own(demo, monkeypatch):
    """A demo reseed sweeps only data/photos-demo: files of the default database
    (data/photos) and of browser.db (data/photos-browser) stay, and the seed's
    photos are served after a reseed."""
    app, Session, *_ = demo
    from core.services.photos import photo_dir
    assert photo_dir() == Path("data") / "photos-demo"
    others = [Path("data/photos/default-db-photo.jpg"), Path("data/photos-browser/browser-db-photo.jpg")]
    for f in others:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"another database's photo")
    stray = Path("data/photos-demo/left-from-before.jpg")
    stray.write_bytes(b"orphan")

    seed.reset_and_seed(force=True)

    assert all(f.exists() for f in others)
    assert not stray.exists()
    with Session() as db:
        photos = db.query(StoryPhoto).all()
        elif_id = db.query(Person).filter(Person.name.like("Elif%")).one().id
        mulberry = db.query(Story).filter(Story.title == "The Mulberry Tree").one().id
        photo_id = next(p.id for p in photos if p.story_id == mulberry)
    assert {Path(p.path).parent for p in photos} == {Path("data/photos-demo")}
    assert sorted(f.name for f in Path("data/photos-demo").iterdir()) == sorted(Path(p.path).name for p in photos)
    async with _client(app) as c:
        r = await c.get(f"/api/photos/{photo_id}", headers={"X-Person-Id": elif_id})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/jpeg")


# ---------------------------------------------------------------------------
# Advance waits for the archivist (server/archive_runs.py)
# ---------------------------------------------------------------------------

def _demo_circle_id(Session) -> str:
    with Session() as db:
        return db.query(Circle).filter(Circle.is_demo.is_(True)).one().id


@pytest.mark.anyio
async def test_status_says_only_whether_the_archivist_runs(demo):
    app, Session, *_ = demo
    from server import archive_runs
    circle_id = _demo_circle_id(Session)
    async with _client(app) as c:
        assert (await c.get("/api/demo/status")).json() == {"archiving": False}
        archive_runs.begin(circle_id)
        try:
            assert (await c.get("/api/demo/status")).json() == {"archiving": True}
        finally:
            archive_runs.end(circle_id)
        assert (await c.get("/api/demo/status")).json() == {"archiving": False}


@pytest.mark.anyio
async def test_advance_waits_for_the_archivist_before_moving_the_clock(demo):
    """Goodbye then +1 day at once: the clock moves only after the story is saved,
    so the story's 24-hour window starts before the move and one press publishes it."""
    import time
    import anyio
    from server import archive_runs
    app, Session, *_ = demo
    circle_id = _demo_circle_id(Session)
    saved_at = {}

    async def archivist():
        await anyio.sleep(0.6)
        with Session() as db:
            saved_at["clock_rows"] = db.get(DemoClock, 1)
        archive_runs.end(circle_id)

    archive_runs.begin(circle_id)
    async with anyio.create_task_group() as tg:
        tg.start_soon(archivist)
        t0 = time.monotonic()
        async with _client(app) as c:
            body = (await c.post("/api/demo/advance", json={"hours": 24})).json()
        waited = time.monotonic() - t0
    assert body["archive_wait"] == "done" and body["offset_hours"] == 24.0
    assert waited >= 0.5
    # When the archivist finished, the clock had not moved yet.
    assert saved_at["clock_rows"] is None or saved_at["clock_rows"].offset_seconds == 0


@pytest.mark.anyio
async def test_advance_goes_ahead_after_the_wait_times_out(demo, monkeypatch):
    import server.routers.demo as demo_r
    from server import archive_runs
    app, Session, *_ = demo
    circle_id = _demo_circle_id(Session)
    monkeypatch.setattr(demo_r, "ARCHIVE_WAIT_S", 0.3)
    archive_runs.begin(circle_id)
    try:
        async with _client(app) as c:
            body = (await c.post("/api/demo/advance", json={"hours": 24})).json()
    finally:
        archive_runs.end(circle_id)
    assert body["archive_wait"] == "timed_out" and body["offset_hours"] == 24.0
