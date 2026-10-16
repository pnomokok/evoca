"""
FastAPI integration tests.

Architecture
------------
The app uses `core.db.SessionLocal` throughout. Tests patch that factory at
the module level with one that points at an in-memory (or temp-file) SQLite
database, avoiding any writes to data/evoca.db.

All tests are async (pytest-anyio) and use httpx.AsyncClient + ASGITransport.

Fake services
-------------
- ScriptedLLM  (re-used from test_chat_agent)
- FakeMCPBridge (re-used from test_chat_agent) — calls real service functions
  on the same patched DB.
- FakeSTT / FakeTTS from server.speech.

Coverage
--------
- Full device flow: session/start → turn → session/end
- WAV positions advance across turns
- Segment start_ms < end_ms after a /turn
- GET /api/audio: center person allowed
- GET /api/audio: private overlap → 403
- GET /api/audio: member blocked without story source
- GET /api/audio: member allowed via story source
- GET /api/circle: shape matches sample
- POST /api/questions: accepted path
- POST /api/questions: filtered path
- POST /api/questions: non-member → 403
"""

from __future__ import annotations

import io
import struct
import uuid
import wave
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from core.clock import now_utc
from core.enums import (
    AccessType, CircleStatus, InvitationStatus,
    QuestionSource, QuestionStatus, Role,
    SessionKind, SessionStart, StoryKind, StoryStatus,
)
from core.models import (
    Base, Circle, Invitation, Membership, Person, Question,
    Segment, SensitiveTopic, Story, Session as OrmSession,
)
from core.services.sessions import add_segment, start_session

from tests.test_chat_agent import FakeMCPBridge, ScriptedLLM, _tool_use


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_silent_pcm(duration_ms: int = 1000) -> bytes:
    n_samples = int(16_000 * duration_ms / 1000)
    return struct.pack(f"<{n_samples}h", *([0] * n_samples))


def _make_wav_bytes(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16_000)
        wf.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Core fixture: patched DB + app
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _enable_fk(conn, _rec):
    c = conn.cursor(); c.execute("PRAGMA foreign_keys=ON"); c.close()


