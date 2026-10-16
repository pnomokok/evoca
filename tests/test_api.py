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
- Privacy rules on /api/audio: answers need can_see() on the answer's story
  (pending / private / hidden stories keep it from the asker); one generic 403
  for every refusal; a private part only for its own speaker; whole-session listening only for the circle center and
  the recorder of a panel_recording; /api/tts only for session participants
- Identity: /turn and /session/end only for the session's owner
- Timeline: the opening reply's audio is in the WAV and segments do not overlap
- Cards: a question card only for a question marked as asked
- Nothing heard: a fixed reply, no LLM call, nothing stored
- Goodbye (end_conversation) ends the session and schedules the archivist
- Filtered panel questions are kept with status "filtered"

The archivist background task is replaced by a recorder (ARCHIVIST_CALLS), so
no test calls Bedrock.
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

# Archivist runs scheduled by the app during a test: (session_id, person_id, circle_id).
ARCHIVIST_CALLS: list[tuple[str, str, str]] = []


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
        def __init__(self, person_id, circle_id, session_id=None):
            self._inner = FakeMCPBridge(db, person_id, circle_id, session_id)
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
    # The privacy gate's checker always confirms in API tests.
    monkeypatch.setattr(dev_r, "privacy_check_llm", lambda: ScriptedLLM(["yes"]))

    ARCHIVIST_CALLS.clear()

    async def _record_archivist(session_id, person_id, circle_id):
        ARCHIVIST_CALLS.append((session_id, person_id, circle_id))

    monkeypatch.setattr(dev_r, "_run_archivist", _record_archivist)

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


# ===========================================================================
# Added after review: privacy rules, identity, timeline, cards
# ===========================================================================

import server.routers.device as _dev_r
from server.routers.audio import _DENIED


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _add_member(db, circle, name, relation):
    p = Person(name=name, birth_year=2000, language="en")
    db.add(p); db.flush()
    db.add(Membership(person_id=p.id, circle_id=circle.id, role=Role.member,
                      relation_to_center=relation))
    db.commit()
    return p


def _story(db, circle, teller, sources, status=StoryStatus.published, access_type=AccessType.circle):
    s = Story(
        circle_id=circle.id, teller_id=teller.id, kind=StoryKind.original,
        title="Story", ai_summary="s", sources=sources,
        access={"type": access_type, "person_ids": []}, status=status,
        publish_at=(now_utc() + timedelta(hours=23)).isoformat(),
        created_at=now_utc().isoformat(),
    )
    db.add(s); db.commit()
    return s


def _answered_question(db, circle, asker, target, session_id, story, start, end):
    q = Question(
        circle_id=circle.id, target_person_id=target.id, asker_id=asker.id,
        text="Where did you grow up?", source=QuestionSource.family,
        status=QuestionStatus.answered, created_at=now_utc().isoformat(),
        answer={"story_id": story.id, "session_id": session_id,
                "start_ms": start, "end_ms": end},
    )
    db.add(q); db.commit()
    return q


async def _get_audio(app, session_id, start, end, person_id=None):
    headers = {"x-person-id": person_id} if person_id else {}
    async with _client(app) as c:
        return await c.get(f"/api/audio/{session_id}",
                           params={"start": start, "end": end}, headers=headers)


def _circle_id_of(db, session_id):
    db.expire_all()
    return db.get(OrmSession, session_id).circle_id


# ---------------------------------------------------------------------------
# Rule 1: an answer is audible only if the asker can_see() its story
# ---------------------------------------------------------------------------
# The story's own source is [0, 300]; the answer is [300, 800], so only the
# answer rule can allow [300, 800].

@pytest.mark.anyio
async def test_answer_audible_when_story_published(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    sid, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, test_app[-1])
    story = _story(db, circle, fatma, [{"session_id": sid, "start_ms": 0, "end_ms": 300}])
    _answered_question(db, circle, elif_, fatma, sid, story, 300, 800)

    r = await _get_audio(app, sid, 300, 800, elif_.id)
    assert r.status_code == 200, r.text


