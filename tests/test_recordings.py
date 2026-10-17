"""
Tests for POST /api/recordings (A4: a family member's own memory).

Uses the test_app fixture from tests/test_api.py (temp SQLite DB, Fatma as the
center, Elif as a member). The background work runs for real: FakeSTT, the
real ArchivistAgent in panel_recording mode with a scripted LLM, and a fake
MCP bridge that calls the real archive services on the same DB.

Coverage
--------
- 202 + a panel_recording session owned by the recorder, ended, with its WAV
  and one Segment (speaker = recorder, word timings)
- The story's teller is always the recorder; the center can be a subject
- access=private is honored (only the teller sees the story), also when the
  agent's own set_story_access call fails
- No questions, answers or declines; an asked question is not reopened; the
  model is offered only the panel tools and never sees asked questions
- Non-member: the generic 403; too long, empty or unreadable audio: 400
- /api/audio: the recorder hears the whole session; a plain member only the
  story's range, once it is published
- The feed and the lifeline pick up the published story
- Failures are logged with the session id, never the transcript text
- Private is applied right after save_story; a circle recording never widens
  access afterwards; if private cannot be enforced the stories are hidden
- The panel archivist cannot read or cite another session of the circle
"""

from __future__ import annotations

import io
import logging
import re
import wave

import pytest

from core.enums import QuestionStatus, Role, SessionKind, SessionStart, StoryStatus
from core.models import Person, Question, Segment, Story, StorySubject
from core.models import Session as OrmSession
from core.services.chat_tools import set_story_access_data
from server.speech import FakeSTT
from tests.test_api import _add_member, _client, _make_silent_pcm, anyio_backend, test_app  # noqa: F401
from tests.test_archivist_agent import DynamicScriptedLLM, FakeArchiveBridge, last_tool_json
from tests.test_chat_agent import _tool_use

TOLD = "Grandma taught me to bake bread when I was eight"


# ---------------------------------------------------------------------------
# Fixture and helpers
# ---------------------------------------------------------------------------

class RecordingBridge(FakeArchiveBridge):
    """FakeArchiveBridge plus set_story_access, usable as `async with`."""

    fail_access = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def call_tool(self, name, arguments):
        if name == "set_story_access":
            self.tool_calls.append((name, arguments))
            if RecordingBridge.fail_access:
                raise RuntimeError("simulated failure")
            set_story_access_data(self._db, self._person_id, self._circle_id,
                                  arguments["story_id"], arguments["type"])
            self._db.commit()
            return {"status": "ok"}
        return await super().call_tool(name, arguments)


def _wav(duration_ms: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16_000)
        wf.writeframes(_make_silent_pcm(duration_ms))
    return buf.getvalue()


def _archivist_script(fatma, elif_):
    """Transcript → save_story (wrong teller on purpose) → question tools → done."""
    def first(messages):
        sid = re.search(r"session_id (\S+)\.", messages[0]["content"][0]["text"]).group(1)
        return [_tool_use("get_session_transcript", {"session_id": sid})]

    def save(messages):
        t = last_tool_json(messages)
        seg = t["segments"][0]
        return [_tool_use("save_story", {
            "title": "Bread with Grandma",
            "summary": "Elif remembers Fatma teaching her to bake bread.",
            "teller_id": fatma.id,
            "subjects": [{"person_id": fatma.id, "period": "retirement"},
                         {"person_id": elif_.id, "period": "childhood"}],
            "sources": [{"session_id": t["session_id"],
                         "start_ms": seg["start_ms"], "end_ms": seg["end_ms"]}],
        })]

    def questions(messages):
        sid = re.search(r"session_id (\S+)\.", messages[0]["content"][0]["text"]).group(1)
        story_id = last_tool_json(messages)["story_id"]
        q = {"question_id": "any", "session_id": sid, "start_ms": 0, "end_ms": 1000}
        return [
            _tool_use("add_question", {"text": "What else did Grandma bake?", "source": "follow_up"}),
            _tool_use("record_answer", {**q, "story_id": story_id}),
            _tool_use("mark_question_declined", q),
        ]

    return DynamicScriptedLLM([first, save, questions, "Saved one story."])


