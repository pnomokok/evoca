"""
Tests for server.agents.archivist_agent.ArchivistAgent.

No network, no real Bedrock.  Uses:
  - ScriptedLLM (from test_chat_agent), extended so a script entry can be a
    function of the conversation so far (needed to use the story_id that
    save_story returned).
  - FakeArchiveBridge : calls the real archive service functions on an
    in-memory DB, and also exposes a chat tool to check it is filtered out.

Coverage
--------
- Full run: transcript → save_story → record_answer → add_question.
- Summary fields: story_ids, answers_recorded, questions_added, trace, latency.
- Question limit enforced in the agent (third add_question never reaches the bridge).
- Duplicate guard: a question the companion already asked in the session, or one
  equal to a waiting / asked question, is rejected before the bridge.
- Chat-agent tools are not offered to the model and are rejected if called.
- Tool errors (e.g. private overlap) are recorded in the trace and fed back.
- max-rounds guard: loop exits after _MAX_TOOL_ROUNDS.
- Model id comes from EVOCA_ARCHIVIST_MODEL.
- Answer check: record_answer goes through only when the checker says the
  speaker's words in the range answer the question ("anyone famous" vs the
  Uncle Ahmed story is rejected; a real answer is accepted).
- Declines and reopening: a confirmed decline sets "declined" and is never
  reopened; an unconfirmed decline is not recorded; every other asked,
  unanswered question goes back to "waiting" at the end of the run; a declined
  question stays declined after a later session.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

import pytest

from core.enums import QuestionStatus, StoryStatus
from core.models import Question, Segment, Story
from core.services.chat_tools import search_archive_data
from core.services.session_tools import get_pending_questions_data
from core.services.archive_tools import (
    add_question_data,
    add_refused_topic_data,
    find_gaps_data,
    link_stories_data,
    get_session_transcript_data,
    mark_question_declined_data,
    merge_stories_data,
    record_answer_data,
    reopen_question_data,
    save_story_data,
)
from server.agents.archivist_agent import (
    _MAX_QUESTIONS,
    _MAX_TOOL_ROUNDS,
    DEFAULT_ARCHIVIST_MODEL,
    ArchivistAgent,
    archivist_model_id,
    checker_said_yes,
    normalize_question,
    possible_split,
)
from tests.test_archive_tools import PRIVATE_TEXT, db, w  # noqa: F401  (fixtures)
from tests.test_chat_agent import ScriptedLLM, _tool_use


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class DynamicScriptedLLM(ScriptedLLM):
    """ScriptedLLM whose entries may also be callables(messages) -> entry."""

    def converse(self, system, messages, tools=None) -> dict:
        idx = min(self._idx, len(self._script) - 1)
        entry = self._script[idx]
        if callable(entry):
            self._script[idx] = entry(messages)
        return super().converse(system, messages, tools)


def last_tool_json(messages: list[dict], tool_index: int = 0) -> Any:
    """Return the JSON of the tool_index-th toolResult in the last user message."""
    results = [b["toolResult"] for b in messages[-1]["content"] if "toolResult" in b]
    return results[tool_index]["content"][0].get("json")


def _spec(name: str) -> dict:
    return {"toolSpec": {"name": name, "description": name,
                         "inputSchema": {"json": {"type": "object"}}}}


class FakeArchiveBridge:
    """Calls the real archive services on the in-memory DB. No network."""

    def __init__(self, db, person_id: str, circle_id: str, session_id: str | None = None) -> None:
        self._db = db
        self._person_id = person_id
        self._circle_id = circle_id
        self.session_id = session_id   # like the X-Evoca-Session-Id header
        self.tool_calls: list[tuple[str, dict]] = []

    async def bedrock_tool_config(self) -> dict:
        return {"tools": [_spec(n) for n in (
            "get_session_transcript", "save_story", "record_answer",
            "add_question", "mark_question_declined", "add_refused_topic",
            "search_archive", "link_stories", "find_gaps", "mark_question_asked",
        )]}

    async def call_tool(self, name: str, arguments: dict) -> Any:
        self.tool_calls.append((name, arguments))
        db, pid, cid = self._db, self._person_id, self._circle_id
        if name == "get_session_transcript":
            return asdict(get_session_transcript_data(db, pid, cid, arguments["session_id"]))
        if name == "save_story":
            story_id = save_story_data(db, pid, cid, **arguments)
            db.commit()
            return {"story_id": story_id}
        if name == "record_answer":
            answer = record_answer_data(db, pid, cid, **arguments)
            db.commit()
            return {"status": "ok", "question_id": arguments["question_id"], "answer": answer}
        if name == "add_question":
            r = add_question_data(db, pid, cid, **arguments)
            db.commit()
            return r
        if name == "get_pending_questions":
            # Used internally by the duplicate guard; the real server wraps a list.
            items = get_pending_questions_data(db, pid, cid, arguments.get("limit", 5))
            return {"result": [asdict(i) for i in items]}
        if name == "mark_question_declined":
            mark_question_declined_data(db, pid, cid, **arguments)
            db.commit()
            return {"status": "ok", "question_id": arguments["question_id"]}
        if name == "add_refused_topic":
            r = add_refused_topic_data(db, pid, cid, self.session_id or "", **arguments)
            db.commit()
            return {"status": "ok", **r}
        if name == "search_archive":
            # The real server wraps a list.
            return {"result": search_archive_data(db, pid, cid, **arguments)}
        if name == "link_stories":
            r = link_stories_data(db, pid, cid, self.session_id or "", **arguments)
            db.commit()
            return {"status": "ok", **r}
        if name == "find_gaps":
            return {"result": find_gaps_data(db, pid, cid, **arguments)}
        if name == "merge_stories":
            r = merge_stories_data(db, pid, cid, self.session_id or "", **arguments)
            db.commit()
            return {"status": "ok", **r}
        if name == "reopen_question":
            reopen_question_data(db, pid, cid, **arguments)
            db.commit()
            return {"status": "ok", "question_id": arguments["question_id"]}
        raise RuntimeError(f"Unknown tool: {name}")


def _make_agent(w, llm, checker=None) -> tuple[ArchivistAgent, FakeArchiveBridge]:
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id)
    agent = ArchivistAgent(story_guard_llm=ScriptedLLM(["no"]), llm=llm, person_id=w.fatma.id,
                           circle_id=w.circle.id, bridge=bridge, checker_llm=checker)
    return agent, bridge


def _story_args(w, start_ms=0, end_ms=10_000) -> dict:
    return {
        "title": "By the River",
        "summary": "Fatma remembers growing up next to the river.",
        "teller_id": w.fatma.id,
        "subjects": [{"person_id": w.fatma.id, "period": "childhood"}],
        "sources": [{"session_id": w.sess.id, "start_ms": start_ms, "end_ms": end_ms}],
    }


def full_script(w) -> list:
    """Transcript → story → answer + one follow-up → final text."""
    return [
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("save_story", _story_args(w))],
        lambda msgs: [
            _tool_use("record_answer", {
                "question_id": w.q_asked.id,
                "story_id": last_tool_json(msgs)["story_id"],
                "start_ms": 0, "end_ms": 10_000,
            }),
            _tool_use("add_question", {
                "text": "What did you catch when you fished in the river?",
                "source": "follow_up", "period": "childhood",
            }),
        ],
        "Saved one story, one answer and one question.",
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_full_run_creates_story_answer_and_question(w):
    llm = DynamicScriptedLLM(full_script(w))
    agent, bridge = _make_agent(w, llm, checker=ScriptedLLM(["yes"]))
    result = await agent.run(w.sess.id)

    assert result.session_id == w.sess.id
    assert len(result.story_ids) == 1
    story = w.db.get(Story, result.story_ids[0])
    assert story.title == "By the River"
    assert story.status == StoryStatus.pending

    assert result.answers_recorded == [w.q_asked.id]
    q = w.db.get(Question, w.q_asked.id)
    assert q.status == QuestionStatus.answered
    assert q.answer["story_id"] == story.id

    assert len(result.questions_added) == 1
    assert result.questions_added[0]["status"] == "waiting"

    assert result.final_text == "Saved one story, one answer and one question."
    assert [t.tool for t in result.trace] == [
        "get_session_transcript", "save_story", "record_answer", "add_question",
    ]
    assert not any(t.is_error for t in result.trace)
    assert set(result.latency) == {"llm_ms", "tools_ms", "total_ms"}


@pytest.mark.anyio
async def test_first_message_names_the_session(w):
    llm = DynamicScriptedLLM(["Nothing to archive."])
    agent, _ = _make_agent(w, llm)
    await agent.run(w.sess.id)
    first = llm.calls[0]["messages"][0]["content"][0]["text"]
    assert w.sess.id in first


@pytest.mark.anyio
async def test_chat_tools_are_not_offered(w):
    llm = DynamicScriptedLLM(["done"])
    agent, _ = _make_agent(w, llm)
    await agent.run(w.sess.id)
    names = {t["toolSpec"]["name"] for t in llm.calls[0]["tools"]["tools"]}
    assert names == {"get_session_transcript", "save_story", "record_answer", "add_question",
                     "mark_question_declined", "add_refused_topic", "search_archive",
                     "link_stories", "find_gaps"}
    assert "reopen_question" not in names   # called by the agent's own code, never by the model


@pytest.mark.anyio
async def test_chat_tool_call_is_rejected(w):
    llm = DynamicScriptedLLM([
        [_tool_use("mark_question_asked", {"question_id": w.q_waiting.id})],
        "done",
    ])
    agent, bridge = _make_agent(w, llm)
    result = await agent.run(w.sess.id)
    assert result.trace[0].is_error
    assert "mark_question_asked" not in [n for n, _ in bridge.tool_calls]
    assert w.db.get(Question, w.q_waiting.id).status == QuestionStatus.waiting


@pytest.mark.anyio
async def test_question_limit_enforced(w):
    asks = [
        _tool_use("add_question", {"text": f"Question number {i}?", "source": "follow_up"})
        for i in range(_MAX_QUESTIONS + 1)
    ]
    llm = DynamicScriptedLLM([asks, "done"])
    agent, bridge = _make_agent(w, llm)
    result = await agent.run(w.sess.id)

    assert len(result.questions_added) == _MAX_QUESTIONS
    assert [n for n, _ in bridge.tool_calls].count("add_question") == _MAX_QUESTIONS
    assert result.trace[-1].is_error
    assert "limit" in result.trace[-1].result_preview.lower()
    added = w.db.query(Question).filter(Question.asker_id.is_(None)).count()
    assert added == _MAX_QUESTIONS


@pytest.mark.anyio
async def test_private_overlap_error_is_fed_back(w):
    llm = DynamicScriptedLLM([
        [_tool_use("save_story", _story_args(w, 0, 30_000))],
        [_tool_use("save_story", _story_args(w, 0, 10_000))],
        "done",
    ])
    agent, _ = _make_agent(w, llm)
    result = await agent.run(w.sess.id)

    assert result.trace[0].is_error
    assert not result.trace[1].is_error
    assert len(result.story_ids) == 1
    # The error text went back to the model as a tool result (message 2:
    # user prompt, assistant tool use, then the tool results).
    error_msg = llm.calls[1]["messages"][2]["content"][0]["toolResult"]["content"][0]["text"]
    assert "overlaps a private part" in error_msg
    assert PRIVATE_TEXT not in error_msg


@pytest.mark.anyio
async def test_max_rounds_guard(w):
    script = [
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})]
        for _ in range(_MAX_TOOL_ROUNDS + 3)
    ]
    llm = DynamicScriptedLLM(script)
    agent, _ = _make_agent(w, llm)
    result = await agent.run(w.sess.id)
    assert len(llm.calls) == _MAX_TOOL_ROUNDS
    assert len(result.trace) == _MAX_TOOL_ROUNDS


def test_archivist_model_from_env(monkeypatch):
    monkeypatch.delenv("EVOCA_ARCHIVIST_MODEL", raising=False)
    assert archivist_model_id() == DEFAULT_ARCHIVIST_MODEL == "us.amazon.nova-2-lite-v1:0"
    monkeypatch.setenv("EVOCA_ARCHIVIST_MODEL", "us.anthropic.some-model")
    assert archivist_model_id() == "us.anthropic.some-model"


# ---------------------------------------------------------------------------
# Duplicate-question guard
# ---------------------------------------------------------------------------

def test_normalize_question():
    assert normalize_question("  What was  Zehra like?! ") == "what was zehra like"
    assert normalize_question("WHAT, was Zehra like") == "what was zehra like"


def _added_questions(w) -> list[str]:
    return [q.text for q in w.db.query(Question).filter(Question.asker_id.is_(None))]


@pytest.mark.anyio
async def test_question_already_asked_by_companion_rejected(w):
    # The companion segment says: "What did you do by the river?"
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("add_question", {"text": "what did you do by the RIVER", "source": "follow_up"})],
        "done",
    ])
    agent, bridge = _make_agent(w, llm)
    result = await agent.run(w.sess.id)

    assert result.trace[-1].tool == "add_question"
    assert result.trace[-1].is_error
    assert "already asked" in result.trace[-1].result_preview
    assert result.questions_added == []
    assert "add_question" not in [n for n, _ in bridge.tool_calls]
    assert _added_questions(w) == []


@pytest.mark.anyio
async def test_question_equal_to_waiting_or_asked_rejected(w):
    llm = DynamicScriptedLLM([
        [
            _tool_use("add_question", {"text": "What was your first job", "source": "follow_up"}),
            _tool_use("add_question", {"text": "Where did you grow up?!", "source": "follow_up"}),
        ],
        "done",
    ])
    agent, bridge = _make_agent(w, llm)
    result = await agent.run(w.sess.id)

    # Equal to w.q_waiting and w.q_asked after normalization.
    assert [t.is_error for t in result.trace] == [True, True]
    assert all("already waiting or asked" in t.result_preview for t in result.trace)
    assert _added_questions(w) == []
    # The waiting questions are read once at the start (for the first message);
    # the guard looked up the transcript itself.
    assert [n for n, _ in bridge.tool_calls][:2] == ["get_pending_questions", "get_session_transcript"]


@pytest.mark.anyio
async def test_same_new_question_twice_in_one_run_rejected(w):
    ask = {"text": "What fish did you catch?", "source": "follow_up"}
    llm = DynamicScriptedLLM([[_tool_use("add_question", ask)], [_tool_use("add_question", ask)], "done"])
    agent, _ = _make_agent(w, llm)
    result = await agent.run(w.sess.id)

    assert [t.is_error for t in result.trace] == [False, True]
    assert _added_questions(w) == ["What fish did you catch?"]


@pytest.mark.anyio
async def test_new_question_passes_guard(w):
    llm = DynamicScriptedLLM([
        [_tool_use("add_question", {"text": "What did your father do?", "source": "follow_up"})],
        "done",
    ])
    agent, _ = _make_agent(w, llm)
    result = await agent.run(w.sess.id)
    assert not result.trace[0].is_error
    assert _added_questions(w) == ["What did your father do?"]


# ---------------------------------------------------------------------------
# Answer check
# ---------------------------------------------------------------------------

FAMOUS_Q = "Did you ever meet anyone famous growing up?"
UNCLE_AHMED = (
    "My uncle had just bought an old stone house in a small village. We were lost for "
    "two hours. Uncle Ahmed was standing on the porch with a big smile, holding an old "
    "glass lantern. It was probably one of the best summers of my life."
)


def _answer_world(w):
    """The real-check case: an asked 'anyone famous' question and a session
    whose speaker segment is the Uncle Ahmed story (saved by the run itself)."""
    from core.enums import QuestionSource
    q = Question(circle_id=w.circle.id, target_person_id=w.fatma.id, asker_id=w.elif_.id,
                 text=FAMOUS_Q, source=QuestionSource.family, status=QuestionStatus.asked,
                 created_at=w.q_asked.created_at)
    w.db.add(q)
    seg = w.db.query(Segment).filter(Segment.session_id == w.sess.id,
                                     Segment.start_ms == 20_000).one()
    seg.transcript = UNCLE_AHMED
    w.db.commit()
    return q


def _checker_input(checker) -> str:
    return checker.calls[0]["messages"][0]["content"][0]["text"]


@pytest.mark.anyio
async def test_answer_check_rejects_unrelated_story(w):
    q = _answer_world(w)
    checker = ScriptedLLM(["no"])
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("save_story", _story_args(w, 20_000, 30_000))],
        lambda msgs: [_tool_use("record_answer", {
            "question_id": q.id, "story_id": last_tool_json(msgs)["story_id"],
            "start_ms": 20_000, "end_ms": 30_000,
        })],
        "done",
    ])
    agent, bridge = _make_agent(w, llm, checker)
    result = await agent.run(w.sess.id)

    assert result.answers_recorded == []
    assert result.trace[-1].tool == "record_answer" and result.trace[-1].is_error
    assert "do not answer the question" in result.trace[-1].result_preview
    assert "record_answer" not in [n for n, _ in bridge.tool_calls]
    w.db.expire_all()
    # Not answered, so it goes back to "waiting" to be asked again later.
    assert w.db.get(Question, q.id).status == QuestionStatus.waiting
    assert w.db.get(Question, q.id).answer is None
    # The checker saw exactly this question and the speaker's words in that range.
    seen = _checker_input(checker)
    assert FAMOUS_Q in seen and "Uncle Ahmed was standing on the porch" in seen
    assert checker.calls[0]["tools"] is None


@pytest.mark.anyio
async def test_answer_must_be_in_a_story_saved_in_this_run(w):
    older = save_story_data(w.db, w.fatma.id, w.circle.id, **_story_args(w))
    w.db.commit()
    checker = ScriptedLLM(["yes"])
    llm = DynamicScriptedLLM([[_tool_use("record_answer", {
        "question_id": w.q_asked.id, "story_id": older, "start_ms": 0, "end_ms": 10_000,
    })], "done"])
    agent, bridge = _make_agent(w, llm, checker)
    result = await agent.run(w.sess.id)
    assert result.answers_recorded == [] and checker.calls == []
    assert "story you saved from this session" in result.trace[0].result_preview
    assert "record_answer" not in [n for n, _ in bridge.tool_calls]


@pytest.mark.anyio
async def test_answer_check_accepts_real_answer(w):
    # "Where did you grow up?" vs "I grew up next to the river." (segment 0-10000).
    checker = ScriptedLLM(["Yes."])
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("save_story", _story_args(w))],
        lambda msgs: [_tool_use("record_answer", {
            "question_id": w.q_asked.id, "story_id": last_tool_json(msgs)["story_id"],
            "start_ms": 0, "end_ms": 10_000,
        })],
        "done",
    ])
    agent, _ = _make_agent(w, llm, checker)
    result = await agent.run(w.sess.id)

    assert result.answers_recorded == [w.q_asked.id]
    w.db.expire_all()
    assert w.db.get(Question, w.q_asked.id).status == QuestionStatus.answered
    seen = _checker_input(checker)
    assert "Where did you grow up?" in seen and "I grew up next to the river." in seen
    # The companion's own words in a range are never part of the passage.
    assert "What did you do by the river?" not in seen


@pytest.mark.anyio
@pytest.mark.parametrize("verdict", ["", "unsure", "Not really.", "maybe yes"])
async def test_answer_check_anything_but_yes_rejects(w, verdict):
    llm = DynamicScriptedLLM([
        [_tool_use("save_story", _story_args(w))],
        lambda msgs: [_tool_use("record_answer", {
            "question_id": w.q_asked.id, "story_id": last_tool_json(msgs)["story_id"],
            "start_ms": 0, "end_ms": 10_000,
        })],
        "done",
    ])
    agent, _ = _make_agent(w, llm, ScriptedLLM([verdict]))
    result = await agent.run(w.sess.id)
    assert result.answers_recorded == []


@pytest.mark.anyio
async def test_answer_check_rejects_range_without_speech(w):
    # 12000-20000 is only the private segment, which the archivist never sees.
    checker = ScriptedLLM(["yes"])
    llm = DynamicScriptedLLM([
        [_tool_use("save_story", _story_args(w))],
        lambda msgs: [_tool_use("record_answer", {
            "question_id": w.q_asked.id, "story_id": last_tool_json(msgs)["story_id"],
            "start_ms": 12_000, "end_ms": 20_000,
        })],
        "done",
    ])
    agent, _ = _make_agent(w, llm, checker)
    result = await agent.run(w.sess.id)
    assert result.answers_recorded == []
    assert "nobody speaks in that range" in result.trace[-1].result_preview
    assert checker.calls == []


# ---------------------------------------------------------------------------
# Declined questions and reopening at the end of the run
# ---------------------------------------------------------------------------
# Segment 20000-30000 is the speaker's; here it holds a refusal.

DECLINE_TEXT = "I'd rather not talk about where I grew up. Let us talk about something else."


def _set_speaker_text(w, text):
    seg = w.db.query(Segment).filter(Segment.session_id == w.sess.id,
                                     Segment.start_ms == 20_000).one()
    seg.transcript = text
    w.db.commit()


def _decline_call(w, question_id=None):
    return [_tool_use("mark_question_declined", {
        "question_id": question_id or w.q_asked.id, "session_id": w.sess.id,
        "start_ms": 20_000, "end_ms": 30_000,
    })]


def _status(w, question_id):
    w.db.expire_all()
    return w.db.get(Question, question_id).status


@pytest.mark.anyio
async def test_confirmed_decline_sets_declined_and_is_not_reopened(w):
    _set_speaker_text(w, DECLINE_TEXT)
    checker = ScriptedLLM(["yes"])
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        _decline_call(w),
        "done",
    ])
    agent, bridge = _make_agent(w, llm, checker)
    result = await agent.run(w.sess.id)

    assert result.questions_declined == [w.q_asked.id]
    assert result.questions_reopened == []
    assert _status(w, w.q_asked.id) == QuestionStatus.declined
    assert "reopen_question" not in [n for n, _ in bridge.tool_calls]
    seen = _checker_input(checker)
    assert "Where did you grow up?" in seen and DECLINE_TEXT in seen


@pytest.mark.anyio
async def test_unanswered_question_is_reopened(w):
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        "Nothing to record.",
    ])
    agent, bridge = _make_agent(w, llm, ScriptedLLM(["yes"]))
    result = await agent.run(w.sess.id)

    assert result.questions_reopened == [w.q_asked.id]
    assert _status(w, w.q_asked.id) == QuestionStatus.waiting
    assert _status(w, w.q_waiting.id) == QuestionStatus.waiting   # untouched
    assert ("reopen_question", {"question_id": w.q_asked.id}) in bridge.tool_calls


@pytest.mark.anyio
async def test_answered_question_is_not_reopened(w):
    llm = DynamicScriptedLLM(full_script(w))
    agent, _ = _make_agent(w, llm, ScriptedLLM(["yes"]))
    result = await agent.run(w.sess.id)
    assert result.questions_reopened == []
    assert _status(w, w.q_asked.id) == QuestionStatus.answered


@pytest.mark.anyio
@pytest.mark.parametrize("verdict", ["no", "unsure", ""])
async def test_unconfirmed_decline_is_not_recorded_and_question_reopened(w, verdict):
    _set_speaker_text(w, "We fished there every summer.")   # not a refusal
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        _decline_call(w),
        "done",
    ])
    agent, _ = _make_agent(w, llm, ScriptedLLM([verdict]))
    result = await agent.run(w.sess.id)

    decline = [t for t in result.trace if t.tool == "mark_question_declined"][0]
    assert decline.is_error and "Decline not recorded" in decline.result_preview
    assert result.questions_declined == []
    assert result.questions_reopened == [w.q_asked.id]
    assert _status(w, w.q_asked.id) == QuestionStatus.waiting


@pytest.mark.anyio
async def test_decline_with_another_session_id_is_checked_in_this_session(w):
    # The model names another session; the archivist uses its own, so the
    # checker judges this session's words (here: no decline) and nothing
    # reaches the other session.
    llm = DynamicScriptedLLM([[_tool_use("mark_question_declined", {
        "question_id": w.q_asked.id, "session_id": w.other_sess.id, "start_ms": 0, "end_ms": 10_000,
    })], "done"])
    checker = ScriptedLLM(["no"])
    agent, bridge = _make_agent(w, llm, checker)
    result = await agent.run(w.sess.id)
    assert "Decline not recorded" in result.trace[0].result_preview
    assert checker.calls and "I grew up next to the river." in json.dumps(checker.calls[0])
    assert all(a.get("session_id") != w.other_sess.id for _, a in bridge.tool_calls)
    assert _status(w, w.q_asked.id) == QuestionStatus.waiting


@pytest.mark.anyio
async def test_wrong_session_id_from_the_model_still_saves_the_stories(w):
    wrong = "bcdc8322-5389-4303-a6ed-bd5f528446b5"     # a mistyped id, as in eval split_v2
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": wrong})],
        lambda msgs: (
            [_tool_use("save_story", {**_story_args(w), "sources": [
                {"session_id": wrong, "start_ms": 0, "end_ms": 10_000}]})]
            if last_tool_json(msgs) and last_tool_json(msgs).get("session_id") == w.sess.id
            else "the transcript was not found"
        ),
        "done",
    ])
    agent, bridge = _make_agent(w, llm)
    result = await agent.run(w.sess.id)
    assert not any(t.is_error for t in result.trace)
    assert len(result.story_ids) == 1
    story = w.db.get(Story, result.story_ids[0])
    assert story.sources == [{"session_id": w.sess.id, "start_ms": 0, "end_ms": 10_000}]
    assert all(a.get("session_id") != wrong for _, a in bridge.tool_calls)


@pytest.mark.anyio
async def test_declined_question_stays_declined_after_a_later_session(w):
    # Session 1: the speaker declines.
    _set_speaker_text(w, DECLINE_TEXT)
    llm1 = DynamicScriptedLLM([[_tool_use("get_session_transcript", {"session_id": w.sess.id})],
                               _decline_call(w), "done"])
    agent1, _ = _make_agent(w, llm1, ScriptedLLM(["yes"]))
    await agent1.run(w.sess.id)
    assert _status(w, w.q_asked.id) == QuestionStatus.declined

    # Session 2: another question is asked and not answered; nothing about the first.
    from core.enums import QuestionSource, SessionKind, SessionStart
    from core.models import Session as OrmSession
    sess2 = OrmSession(circle_id=w.circle.id, kind=SessionKind.solo,
                       started_by=SessionStart.spontaneous, participant_ids=[w.fatma.id],
                       started_at=w.sess.started_at, ended_at=w.sess.ended_at)
    w.db.add(sess2); w.db.flush()
    w.db.add(Segment(session_id=sess2.id, speaker_id=w.fatma.id, start_ms=0, end_ms=5_000,
                     transcript="My father mended nets on the steps.", words=[], is_private=False))
    w.q_waiting.status = QuestionStatus.asked
    w.db.commit()

    llm2 = DynamicScriptedLLM([[_tool_use("get_session_transcript", {"session_id": sess2.id})],
                               "Nothing to record."])
    agent2, _ = _make_agent(w, llm2, ScriptedLLM(["yes"]))
    result2 = await agent2.run(sess2.id)

    assert result2.questions_reopened == [w.q_waiting.id]
    assert _status(w, w.q_waiting.id) == QuestionStatus.waiting
    assert _status(w, w.q_asked.id) == QuestionStatus.declined     # still declined
    # A declined question is never offered again.
    from core.services.session_tools import get_pending_questions_data
    offered = [q.question_id for q in get_pending_questions_data(w.db, w.fatma.id, w.circle.id, 50)]
    assert w.q_asked.id not in offered and w.q_waiting.id in offered


# ---------------------------------------------------------------------------
# Reading the checker's verdict (Nova answers in Markdown: "**yes**")
# ---------------------------------------------------------------------------

NOVA_YES = "**yes**" + "\n\n" + "The passage directly addresses the question"


@pytest.mark.parametrize("verdict,expected", [
    ("yes", True),
    ("Yes.", True),
    ("**yes**", True),
    (NOVA_YES, True),   # the real Nova reply
    ("**Yes.**", True),
    ("no", False),
    ("**no**", False),
    ("", False),
    ("unsure", False),
    ("maybe yes", False),
    ("Not really.", False),
    ("yesterday she met him", False),
])
def test_checker_said_yes(verdict, expected):
    assert checker_said_yes(verdict) is expected


@pytest.mark.anyio
async def test_markdown_yes_from_checker_records_the_answer(w):
    checker = ScriptedLLM([NOVA_YES])
    llm = DynamicScriptedLLM([
        [_tool_use("save_story", _story_args(w))],
        lambda msgs: [_tool_use("record_answer", {
            "question_id": w.q_asked.id, "story_id": last_tool_json(msgs)["story_id"],
            "start_ms": 0, "end_ms": 10_000,
        })],
        "done",
    ])
    agent, _ = _make_agent(w, llm, checker)
    result = await agent.run(w.sess.id)
    assert result.answers_recorded == [w.q_asked.id]


# ---------------------------------------------------------------------------
# Split guard: one memory saved as two stories is logged, then merged when
# the parts share a subject period
# ---------------------------------------------------------------------------

def _src(start, end, session="s1"):
    return {"session_id": session, "start_ms": start, "end_ms": end}


@pytest.mark.parametrize("a,b,expected", [
    # Adjacent (gap 3 s) and the same place, in any case and spacing.
    ({"sources": [_src(0, 10_000)], "place": "Akcaabat"},
     {"sources": [_src(13_000, 20_000)], "place": " akcaabat "}, True),
    # Overlapping and a shared subject period, no place.
    ({"sources": [_src(0, 10_000)], "subjects": [{"person_id": "p", "period": "childhood"}]},
     {"sources": [_src(8_000, 12_000)], "subjects": [{"person_id": "q", "period": "childhood"}]}, True),
    # Gap of 5 s or more: separate memories.
    ({"sources": [_src(0, 10_000)], "place": "Akcaabat"},
     {"sources": [_src(15_000, 20_000)], "place": "Akcaabat"}, False),
    # Adjacent but nothing shared.
    ({"sources": [_src(0, 10_000)], "place": "Akcaabat", "subjects": [{"period": "childhood"}]},
     {"sources": [_src(10_500, 20_000)], "place": "Trabzon", "subjects": [{"period": "marriage_early_years"}]},
     False),
    # Same numbers, different sessions.
    ({"sources": [_src(0, 10_000, "s1")], "place": "Akcaabat"},
     {"sources": [_src(0, 10_000, "s2")], "place": "Akcaabat"}, False),
])
def test_possible_split(a, b, expected):
    assert possible_split(a, b) is expected
    assert possible_split(b, a) is expected


@pytest.mark.anyio
async def test_split_guard_logs_ids_only_and_merges_the_split(w, caplog):
    def story(title, start, end, place):
        return {**_story_args(w, start, end), "title": title, "place": place,
                "summary": f"Fatma remembers {title.lower()}."}

    llm = DynamicScriptedLLM([
        [_tool_use("save_story", story("The Harbour", 0, 5_000, "Akcaabat")),
         _tool_use("save_story", story("The Fishing Boats", 6_000, 10_000, "Akcaabat")),
         _tool_use("save_story", story("Summer Fishing", 20_000, 30_000, "Rize"))],
        "done",
        '{"title": "Harbour Mornings", "summary": "Fatma remembers the harbour and its boats."}',
    ])
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=w.sess.id)
    agent = ArchivistAgent(story_guard_llm=ScriptedLLM(["no"]), llm=llm, person_id=w.fatma.id,
                           circle_id=w.circle.id, bridge=bridge, checker_llm=ScriptedLLM(["yes"]))
    with caplog.at_level("INFO", logger="server.agents.archivist_agent"):
        result = await agent.run(w.sess.id)

    # Summer Fishing shares the childhood period but starts 10 s after the boats.
    harbour = result.stories_merged[0]["story_id"]
    boats = result.stories_merged[0]["merged_ids"][0]
    assert result.possible_splits[0] == (harbour, boats)
    assert len(result.story_ids) == 2 and harbour in result.story_ids and boats not in result.story_ids
    w.db.expire_all()
    merged = w.db.get(Story, harbour)
    assert w.db.get(Story, boats) is None
    assert merged.title == "Harbour Mornings"
    assert merged.ai_summary == "Fatma remembers the harbour and its boats."
    assert [(x["start_ms"], x["end_ms"]) for x in merged.sources] == [(0, 5_000), (6_000, 10_000)]
    # The merge text came from the teller's words only, in one call.
    merge_call = llm.calls[-1]
    assert merge_call["tools"] is None
    lines = [r.getMessage() for r in caplog.records
             if "split" in r.getMessage().lower() or "Merged" in r.getMessage()]
    assert lines and all("Harbour" not in x and "Akcaabat" not in x for x in lines)


@pytest.mark.anyio
async def test_split_sharing_only_a_place_is_not_merged(w):
    def story(title, start, end, period):
        return {**_story_args(w, start, end), "title": title, "place": "Akcaabat",
                "subjects": [{"person_id": w.fatma.id, "period": period}]}

    llm = DynamicScriptedLLM([
        [_tool_use("save_story", story("The Harbour", 0, 5_000, "childhood")),
         _tool_use("save_story", story("The Wedding", 6_000, 10_000, "marriage_early_years"))],
        "done",
    ])
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=w.sess.id)
    agent = ArchivistAgent(story_guard_llm=ScriptedLLM(["no"]), llm=llm, person_id=w.fatma.id,
                           circle_id=w.circle.id, bridge=bridge)
    result = await agent.run(w.sess.id)
    assert len(result.possible_splits) == 1            # flagged (same place) ...
    assert result.stories_merged == [] and len(result.story_ids) == 2   # ... but different periods


# The real case: her three segments are 5.0-5.4 s apart, each gap holding a
# companion question (timings of evals/run_archivist_split.py, one_memory).
_TELLER = [(0, 11_200), (16_600, 27_000), (32_000, 45_600)]
_COMPANION = [(11_700, 16_100), (27_500, 31_500)]


def test_possible_split_ignores_companion_segments_in_the_gap():
    harbour = {"sources": [_src(*_TELLER[0])], "place": "Akcaabat"}
    boats = {"sources": [_src(*_TELLER[1])], "place": "Akcaabat"}
    father = {"sources": [_src(*_TELLER[2])], "place": "Akcaabat"}
    companion = {"s1": _COMPANION}
    # Without the companion ranges the gaps are 5.4 s and 5.0 s: not "adjacent".
    assert not possible_split(harbour, boats) and not possible_split(boats, father)
    # Not counting the companion's questions, 1 s of silence is left: one memory.
    assert possible_split(harbour, boats, companion) and possible_split(boats, father, companion)
    # Companion ranges of another session do not count.
    assert not possible_split(harbour, boats, {"s2": _COMPANION})
    # A long silence that is not the companion still separates them.
    assert not possible_split({"sources": [_src(0, 10_000)], "place": "Akcaabat"},
                              {"sources": [_src(20_000, 30_000)], "place": "Akcaabat"},
                              {"s1": [(10_000, 12_000)]})


@pytest.mark.anyio
async def test_split_guard_catches_the_real_harbour_case(w):
    from core.enums import SessionKind, SessionStart
    from core.models import Session as OrmSession
    sess = OrmSession(circle_id=w.circle.id, kind=SessionKind.solo, started_by=SessionStart.spontaneous,
                      participant_ids=[w.fatma.id], started_at=w.sess.started_at, ended_at=w.sess.ended_at)
    w.db.add(sess); w.db.flush()
    for (start, end), speaker in zip(_TELLER + _COMPANION, [w.fatma.id] * 3 + [None] * 2):
        w.db.add(Segment(session_id=sess.id, speaker_id=speaker, start_ms=start, end_ms=end,
                         transcript="the harbour" if speaker else "Tell me more?", words=[]))
    w.db.commit()

    def story(title, rng):
        return {"title": title, "summary": f"Fatma remembers {title.lower()}.", "teller_id": w.fatma.id,
                "subjects": [{"person_id": w.fatma.id, "period": "childhood"}], "place": "Akcaabat",
                "sources": [{"session_id": sess.id, "start_ms": rng[0], "end_ms": rng[1]}]}

    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": sess.id})],
        [_tool_use("save_story", story("The Harbour", _TELLER[0])),
         _tool_use("save_story", story("The Fishing Boats", _TELLER[1])),
         _tool_use("save_story", story("Father and the Fishermen", _TELLER[2]))],
        "done",
    ])
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=sess.id)
    agent = ArchivistAgent(story_guard_llm=ScriptedLLM(["no"]), llm=llm, person_id=w.fatma.id,
                           circle_id=w.circle.id, bridge=bridge)
    result = await agent.run(sess.id)
    assert len(result.possible_splits) == 2
    (harbour, boats), (_, father) = result.possible_splits
    assert result.possible_splits[1][0] == boats
    # All three parts become one story; the merge text falls back to the first title.
    assert result.story_ids == [harbour]
    assert result.stories_merged == [{"story_id": harbour, "merged_ids": [boats, father]}]
    w.db.expire_all()
    story = w.db.get(Story, harbour)
    assert story.title == "The Harbour"
    assert [(x["start_ms"], x["end_ms"]) for x in story.sources] == _TELLER