@pytest.mark.anyio
@pytest.mark.parametrize("status,access_type", [
    (StoryStatus.pending, AccessType.circle),     # not published yet (24-hour wait)
    (StoryStatus.published, AccessType.private),  # teller made it private
    (StoryStatus.hidden, AccessType.circle),      # hidden by the center or an admin
])
async def test_answer_not_audible_when_story_not_visible(test_app, status, access_type):
    app, db, fatma, elif_, circle, *_ = test_app
    sid, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, test_app[-1])
    story = _story(db, circle, fatma, [{"session_id": sid, "start_ms": 0, "end_ms": 300}],
                   status=status, access_type=access_type)
    _answered_question(db, circle, elif_, fatma, sid, story, 300, 800)

    r = await _get_audio(app, sid, 300, 800, elif_.id)
    assert r.status_code == 403
    assert r.json()["detail"] == _DENIED


@pytest.mark.anyio
async def test_answer_not_audible_to_someone_who_did_not_ask(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    can = _add_member(db, circle, "Can", "grandson")
    sid, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, test_app[-1])
    story = _story(db, circle, fatma, [{"session_id": sid, "start_ms": 0, "end_ms": 300}])
    _answered_question(db, circle, elif_, fatma, sid, story, 300, 800)

    r = await _get_audio(app, sid, 300, 800, can.id)
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Rule 2: one generic 403 for every refusal; private ranges refused for everyone
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_private_overlap_and_no_access_look_the_same(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    sid, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, test_app[-1])

    private = await _get_audio(app, sid, 900, 1500, elif_.id)   # overlaps the private part
    no_access = await _get_audio(app, sid, 0, 800, elif_.id)    # public, but no story
    unknown = await _get_audio(app, str(uuid.uuid4()), 0, 800, elif_.id)
    no_header = await _get_audio(app, sid, 0, 800)

    for r in (private, no_access, unknown, no_header):
        assert r.status_code == 403
        assert r.json() == {"detail": _DENIED}
    assert "private" not in _DENIED.lower()


@pytest.mark.anyio
async def test_story_source_does_not_open_someone_elses_private_part(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    sid, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, test_app[-1])   # private part spoken by Fatma
    # A story whose (wrong) source covers the private part does not open it to Elif.
    _story(db, circle, fatma, [{"session_id": sid, "start_ms": 0, "end_ms": 2000}])

    r = await _get_audio(app, sid, 500, 1500, elif_.id)
    assert r.status_code == 403
    assert r.json()["detail"] == _DENIED
    # A range touching the private part's boundary is not an overlap.
    assert (await _get_audio(app, sid, 0, 1000, elif_.id)).status_code == 200


# ---------------------------------------------------------------------------
# Rule 2b: a private part is audible only to its own speaker
# ---------------------------------------------------------------------------

def _session_with_segments(db, circle, participants, started_by, audio_dir, segments):
    """segments: [(speaker or None, start_ms, end_ms, is_private)]; WAV covers them all."""
    sess = start_session(db, circle.id, started_by, [p.id for p in participants])
    db.commit()
    for speaker, start, end, is_private in segments:
        add_segment(db, sess.id, speaker.id if speaker else None, "x", start, end, is_private=is_private)
    db.commit()
    with wave.open(str(audio_dir / f"{sess.id}.wav"), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16_000)
        wf.writeframes(_make_silent_pcm(max(e for _, _, e, _ in segments)))
    return sess.id