@pytest.fixture
def rec(test_app, monkeypatch):
    app, db, fatma, elif_, circle, q, *_ = test_app
    import server.routers.recordings as rec_r
    import server.routers.device as dev_r
    from core.db import SessionLocal

    monkeypatch.setattr(rec_r, "SessionLocal", SessionLocal)   # patched by test_app
    bridges: list[RecordingBridge] = []

    def _bridge(person_id, circle_id, session_id=None):
        b = RecordingBridge(db, person_id, circle_id)
        bridges.append(b)
        return b

    monkeypatch.setattr(rec_r, "MCPBridge", _bridge)
    llms = [_archivist_script(fatma, elif_)]
    monkeypatch.setattr(rec_r, "archivist_llm", lambda: llms[0])
    stt = FakeSTT(text=TOLD, duration_ms=2000)
    app.dependency_overrides[dev_r._get_stt] = lambda: stt
    RecordingBridge.fail_access = False

    ali = _add_member(db, circle, "Ali", "grandson")
    db.commit()
    return dict(app=app, db=db, fatma=fatma, elif_=elif_, ali=ali, circle=circle, q=q,
                llms=llms, bridges=bridges, stt=stt, audio_dir=test_app[-1])


async def _record(app, person, audio=None, access=None):
    data = {"access": access} if access else {}
    async with _client(app) as c:
        return await c.post(
            "/api/recordings",
            headers={"x-person-id": person.id},
            files={"audio": ("rec.wav", _wav(2000) if audio is None else audio, "audio/wav")},
            data=data,
        )


async def _get(app, url, person):
    async with _client(app) as c:
        return await c.get(url, headers={"x-person-id": person.id})


def _stories(db, session_id):
    db.expire_all()
    return [s for s in db.query(Story).all()
            if any(src["session_id"] == session_id for src in s.sources)]


# ---------------------------------------------------------------------------
# Session, segment, story
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_returns_202_and_creates_panel_recording_session(rec):
    db, elif_ = rec["db"], rec["elif_"]
    r = await _record(rec["app"], elif_)
    assert r.status_code == 202
    body = r.json()
    assert set(body) == {"session_id", "started_by", "processing"}
    assert body["started_by"] == "panel_recording" and body["processing"] == "started"

    db.expire_all()
    sess = db.get(OrmSession, body["session_id"])
    assert sess.started_by == SessionStart.panel_recording
    assert sess.kind == SessionKind.solo
    assert sess.participant_ids == [elif_.id]
    assert sess.ended_at is not None
    assert (rec["audio_dir"] / f"{sess.id}.wav").exists()

    segs = db.query(Segment).filter(Segment.session_id == sess.id).all()
    assert len(segs) == 1
    seg = segs[0]
    assert seg.speaker_id == elif_.id and seg.transcript == TOLD
    assert (seg.start_ms, seg.end_ms) == (0, 2000)
    assert seg.words and seg.words[0]["w"] == "Grandma"
    assert "Fatma" in rec["stt"].prompts[0]   # member names as the Whisper hint


@pytest.mark.anyio
async def test_teller_is_the_recorder_and_center_can_be_a_subject(rec):
    db, fatma, elif_ = rec["db"], rec["fatma"], rec["elif_"]
    sid = (await _record(rec["app"], elif_)).json()["session_id"]

    [story] = _stories(db, sid)
    assert story.teller_id == elif_.id          # the model passed Fatma; code overrides
    assert story.status == StoryStatus.pending
    assert story.access["type"] == "circle"
    subjects = {s.person_id: s.period
                for s in db.query(StorySubject).filter(StorySubject.story_id == story.id)}
    assert subjects == {fatma.id: "retirement", elif_.id: "childhood"}

    first_msg = rec["llms"][0].calls[0]["messages"][0]["content"][0]["text"]
    assert fatma.id in first_msg and "the center of the circle" in first_msg


@pytest.mark.parametrize("fail_access", [False, True])
@pytest.mark.anyio
async def test_private_access_only_teller_sees_it(rec, fail_access):
    RecordingBridge.fail_access = fail_access   # the run's own call fails: enforced afterwards
    app, db = rec["app"], rec["db"]
    sid = (await _record(app, rec["elif_"], access="private")).json()["session_id"]

    [story] = _stories(db, sid)
    assert story.access["type"] == "private"
    story.status = StoryStatus.published
    db.commit()
    assert (await _get(app, f"/api/stories/{story.id}", rec["elif_"])).status_code == 200
    for viewer in (rec["fatma"], rec["ali"]):
        assert (await _get(app, f"/api/stories/{story.id}", viewer)).status_code == 404


