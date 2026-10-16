"""
The core loop, end to end, through the real HTTP endpoints (PROJECT.md, the
16 Ekim decision point):

  Elif asks a question in the panel  -> POST /api/questions
  Fatma's agent asks it              -> POST /api/device/session/start
  Fatma answers                      -> POST /api/device/turn
  the session ends                   -> POST /api/device/session/end
  the archivist records the answer   -> background task (real ArchivistAgent)
  the story is published             -> publish_due_stories() with DEMO_NOW +24 h
  Elif sees the answer in her feed   -> GET /api/feed
  and hears it in Fatma's own voice  -> GET /api/audio (the exact bytes Fatma spoke)

Fakes: STT, TTS, both LLMs (chat agent, archivist + its answer checker) and the
MCP transport (in-process bridges calling the real service functions on the
same database). Everything else is the real code.
"""

from __future__ import annotations

import struct
from datetime import datetime, timedelta

import pytest

from core.enums import AccessType, QuestionStatus, Role, StoryStatus
from core.models import Membership, Person, Question, Story
from core.services.publisher import publish_due_stories
from server.agents.archivist_agent import ArchivistAgent
from tests.test_api import _client, _make_wav_bytes, _set_llm_script, test_app  # noqa: F401
from tests.test_archivist_agent import DynamicScriptedLLM, FakeArchiveBridge, last_tool_json
from tests.test_chat_agent import ScriptedLLM, _tool_use

QUESTION = "Did you ever meet anyone famous growing up?"
ANSWER = "Yes! When I was sixteen, a famous singer came to our village fair and shook my hand."


def _voice_pcm(ms: int) -> bytes:
    """A recognisable, non-silent 16 kHz mono signal standing in for Fatma's voice."""
    n = 16 * ms
    return struct.pack(f"<{n}h", *[(i * 37) % 20_000 - 10_000 for i in range(n)])