@pytest.mark.anyio
async def test_speaker_hears_own_private_part(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    # Fatma (the center) marked part of her own conversation private.
    sid, _, _ = _setup_session_with_audio(db, fatma, elif_, circle, test_app[-1])
    assert (await _get_audio(app, sid, 500, 1500, fatma.id)).status_code == 200

    # Elif marked part of her own panel recording private.
    sid2 = _session_with_segments(db, circle, [elif_], SessionStart.panel_recording, test_app[-1],
                                  [(elif_, 0, 1000, False), (elif_, 1000, 2000, True)])
    assert (await _get_audio(app, sid2, 500, 1500, elif_.id)).status_code == 200


@pytest.mark.anyio
async def test_center_refused_for_another_speakers_private_part(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    sid = _session_with_segments(db, circle, [elif_], SessionStart.panel_recording, test_app[-1],
                                 [(elif_, 0, 1000, False), (elif_, 1000, 2000, True)])

    r = await _get_audio(app, sid, 500, 1500, fatma.id)   # the circle center
    assert r.status_code == 403
    assert r.json()["detail"] == _DENIED
    # The center can still hear the public part of the same session.
    assert (await _get_audio(app, sid, 0, 1000, fatma.id)).status_code == 200


@pytest.mark.anyio
async def test_range_over_two_speakers_private_parts_refused_for_both(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    # A panel recording by Elif with Fatma present: Fatma's private part, then Elif's.
    sid = _session_with_segments(
        db, circle, [elif_, fatma], SessionStart.panel_recording, test_app[-1],
        [(elif_, 0, 1000, False), (fatma, 1000, 2000, True), (elif_, 2000, 3000, True)],
    )

    for person in (fatma, elif_):
        r = await _get_audio(app, sid, 1500, 2500, person.id)
        assert r.status_code == 403
        assert r.json()["detail"] == _DENIED
    # Each of them can hear their own private part alone.
    assert (await _get_audio(app, sid, 1000, 2000, fatma.id)).status_code == 200
    assert (await _get_audio(app, sid, 2000, 3000, elif_.id)).status_code == 200
    assert (await _get_audio(app, sid, 1000, 2000, elif_.id)).status_code == 403
    assert (await _get_audio(app, sid, 2000, 3000, fatma.id)).status_code == 403


@pytest.mark.anyio
async def test_private_agent_segment_refused_for_everyone(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    sid = _session_with_segments(db, circle, [fatma], SessionStart.spontaneous, test_app[-1],
                                 [(fatma, 0, 1000, False), (None, 1000, 2000, True)])
    assert (await _get_audio(app, sid, 500, 1500, fatma.id)).status_code == 403


# ---------------------------------------------------------------------------
# Rule 3: whole-session listening: circle center, or the recorder of a panel_recording
# ---------------------------------------------------------------------------

def _session_with_pcm(db, circle, participants, started_by, audio_dir, ms=1000):
    sess = start_session(db, circle.id, started_by, [p.id for p in participants])
    db.commit()
    add_segment(db, sess.id, participants[0].id, "Public", 0, ms)
    db.commit()
    with wave.open(str(audio_dir / f"{sess.id}.wav"), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16_000)
        wf.writeframes(_make_silent_pcm(ms))
    return sess.id


@pytest.mark.anyio
async def test_first_participant_is_not_the_center(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    # A session whose first participant is Elif (e.g. a gathering) does not
    # make Elif a whole-session listener; the circle center still is.
    sid = _session_with_pcm(db, circle, [elif_, fatma], SessionStart.spontaneous, test_app[-1])

    assert (await _get_audio(app, sid, 0, 800, elif_.id)).status_code == 403
    assert (await _get_audio(app, sid, 0, 800, fatma.id)).status_code == 200


@pytest.mark.anyio
async def test_panel_recording_audible_to_its_recorder(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    can = _add_member(db, circle, "Can", "grandson")
    sid = _session_with_pcm(db, circle, [elif_], SessionStart.panel_recording, test_app[-1])

    assert (await _get_audio(app, sid, 0, 800, elif_.id)).status_code == 200
    assert (await _get_audio(app, sid, 0, 800, fatma.id)).status_code == 200   # circle center
    assert (await _get_audio(app, sid, 0, 800, can.id)).status_code == 403


# ---------------------------------------------------------------------------
# Rule 4: /api/tts only for the session's participants
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tts_file_only_for_session_participants(test_app):
    app, db, fatma, elif_, *_ = test_app
    _set_llm_script(test_app, ["Hello, Fatma!"])
    async with _client(app) as c:
        r = await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})
        url = r.json()["reply_audio_url"]

        assert (await c.get(url)).status_code == 403
        assert (await c.get(url, headers={"x-person-id": elif_.id})).status_code == 403
        ok = await c.get(url, headers={"x-person-id": fatma.id})
        assert ok.status_code == 200
        assert ok.headers["content-type"] == "audio/wav"   # FakeTTS returns WAV

        bad = await c.get("/api/tts/evoca.db", headers={"x-person-id": fatma.id})
        assert bad.status_code == 400


# ---------------------------------------------------------------------------
# Rule 5: /turn and /session/end only for the session's owner
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_turn_and_end_require_session_owner(test_app):
    app, db, fatma, elif_, *_ = test_app
    _set_llm_script(test_app, ["Hello, Fatma!"])
    wav = _make_wav_bytes(_make_silent_pcm(300))

    async with _client(app) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": fatma.id})).json()["session_id"]

        for headers in ({}, {"x-person-id": elif_.id}):
            turn = await c.post("/api/device/turn", headers=headers, data={"session_id": sid},
                                files={"audio": ("a.wav", wav, "audio/wav")})
            assert turn.status_code == 403
            end = await c.post("/api/device/session/end", headers=headers, json={"session_id": sid})
            assert end.status_code == 403

        assert ARCHIVIST_CALLS == []
        end = await c.post("/api/device/session/end", headers={"x-person-id": fatma.id},
                           json={"session_id": sid})
        assert end.status_code == 200

    assert ARCHIVIST_CALLS == [(sid, fatma.id, _circle_id_of(db, sid))]


@pytest.mark.anyio
async def test_session_start_requires_center(test_app):
    app, db, fatma, elif_, *_ = test_app
    async with _client(app) as c:
        assert (await c.post("/api/device/session/start")).status_code == 403
        assert (await c.post("/api/device/session/start",
                             headers={"x-person-id": elif_.id})).status_code == 403


# ---------------------------------------------------------------------------
# Timeline, cards, nothing heard, goodbye, invitation, filtered questions
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_opening_reply_is_in_wav_and_segments_do_not_overlap(test_app):
    app, db, fatma, *_ = test_app
    _set_llm_script(test_app, ["Hello, Fatma!", "What a lovely memory."])
    async with _client(app) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": fatma.id})).json()["session_id"]
        await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                     data={"session_id": sid},
                     files={"audio": ("a.wav", _make_wav_bytes(_make_silent_pcm(500)), "audio/wav")})

    db.expire_all()
    segs = db.query(Segment).filter(Segment.session_id == sid).order_by(Segment.start_ms).all()
    # FakeTTS = 400 ms: opening reply [0,400], user [400,900], reply [900,1300].
    assert [(s.speaker_id is None, s.start_ms, s.end_ms) for s in segs] == [
        (True, 0, 400), (False, 400, 900), (True, 900, 1300),
    ]


@pytest.mark.anyio
async def test_question_card_only_for_marked_question(test_app):
    app, db, fatma, elif_, circle, q, *_ = test_app
    _set_llm_script(test_app, [
        [_tool_use("get_session_context", {}), _tool_use("get_pending_questions", {"limit": 5})],
        "Is there a memory on your mind today?",                       # opening: nothing marked
        [_tool_use("mark_question_asked", {"question_id": q.id})],
        "Your granddaughter Elif would love to know about school.",     # turn: marked
    ])
    async with _client(app) as c:
        start = (await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})).json()
        assert start["cards"] == []

        turn = (await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                             data={"session_id": start["session_id"]},
                             files={"audio": ("a.wav", _make_wav_bytes(_make_silent_pcm(300)),
                                              "audio/wav")})).json()

    assert turn["cards"] == [{
        "type": "question", "question_id": q.id, "text": "What was school like?",
        "asker": {"id": elif_.id, "name": "Elif", "relation_to_center": "granddaughter"},
    }]