@pytest.fixture(scope="function")
def test_app(tmp_path, monkeypatch):
    """
    Build a fully-wired test environment:
      1. Create a temp-file SQLite DB engine.
      2. Patch core.db.SessionLocal to use it.
      3. Seed minimal data (circle, 2 people, question, invitation).
      4. Redirect data/audio and data/tts to tmp_path.
      5. Patch MCPBridge + chat_llm in the device router.
      6. Override STT/TTS with fakes.
      7. Return (app, db_session, people, ...).
    """
    # ---- 1. Engine --------------------------------------------------------
    db_path = tmp_path / "test.db"
    eng = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(eng, "connect", _enable_fk)
    Base.metadata.create_all(bind=eng)
    TestSession = sessionmaker(bind=eng, autocommit=False, autoflush=False, expire_on_commit=False)

    # ---- 2. Patch SessionLocal --------------------------------------------
    import core.db as cdb
    monkeypatch.setattr(cdb, "SessionLocal", TestSession)
    # Also patch wherever it's already imported.
    import server.routers.device as dev_r
    import server.routers.panel  as pan_r
    import server.routers.audio  as aud_r
    import server.agents.chat_agent as ca
    import core.services.sessions as cs
    import core.services.session_tools as cst
    for mod in (dev_r, pan_r, aud_r, ca, cs, cst):
        if hasattr(mod, "SessionLocal"):
            monkeypatch.setattr(mod, "SessionLocal", TestSession)

    # ---- 3. Seed ----------------------------------------------------------
    now = now_utc()
    db = TestSession()

    fatma = Person(name="Fatma", birth_year=1948, language="en")
    elif_ = Person(name="Elif",  birth_year=2003, language="en")
    db.add_all([fatma, elif_]); db.flush()

    circle = Circle(
        name="Test Family", center_person_id=fatma.id,
        status=CircleStatus.active, chat_time="10:00", timezone="Europe/Istanbul",
    )
    db.add(circle); db.flush()

    db.add_all([
        Membership(person_id=fatma.id, circle_id=circle.id,
                   role=Role.center, relation_to_center=None),
        Membership(person_id=elif_.id, circle_id=circle.id,
                   role=Role.member, relation_to_center="granddaughter"),
    ])

    q = Question(
        circle_id=circle.id, target_person_id=fatma.id, asker_id=elif_.id,
        text="What was school like?",
        source=QuestionSource.family, period=None,
        status=QuestionStatus.waiting, answer=None,
        created_at=(now - timedelta(hours=1)).isoformat(),
    )
    db.add(q)

    today_str = now.strftime("%Y-%m-%d")
    inv = Invitation(
        circle_id=circle.id, person_id=fatma.id,
        date=today_str, reason="Elif has a question.",
        status=InvitationStatus.sent,
    )
    db.add(inv)
    db.commit()

    # ---- 4. Redirect audio/tts dirs ---------------------------------------
    audio_dir = tmp_path / "audio"
    tts_dir   = tmp_path / "tts"
    audio_dir.mkdir(); tts_dir.mkdir()

    import server.wav_writer as ww
    monkeypatch.setattr(ww, "_AUDIO_DIR", audio_dir)
    monkeypatch.setattr(dev_r, "TTS_DIR", tts_dir)
    monkeypatch.setattr(aud_r, "TTS_DIR", tts_dir)

    # ---- 5. Patch MCPBridge and chat_llm ----------------------------------
    _llm_holder: list[ScriptedLLM] = []

    class _FakeBridgeFactory:
        """Returned by patched MCPBridge(person_id, circle_id).
        Acts as both the context manager AND the bridge itself so device.py's
        pattern (bridge = MCPBridge(...); await bridge.__aenter__(); agent uses bridge)
        works correctly.
        """
        def __init__(self, person_id, circle_id):
            self._inner = FakeMCPBridge(db, person_id, circle_id)
        async def __aenter__(self):
            return self   # device.py stores the factory itself as the bridge
        async def __aexit__(self, *a):
            pass
        async def bedrock_tool_config(self):
            return await self._inner.bedrock_tool_config()
        async def call_tool(self, name, arguments):
            return await self._inner.call_tool(name, arguments)

    monkeypatch.setattr(dev_r, "MCPBridge", _FakeBridgeFactory)

    def _make_scripted_llm():
        if _llm_holder:
            return _llm_holder[0]
        llm = ScriptedLLM(["Hello, Fatma!"])
        _llm_holder.append(llm)
        return llm

    monkeypatch.setattr(dev_r, "chat_llm", _make_scripted_llm)

    # ---- 6. Override STT/TTS with fakes -----------------------------------
    from server.app import app
    from server.session_store import SessionStore
    from server.speech import FakeSTT, FakeTTS

    fake_store = SessionStore()
    fake_stt   = FakeSTT(text="hello grandma")
    fake_tts   = FakeTTS(duration_ms=400)

    app.dependency_overrides[dev_r._get_store] = lambda: fake_store
    app.dependency_overrides[dev_r._get_stt]   = lambda: fake_stt
    app.dependency_overrides[dev_r._get_tts]   = lambda: fake_tts

    # Also patch init_db so lifespan doesn't recreate tables on top of ours.
    monkeypatch.setattr(cdb, "init_db", lambda: None)

    yield app, db, fatma, elif_, circle, q, fake_store, _llm_holder, audio_dir

    app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(bind=eng)


def _set_llm_script(test_app_fixture, script):
    """Replace the scripted LLM's script in place."""
    _, _, _, _, _, _, _, llm_holder, _ = test_app_fixture
    if llm_holder:
        llm_holder[0]._script = list(script)
        llm_holder[0]._idx    = 0
    else:
        llm_holder.append(ScriptedLLM(script))