@pytest.mark.anyio
async def test_core_loop_question_to_answer_in_fatmas_voice(test_app, monkeypatch):
    import server.routers.device as dev_r

    app, db, fatma, elif_, circle, *_ = test_app
    can = Person(name="Can", birth_year=2006, language="en")
    outsider = Person(name="Outsider", birth_year=1990, language="en")
    db.add_all([can, outsider]); db.flush()
    db.add(Membership(person_id=can.id, circle_id=circle.id, role=Role.member,
                      relation_to_center="grandson"))
    db.commit()

    # The real archivist, with a scripted LLM, a "yes" checker and an in-process bridge.
    archive_runs = []

    async def _real_archivist(session_id, person_id, circle_id):
        found = {}

        def save_story(msgs):
            transcript = last_tool_json(msgs)
            seg = [s for s in transcript["segments"] if s["speaker_id"] == fatma.id][0]
            found["range"] = (seg["start_ms"], seg["end_ms"])
            return [_tool_use("save_story", {
                "title": "The Singer at the Fair",
                "summary": "Fatma remembers a famous singer shaking her hand at the village fair.",
                "teller_id": fatma.id,
                "subjects": [{"person_id": fatma.id, "period": "youth"}],
                "sources": [{"session_id": session_id, "start_ms": seg["start_ms"], "end_ms": seg["end_ms"]}],
            })]

        def record_answer(msgs):
            return [_tool_use("record_answer", {
                "question_id": question_id, "story_id": last_tool_json(msgs)["story_id"],
                "start_ms": found["range"][0], "end_ms": found["range"][1],
            })]

        llm = DynamicScriptedLLM([
            [_tool_use("get_session_transcript", {"session_id": session_id})],
            save_story,
            record_answer,
            "Saved one story and one answer.",
        ])
        checker = ScriptedLLM(["yes"])
        agent = ArchivistAgent(llm=llm, person_id=person_id, circle_id=circle_id,
                               bridge=FakeArchiveBridge(db, person_id, circle_id), checker_llm=checker)
        result = await agent.run(session_id)
        archive_runs.append((result, checker, found))

    monkeypatch.setattr(dev_r, "_run_archivist", _real_archivist)

    async with _client(app) as c:
        # 1. Elif asks in the panel.
        r = await c.post("/api/questions", headers={"x-person-id": elif_.id},
                         json={"target_person_id": fatma.id, "text": QUESTION})
        assert r.status_code == 200 and r.json()["status"] == "waiting"
        question_id = r.json()["question"]["id"]

        # 2. Fatma's agent asks it at the start of a session.
        _set_llm_script(test_app, [
            [_tool_use("get_session_context", {}), _tool_use("get_pending_questions", {"limit": 5})],
            [_tool_use("mark_question_asked", {"question_id": question_id})],
            "Your granddaughter Elif would love to know, did you ever meet anyone famous growing up?",
            "What a wonderful memory. What did the singer say to you?",
        ])
        start = (await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})).json()
        session_id = start["session_id"]
        assert [card["type"] for card in start["cards"]] == ["question"]
        assert start["cards"][0]["question_id"] == question_id
        db.expire_all()
        assert db.get(Question, question_id).status == QuestionStatus.asked

        # 3. Fatma answers in her own voice.
        app.dependency_overrides[dev_r._get_stt]()._text = ANSWER
        voice = _voice_pcm(700)
        turn = (await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                             data={"session_id": session_id},
                             files={"audio": ("answer.wav", _make_wav_bytes(voice), "audio/wav")})).json()
        assert turn["heard_text"] == ANSWER

        # 4. The session ends; the archivist runs in the background.
        end = await c.post("/api/device/session/end", headers={"x-person-id": fatma.id},
                           json={"session_id": session_id})
        assert end.status_code == 200
        assert len(archive_runs) == 1
        result, checker, found = archive_runs[0]
        assert result.answers_recorded == [question_id]
        assert QUESTION in checker.calls[0]["messages"][0]["content"][0]["text"]
        assert ANSWER in checker.calls[0]["messages"][0]["content"][0]["text"]
        start_ms, end_ms = found["range"]
        assert (start_ms, end_ms) == (400, 1100)   # FakeTTS opening reply is 0-400 ms

        db.expire_all()
        q = db.get(Question, question_id)
        assert q.status == QuestionStatus.answered
        story = db.get(Story, q.answer["story_id"])
        assert story.status == StoryStatus.pending

        # 5. Before publishing: nothing in Elif's feed, and the answer is not audible yet.
        feed = (await c.get("/api/feed", headers={"x-person-id": elif_.id})).json()
        assert feed == {"items": []}
        url = f"/api/audio/{session_id}?start={start_ms}&end={end_ms}"
        assert (await c.get(url, headers={"x-person-id": elif_.id})).status_code == 403

        # 6. The publisher, 24 hours later.
        monkeypatch.setenv("DEMO_NOW", (datetime.now().astimezone() + timedelta(hours=24, minutes=1)).isoformat())
        assert publish_due_stories(db) == [story.id]

        # 7. Elif sees the answer in her feed ...
        feed = (await c.get("/api/feed", headers={"x-person-id": elif_.id})).json()
        answered = [i for i in feed["items"] if i["type"] == "question_answered"]
        assert len(answered) == 1
        card = answered[0]
        assert card["question"] == {"id": question_id, "text": QUESTION, "asker_id": elif_.id}
        assert card["answer"]["story_title"] == "The Singer at the Fair"
        assert card["answer"]["teller"]["id"] == fatma.id
        assert card["answer"]["audio_url"] == url

        # ... and hears it in Fatma's own voice: exactly the bytes Fatma spoke.
        audio = await c.get(card["answer"]["audio_url"], headers={"x-person-id": elif_.id})
        assert audio.status_code == 200
        assert audio.headers["content-type"] == "audio/wav"
        assert audio.content[44:] == voice                 # 44-byte WAV header, then PCM

        # 8. Who else may hear it: not a non-member; not Can once the story is for Elif only.
        assert (await c.get(url, headers={"x-person-id": outsider.id})).status_code == 403
        assert (await c.get(url, headers={"x-person-id": can.id})).status_code == 200   # circle story
        story = db.get(Story, story.id)
        story.access = {"type": AccessType.selected, "person_ids": [elif_.id]}
        db.commit()
        assert (await c.get(url, headers={"x-person-id": can.id})).status_code == 403
        assert (await c.get(url, headers={"x-person-id": elif_.id})).status_code == 200
        can_feed = (await c.get("/api/feed", headers={"x-person-id": can.id})).json()
        assert can_feed == {"items": []}