@pytest.mark.anyio
async def test_nothing_heard_asks_again_without_llm(test_app):
    app, db, fatma, *_ = test_app
    llm_holder = test_app[7]
    _set_llm_script(test_app, ["Hello, Fatma!"])
    fake_stt = app.dependency_overrides[_dev_r._get_stt]()
    fake_stt._text = "   "

    async with _client(app) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": fatma.id})).json()["session_id"]
        calls_before = len(llm_holder[0].calls)
        r = await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                         data={"session_id": sid},
                         files={"audio": ("a.wav", _make_wav_bytes(_make_silent_pcm(300)), "audio/wav")})

    data = r.json()
    assert r.status_code == 200
    assert data["heard_text"] == ""
    assert data["reply_text"] == _dev_r.DIDNT_CATCH
    assert data["session_open"] is True
    assert len(llm_holder[0].calls) == calls_before
    db.expire_all()
    assert db.query(Segment).filter(Segment.session_id == sid).count() == 1   # only the opening


@pytest.mark.anyio
async def test_goodbye_ends_session_and_schedules_archivist(test_app):
    app, db, fatma, *_ = test_app
    _set_llm_script(test_app, [
        "Hello, Fatma!",
        [{"text": "Thank you for these stories. Rest well."}, _tool_use("end_conversation", {})],
    ])
    async with _client(app) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": fatma.id})).json()["session_id"]
        r = await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                         data={"session_id": sid},
                         files={"audio": ("a.wav", _make_wav_bytes(_make_silent_pcm(300)), "audio/wav")})
        assert r.json()["session_open"] is False
        again = await c.post("/api/device/session/end", headers={"x-person-id": fatma.id},
                             json={"session_id": sid})
        assert again.status_code == 404

    db.expire_all()
    assert db.get(OrmSession, sid).ended_at is not None
    assert [call[0] for call in ARCHIVIST_CALLS] == [sid]