@pytest.mark.anyio
async def test_no_questions_answers_or_declines(rec):
    db, q = rec["db"], rec["q"]
    q.status = QuestionStatus.asked             # asked in a live device session
    db.commit()
    before = db.query(Question).count()

    await _record(rec["app"], rec["elif_"])

    db.expire_all()
    assert db.query(Question).count() == before
    assert db.get(Question, q.id).status == QuestionStatus.asked   # not reopened
    assert db.get(Question, q.id).answer is None

    llm = rec["llms"][0]
    offered = {t["toolSpec"]["name"] for t in llm.calls[0]["tools"]["tools"]}
    assert offered == {"get_session_transcript", "save_story", "search_archive", "link_stories"}
    transcript = llm.calls[1]["messages"][2]["content"][0]["toolResult"]["content"][0]["json"]
    assert transcript["asked_questions"] == []
    called = [name for b in rec["bridges"] for name, _ in b.tool_calls]
    assert not {"add_question", "record_answer", "mark_question_declined",
                "reopen_question"} & set(called)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_non_member_gets_generic_403(rec):
    db = rec["db"]
    stranger = Person(name="Stranger", birth_year=1990, language="en")
    db.add(stranger); db.commit()
    r = await _record(rec["app"], stranger)
    assert r.status_code == 403
    assert r.json()["detail"] == "Not a member of any circle."


@pytest.mark.parametrize("audio, access, detail", [
    (_wav(3 * 60 * 1000 + 1000), None, "A recording can be at most 3 minutes long."),
    (b"", None, "The recording is empty."),
    (_wav(0), None, None),   # decode error or no samples: 400 either way
    (_wav(200), None, "The recording is empty."),
    (b"not audio at all", None, "Could not read the audio."),
    (None, "selected", "access must be 'circle' or 'private'."),
], ids=["too_long", "no_bytes", "no_frames", "too_short", "not_audio", "bad_access"])
@pytest.mark.anyio
async def test_bad_audio_or_access_is_400_and_creates_nothing(rec, audio, access, detail):
    db = rec["db"]
    before = db.query(OrmSession).count()
    r = await _record(rec["app"], rec["elif_"], audio=audio, access=access)
    assert r.status_code == 400
    if detail:
        assert r.json()["detail"] == detail
    assert db.query(OrmSession).count() == before


# ---------------------------------------------------------------------------
# Audio, feed, lifeline
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_recorder_hears_whole_session_member_only_after_publish(rec):
    app, db, ali = rec["app"], rec["db"], rec["ali"]
    sid = (await _record(app, rec["elif_"])).json()["session_id"]
    [story] = _stories(db, sid)
    src = story.sources[0]
    url = f"/api/audio/{sid}?start={src['start_ms']}&end={src['end_ms']}"

    assert (await _get(app, url, rec["elif_"])).status_code == 200
    assert (await _get(app, url, ali)).status_code == 403          # pending

    story.status = StoryStatus.published
    db.commit()
    assert (await _get(app, url, ali)).status_code == 200


@pytest.mark.anyio
async def test_feed_and_lifeline_pick_up_the_story(rec):
    app, db, ali, fatma, elif_ = rec["app"], rec["db"], rec["ali"], rec["fatma"], rec["elif_"]
    sid = (await _record(app, elif_)).json()["session_id"]
    [story] = _stories(db, sid)
    story.status = StoryStatus.published
    db.commit()

    feed = (await _get(app, "/api/feed", ali)).json()
    assert story.id in [i["story"]["id"] for i in feed["items"] if i["type"] == "story_published"]

    for person, period in ((fatma, "retirement"), (elif_, "childhood")):
        life = (await _get(app, f"/api/lifeline/{person.id}", ali)).json()
        ids = [s["id"] for p in life["periods"] if p["period"] == period for s in p["stories"]]
        assert ids == [story.id]
        [card] = [s for p in life["periods"] for s in p["stories"]]
        assert card["teller"]["id"] == elif_.id


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------

class _Boom:
    def converse(self, *a, **k):
        raise RuntimeError(TOLD)   # an error that carries the transcript text


class _BrokenSTT:
    async def transcribe(self, pcm, prompt=""):
        raise RuntimeError(TOLD)