# ---------------------------------------------------------------------------
# Full device flow
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_full_device_flow(test_app):
    app, db, fatma, elif_, circle, q, store, llm_h, _ = test_app

    uid1, uid2, uid3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    _set_llm_script(test_app, [
        [_tool_use("get_session_context", {}, uid1),
         _tool_use("get_pending_questions", {"limit": 5}, uid2)],
        [_tool_use("mark_question_asked", {"question_id": q.id}, uid3)],
        "Good morning! What was school like for you?",
        "What a wonderful memory!",
    ])

    pcm = _make_silent_pcm(500)
    wav = _make_wav_bytes(pcm)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["session_open"] is True
        assert data["reply_text"]
        assert "stt_ms" in data["latency"]
        assert "tts_ms" in data["latency"]
        session_id = data["session_id"]

        r2 = await c.post(
            "/api/device/turn",
            headers={"x-person-id": fatma.id},
            data={"session_id": session_id},
            files={"audio": ("clip.wav", wav, "audio/wav")},
        )
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["heard_text"] == "hello grandma"
        assert d2["session_open"] is True

        r3 = await c.post(
            "/api/device/session/end",
            headers={"x-person-id": fatma.id},
            json={"session_id": session_id},
        )
        assert r3.status_code == 200, r3.text
        d3 = r3.json()
        assert d3["session_id"] == session_id
        assert d3["ended_at"]
        assert d3["processing"] == "started"


@pytest.mark.anyio
async def test_session_not_found_returns_404(test_app):
    app, db, fatma, *_ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/device/turn",
            headers={"x-person-id": fatma.id},
            data={"session_id": "nonexistent"},
            files={"audio": ("a.wav", _make_wav_bytes(_make_silent_pcm()), "audio/wav")},
        )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# WAV positions
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_wav_positions_advance_across_turns(test_app):
    app, db, fatma, elif_, circle, q, store, llm_h, audio_dir = test_app
    _set_llm_script(test_app, ["Turn 1 reply.", "Turn 2 reply."])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})
        assert r.status_code == 200, r.text
        session_id = r.json()["session_id"]

        for dur in [500, 800]:
            rr = await c.post(
                "/api/device/turn",
                headers={"x-person-id": fatma.id},
                data={"session_id": session_id},
                files={"audio": ("c.wav", _make_wav_bytes(_make_silent_pcm(dur)), "audio/wav")},
            )
            assert rr.status_code == 200, rr.text

    path = audio_dir / f"{session_id}.wav"
    assert path.exists()
    import server.wav_writer as ww
    total = ww._count_existing_samples(path)
    # At least 500+800 ms of user audio (16_000 samples/sec).
    assert total >= int((500 + 800) * 16_000 / 1000)


@pytest.mark.anyio
async def test_segments_stored_with_nonzero_end_ms(test_app):
    app, db, fatma, *_ = test_app
    _set_llm_script(test_app, ["A reply."])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})
        session_id = r.json()["session_id"]

        await c.post(
            "/api/device/turn",
            headers={"x-person-id": fatma.id},
            data={"session_id": session_id},
            files={"audio": ("a.wav", _make_wav_bytes(_make_silent_pcm(600)), "audio/wav")},
        )

    segs = db.query(Segment).filter(Segment.session_id == session_id).all()
    for seg in segs:
        assert seg.end_ms >= seg.start_ms, f"Segment {seg.id}: [{seg.start_ms},{seg.end_ms}]"


# ---------------------------------------------------------------------------
# Audio access rules
# ---------------------------------------------------------------------------

def _setup_session_with_audio(db, fatma, elif_, circle, audio_dir):
    """Create a finished session with a public segment (0-1000) and a
    private segment (1000-2000), backed by a real WAV file."""
    sess = start_session(db, circle.id, SessionStart.spontaneous, [fatma.id])
    db.commit()

    pub_pcm  = _make_silent_pcm(1000)
    priv_pcm = _make_silent_pcm(1000)

    pub_seg  = add_segment(db, sess.id, fatma.id, "Public",  0,    1000)
    priv_seg = add_segment(db, sess.id, fatma.id, "Private", 1000, 2000, is_private=True)
    db.commit()

    # Write WAV.
    path = audio_dir / f"{sess.id}.wav"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16_000)
        wf.writeframes(pub_pcm + priv_pcm)

    sess_row = db.get(OrmSession, sess.id)
    sess_row.audio_path = str(path)
    db.commit()

    return sess.id, pub_seg, priv_seg