@pytest.mark.anyio
async def test_session_start_accepts_todays_invitation(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    _set_llm_script(test_app, ["Hello, Fatma!"])
    # The fixture's invitation uses the UTC date; make it today's date in the circle's zone.
    from zoneinfo import ZoneInfo
    inv = db.query(Invitation).first()
    inv.date = now_utc().astimezone(ZoneInfo(circle.timezone)).strftime("%Y-%m-%d")
    db.commit()

    async with _client(app) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": fatma.id})).json()["session_id"]

    db.expire_all()
    assert db.get(OrmSession, sid).started_by == SessionStart.invitation
    assert db.get(Invitation, inv.id).status == InvitationStatus.accepted


@pytest.mark.anyio
async def test_filtered_question_is_saved_with_status_filtered(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    db.add(SensitiveTopic(circle_id=circle.id, text="Hatice Germany separation",
                          added_by=fatma.id, created_at=now_utc().isoformat()))
    db.commit()
    async with _client(app) as c:
        r = await c.post("/api/questions", headers={"x-person-id": elif_.id},
                         json={"target_person_id": fatma.id, "text": "Why did Hatice leave?"})
        bad = await c.post("/api/questions", headers={"x-person-id": elif_.id},
                           json={"target_person_id": fatma.id, "text": "Hi?", "period": "old_age"})
    assert r.json()["status"] == "filtered"
    assert bad.status_code == 400
    db.expire_all()
    saved = db.query(Question).filter(Question.text == "Why did Hatice leave?").one()
    assert saved.status == QuestionStatus.filtered
    assert saved.asker_id == elif_.id


# ---------------------------------------------------------------------------
# MCP clients: opened and closed in the same task, none left open
# ---------------------------------------------------------------------------

class _TrackingBridge:
    """Fake MCP bridge that, like the real anyio-based MCP client, must be
    closed in the task that opened it. Counts open connections."""

    open_count = 0
    opened = 0
    wrong_task_exits = 0

    def __init__(self, db, person_id, circle_id):
        self._inner = FakeMCPBridge(db, person_id, circle_id)
        self._task = None

    async def __aenter__(self):
        import asyncio
        self._task = asyncio.current_task()
        type(self).open_count += 1
        type(self).opened += 1
        return self

    async def __aexit__(self, *exc):
        import asyncio
        if asyncio.current_task() is not self._task:
            type(self).wrong_task_exits += 1
            raise RuntimeError("Attempted to exit cancel scope in a different task than it was entered in")
        type(self).open_count -= 1

    async def bedrock_tool_config(self):
        return await self._inner.bedrock_tool_config()

    async def call_tool(self, name, arguments):
        return await self._inner.call_tool(name, arguments)


@pytest.mark.anyio
async def test_mcp_clients_closed_in_same_task_over_several_sessions(test_app, monkeypatch):
    app, db, fatma, *_ = test_app
    _TrackingBridge.open_count = _TrackingBridge.opened = _TrackingBridge.wrong_task_exits = 0
    monkeypatch.setattr(_dev_r, "MCPBridge",
                        lambda person_id, circle_id, session_id=None: _TrackingBridge(db, person_id, circle_id))
    _set_llm_script(test_app, ["A reply."])
    wav = _make_wav_bytes(_make_silent_pcm(300))

    cycles, turns_per_cycle = 3, 2
    async with _client(app) as c:
        for _ in range(cycles):
            r = await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})
            assert r.status_code == 200, r.text
            sid = r.json()["session_id"]
            assert "mcp_connect_ms" in r.json()["latency"]
            for _ in range(turns_per_cycle):
                t = await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                                 data={"session_id": sid}, files={"audio": ("a.wav", wav, "audio/wav")})
                assert t.status_code == 200, t.text
                assert _TrackingBridge.open_count == 0      # nothing open between requests
            e = await c.post("/api/device/session/end", headers={"x-person-id": fatma.id},
                             json={"session_id": sid})
            assert e.status_code == 200, e.text

    assert _TrackingBridge.wrong_task_exits == 0
    assert _TrackingBridge.open_count == 0
    assert _TrackingBridge.opened == cycles * (1 + turns_per_cycle)   # one per start and per turn
    assert len(ARCHIVIST_CALLS) == cycles