@pytest.mark.parametrize("broken", ["archivist", "stt"])
@pytest.mark.anyio
async def test_failures_log_session_id_never_transcript(rec, caplog, broken):
    import server.routers.device as dev_r
    if broken == "archivist":
        rec["llms"][0] = _Boom()
    else:
        rec["app"].dependency_overrides[dev_r._get_stt] = lambda: _BrokenSTT()

    with caplog.at_level(logging.INFO, logger="server"):
        r = await _record(rec["app"], rec["elif_"])
    assert r.status_code == 202
    sid = r.json()["session_id"]
    assert any(sid in rec_.getMessage() and rec_.levelno >= logging.ERROR
               for rec_ in caplog.records)
    assert "bake bread" not in caplog.text
    assert _stories(rec["db"], sid) == []


# ---------------------------------------------------------------------------
# Access is applied at once, never widened, and fails closed
# ---------------------------------------------------------------------------

class _SpyLLM(DynamicScriptedLLM):
    """Records the access of the session's stories at every model call."""

    def __init__(self, inner, db, on_call=None):
        super().__init__(inner._script)
        self.db, self.seen, self.on_call = db, [], on_call

    def converse(self, system, messages, tools=None):
        self.db.expire_all()
        self.seen.append([s.access["type"] for s in self.db.query(Story).all()])
        if self.on_call:
            self.on_call(self.db)
        return super().converse(system, messages, tools)


@pytest.mark.anyio
async def test_private_applied_right_after_save_story(rec):
    spy = _SpyLLM(rec["llms"][0], rec["db"])
    rec["llms"][0] = spy
    await _record(rec["app"], rec["elif_"], access="private")
    # Call 3 is the first model call after save_story: already private.
    assert spy.seen[2] == ["private"]


@pytest.mark.anyio
async def test_circle_recording_never_widens_access_set_by_teller(rec):
    def teller_makes_private(db):
        for s in db.query(Story).all():
            s.access = {"type": "private", "person_ids": []}
        db.commit()

    rec["llms"][0] = _SpyLLM(rec["llms"][0], rec["db"], on_call=teller_makes_private)
    sid = (await _record(rec["app"], rec["elif_"])).json()["session_id"]
    [story] = _stories(rec["db"], sid)
    assert story.access["type"] == "private"


@pytest.mark.anyio
async def test_stories_hidden_when_private_cannot_be_enforced(rec, monkeypatch):
    import server.routers.recordings as rec_r
    RecordingBridge.fail_access = True

    def broken(*a):
        raise RuntimeError("db down")

    monkeypatch.setattr(rec_r, "_enforce_private", broken)
    sid = (await _record(rec["app"], rec["elif_"], access="private")).json()["session_id"]
    [story] = _stories(rec["db"], sid)
    assert story.status == StoryStatus.hidden
    for viewer in (rec["fatma"], rec["ali"]):
        assert (await _get(rec["app"], f"/api/stories/{story.id}", viewer)).status_code == 404


@pytest.mark.anyio
async def test_panel_archivist_cannot_read_or_cite_another_session(rec):
    from tests.test_api import _session_with_pcm
    other = _session_with_pcm(rec["db"], rec["circle"], [rec["fatma"]],
                              SessionStart.spontaneous, rec["audio_dir"])
    rec["llms"][0] = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": other})],
        [_tool_use("save_story", {
            "title": "x", "summary": "x", "teller_id": rec["elif_"].id, "subjects": [],
            "sources": [{"session_id": other, "start_ms": 0, "end_ms": 500}]})],
        "done",
    ])
    await _record(rec["app"], rec["elif_"])
    called = [(n, a) for b in rec["bridges"] for n, a in b.tool_calls]
    assert not any(a.get("session_id") == other or
                   any(s.get("session_id") == other for s in a.get("sources", []))
                   for _, a in called)
    assert _stories(rec["db"], other) == []


@pytest.mark.anyio
async def test_center_gets_generic_403_on_members_private_recording(rec):
    app, db, fatma = rec["app"], rec["db"], rec["fatma"]
    sid = (await _record(app, rec["elif_"], access="private")).json()["session_id"]
    [story] = _stories(db, sid)
    story.status = StoryStatus.published
    db.commit()
    src = story.sources[0]
    whole = await _get(app, f"/api/audio/{sid}?start=0&end=2000", fatma)
    rng = await _get(app, f"/api/audio/{sid}?start={src['start_ms']}&end={src['end_ms']}", fatma)
    for r in (whole, rng):
        assert r.status_code == 403
        assert r.json()["detail"] == "You do not have access to this audio."
    assert (await _get(app, f"/api/audio/{sid}?start=0&end=2000", rec["elif_"])).status_code == 200