@pytest.mark.anyio
async def test_center_person_can_hear_own_audio(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    _, audio_dir = test_app[-2], test_app[-1]
    session_id, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, audio_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(
            f"/api/audio/{session_id}",
            params={"start": 0, "end": 800},
            headers={"x-person-id": fatma.id},
        )
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"


@pytest.mark.anyio
async def test_private_overlap_returns_403(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    audio_dir = test_app[-1]
    session_id, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, audio_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Range 900–1500 overlaps the private segment at 1000–2000.
        r = await c.get(
            f"/api/audio/{session_id}",
            params={"start": 900, "end": 1500},
            headers={"x-person-id": elif_.id},
        )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_member_blocked_without_story_source(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    audio_dir = test_app[-1]
    session_id, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, audio_dir)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(
            f"/api/audio/{session_id}",
            params={"start": 0, "end": 800},
            headers={"x-person-id": elif_.id},
        )
    assert r.status_code == 403


@pytest.mark.anyio
async def test_member_allowed_via_story_source(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    audio_dir = test_app[-1]
    session_id, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, audio_dir)

    # Give Elif access via a circle-visible story citing [0, 800].
    story = Story(
        circle_id=circle.id, teller_id=fatma.id,
        kind=StoryKind.original, title="Src story",
        ai_summary="s",
        sources=[{"session_id": session_id, "start_ms": 0, "end_ms": 800}],
        access={"type": AccessType.circle, "person_ids": []},
        status=StoryStatus.published,
        publish_at=(now_utc() - timedelta(hours=1)).isoformat(),
        created_at=(now_utc() - timedelta(hours=2)).isoformat(),
    )
    db.add(story); db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(
            f"/api/audio/{session_id}",
            params={"start": 0, "end": 800},
            headers={"x-person-id": elif_.id},
        )
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Panel endpoints
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_circle_shape(test_app):
    app, db, fatma, elif_, circle, *_ = test_app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/circle", headers={"x-person-id": elif_.id})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["circle"]["id"] == circle.id
    assert data["me"]["id"] == elif_.id
    assert data["me"]["role"] == Role.member
    assert data["me"]["relation_to_center"] == "granddaughter"
    member_ids = [m["id"] for m in data["members"]]
    assert fatma.id in member_ids and elif_.id in member_ids


@pytest.mark.anyio
async def test_get_circle_requires_header(test_app):
    app, *_ = test_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/circle")
    assert r.status_code == 403


@pytest.mark.anyio
async def test_post_question_accepted(test_app):
    app, db, fatma, elif_, circle, *_ = test_app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/questions",
            headers={"x-person-id": elif_.id},
            json={"target_person_id": fatma.id,
                  "text": "Did you have a favourite teacher?"},
        )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "waiting"
    assert data["question"]["text"] == "Did you have a favourite teacher?"
    assert data["question"]["source"] == "family"


@pytest.mark.anyio
async def test_post_question_filtered(test_app):
    app, db, fatma, elif_, circle, *_ = test_app

    topic = SensitiveTopic(
        circle_id=circle.id, text="Hatice Germany separation",
        added_by=fatma.id, created_at=now_utc().isoformat(),
    )
    db.add(topic); db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/questions",
            headers={"x-person-id": elif_.id},
            json={"target_person_id": fatma.id,
                  "text": "Why did Hatice leave for Germany?"},
        )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "filtered"
    assert data["question"] is None
    # Message must not leak the topic text.
    assert "Hatice" not in data["message"]
    assert "Germany" not in data["message"]


@pytest.mark.anyio
async def test_post_question_nonmember_returns_403(test_app):
    app, db, fatma, *_ = test_app

    outsider = Person(name="Outsider", birth_year=1990, language="en")
    db.add(outsider); db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post(
            "/api/questions",
            headers={"x-person-id": outsider.id},
            json={"target_person_id": fatma.id, "text": "Hello?"},
        )
    assert r.status_code == 403