@pytest.mark.anyio
async def test_turn_with_mcp_down_returns_502_and_stores_nothing(test_app, monkeypatch):
    app, db, fatma, *_ = test_app
    _set_llm_script(test_app, ["Hello, Fatma!"])
    async with _client(app) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": fatma.id})).json()["session_id"]

        class _Down:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                raise ConnectionError("MCP server down")

            async def __aexit__(self, *a):
                pass

        monkeypatch.setattr(_dev_r, "MCPBridge", _Down)
        r = await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                         data={"session_id": sid},
                         files={"audio": ("a.wav", _make_wav_bytes(_make_silent_pcm(300)), "audio/wav")})
    assert r.status_code == 502
    db.expire_all()
    assert db.query(Segment).filter(Segment.session_id == sid).count() == 1   # only the opening


# ---------------------------------------------------------------------------
# Whisper gets the question the agent just asked, plus the family names
# ---------------------------------------------------------------------------

def test_build_initial_prompt_with_question():
    from server.speech import build_initial_prompt
    members = [{"name": "Fatma", "relation_to_center": None},
               {"name": "Elif", "relation_to_center": "granddaughter"}]
    assert build_initial_prompt(members) == "A family story. Names: Fatma, Elif (granddaughter)."
    assert build_initial_prompt(members, "Did you ever meet anyone famous?") == (
        "A family story. Names: Fatma, Elif (granddaughter). "
        "The question was: Did you ever meet anyone famous?"
    )
    assert len(build_initial_prompt([], "x" * 500)) < 230


@pytest.mark.anyio
async def test_whisper_prompt_contains_the_question_just_asked(test_app):
    app, db, fatma, *_ = test_app
    _set_llm_script(test_app, [
        "Hello! Your granddaughter Elif would love to know, did you ever meet anyone famous growing up?",
        "How lovely. What song did the singer sing?",
        "Thank you.",
    ])
    fake_stt = app.dependency_overrides[_dev_r._get_stt]()
    wav = _make_wav_bytes(_make_silent_pcm(300))
    async with _client(app) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": fatma.id})).json()["session_id"]
        for _ in range(2):
            await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                         data={"session_id": sid}, files={"audio": ("a.wav", wav, "audio/wav")})

    first, second = fake_stt.prompts[-2:]
    assert "Names: Fatma, Elif (granddaughter)." in first
    assert first.endswith("The question was: Your granddaughter Elif would love to know, "
                          "did you ever meet anyone famous growing up?")
    assert "Hello!" not in first                                            # only the question sentence
    assert second.endswith("The question was: What song did the singer sing?")   # the latest question


# ---------------------------------------------------------------------------
# "Don't let anyone hear that" through the device endpoints
# ---------------------------------------------------------------------------

def _seg_rows(db, session_id):
    db.expire_all()
    return (db.query(Segment).filter(Segment.session_id == session_id)
            .order_by(Segment.start_ms).all())


@pytest.mark.anyio
async def test_private_turn_through_device_and_audio_rules(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    _set_llm_script(test_app, [
        "Hello, Fatma!",
        [_tool_use("keep_private", {"scope": "this_turn"})],
        "Of course, that part will stay private.",
        "How lovely. What else do you remember?",
    ])
    stt = app.dependency_overrides[_dev_r._get_stt]()
    wav = _make_wav_bytes(_make_silent_pcm(500))
    async with _client(app) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": fatma.id})).json()["session_id"]
        stt._text = "My father lost all our money gambling. Please don't tell anyone."
        r1 = await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                          data={"session_id": sid}, files={"audio": ("a.wav", wav, "audio/wav")})
        assert "mark_private" in [t["tool"] for t in r1.json()["trace"]]
        stt._text = "We had a garden."
        await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                     data={"session_id": sid}, files={"audio": ("a.wav", wav, "audio/wav")})
        await c.post("/api/device/session/end", headers={"x-person-id": fatma.id},
                     json={"session_id": sid})

    segs = _seg_rows(db, sid)
    # opening reply [0,400], private user [400,900] + reply [900,1300], then public.
    assert [(s.start_ms, s.end_ms, s.is_private) for s in segs] == [
        (0, 400, False), (400, 900, True), (900, 1300, True), (1300, 1800, False), (1800, 2200, False),
    ]
    assert [call[0] for call in ARCHIVIST_CALLS] == [sid]   # marks applied, so the archivist runs

    # A (wrong) circle story over the private part does not open it to Elif.
    _story(db, circle, fatma, [{"session_id": sid, "start_ms": 0, "end_ms": 2200}])
    assert (await _get_audio(app, sid, 400, 900, elif_.id)).status_code == 403
    assert (await _get_audio(app, sid, 900, 1300, fatma.id)).status_code == 403   # agent's reply: nobody
    assert (await _get_audio(app, sid, 400, 900, fatma.id)).status_code == 200    # the speaker herself
    assert (await _get_audio(app, sid, 1300, 1800, elif_.id)).status_code == 200  # the public part


class _FlakyBridge:
    """Fake MCP bridge whose mark_private fails while FAIL is set."""

    FAIL = {"on": True}

    def __init__(self, db, person_id, circle_id, session_id=None):
        self._inner = FakeMCPBridge(db, person_id, circle_id, session_id)

    async def __aenter__(self):
        if self.FAIL["on"]:
            self._inner.fail_tools = {"mark_private"}
        return self

    async def __aexit__(self, *exc):
        pass

    async def bedrock_tool_config(self):
        return await self._inner.bedrock_tool_config()

    async def call_tool(self, name, arguments):
        return await self._inner.call_tool(name, arguments)


async def _private_session_with_failing_marks(test_app, monkeypatch):
    app, db, fatma, *_ = test_app
    monkeypatch.setattr(_dev_r, "MCPBridge",
                        lambda person_id, circle_id, session_id=None:
                        _FlakyBridge(db, person_id, circle_id, session_id))
    _set_llm_script(test_app, [
        "Hello, Fatma!",
        [_tool_use("keep_private", {"scope": "this_turn"})],
        "Of course, that part will stay private.",
    ])
    app.dependency_overrides[_dev_r._get_stt]()._text = "SECRET keep this between us."
    async with _client(app) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": fatma.id})).json()["session_id"]
        r = await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                         data={"session_id": sid},
                         files={"audio": ("a.wav", _make_wav_bytes(_make_silent_pcm(500)), "audio/wav")})
        assert r.status_code == 200
        assert [t["is_error"] for t in r.json()["trace"] if t["tool"] == "mark_private"] == [True, True]
    return app, db, fatma, sid


@pytest.mark.anyio
async def test_failed_mark_retried_at_end_then_archivist_skipped(test_app, monkeypatch, caplog):
    import logging
    _FlakyBridge.FAIL["on"] = True
    app, db, fatma, sid = await _private_session_with_failing_marks(test_app, monkeypatch)
    with caplog.at_level(logging.ERROR, logger="server.routers.device"):
        async with _client(app) as c:
            end = await c.post("/api/device/session/end", headers={"x-person-id": fatma.id},
                               json={"session_id": sid})
    assert end.status_code == 200
    assert ARCHIVIST_CALLS == []                                         # fail closed
    assert f"Session {sid}: 2 segment(s) could not be marked private" in caplog.text
    assert "archivist is NOT run" in caplog.text


@pytest.mark.anyio
async def test_failed_mark_retried_at_end_succeeds_then_archivist_runs(test_app, monkeypatch):
    _FlakyBridge.FAIL["on"] = True
    app, db, fatma, sid = await _private_session_with_failing_marks(test_app, monkeypatch)
    assert not any(s.is_private for s in _seg_rows(db, sid))
    _FlakyBridge.FAIL["on"] = False                                      # MCP is back
    async with _client(app) as c:
        await c.post("/api/device/session/end", headers={"x-person-id": fatma.id},
                     json={"session_id": sid})
    assert [s.is_private for s in _seg_rows(db, sid)] == [False, True, True]
    assert [call[0] for call in ARCHIVIST_CALLS] == [sid]


@pytest.mark.anyio
async def test_reaction_announced_once_across_sessions(test_app):
    from core.enums import Emoji
    from core.models import Reaction
    app, db, fatma, elif_, circle, *_ = test_app
    story = _story(db, circle, fatma, [])
    db.add(Reaction(story_id=story.id, person_id=elif_.id, emoji=Emoji.laugh,
                    delivered_to_center=False, created_at=now_utc().isoformat()))
    db.commit()

    async with _client(app) as c:
        _set_llm_script(test_app, [[_tool_use("get_session_context", {})],
                                   "Your granddaughter Elif laughed at your story."])
        first = (await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})).json()
        await c.post("/api/device/session/end", headers={"x-person-id": fatma.id},
                     json={"session_id": first["session_id"]})
        _set_llm_script(test_app, [[_tool_use("get_session_context", {})], "Good morning, Fatma!"])
        second = (await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})).json()

    assert [card["type"] for card in first["cards"]] == ["reaction"]
    assert "mark_reactions_delivered" in [t["tool"] for t in first["trace"]]
    assert second["cards"] == []
