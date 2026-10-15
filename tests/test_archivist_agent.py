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
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from typing import Any

import pytest

from core.enums import QuestionStatus, StoryStatus
from core.models import Question, Story
from core.services.session_tools import get_pending_questions_data
from core.services.archive_tools import (
    add_question_data,
    get_session_transcript_data,
    record_answer_data,
    save_story_data,
)
from server.agents.archivist_agent import (
    _MAX_QUESTIONS,
    _MAX_TOOL_ROUNDS,
    DEFAULT_ARCHIVIST_MODEL,
    ArchivistAgent,
    archivist_model_id,
    normalize_question,
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

    def __init__(self, db, person_id: str, circle_id: str) -> None:
        self._db = db
        self._person_id = person_id
        self._circle_id = circle_id
        self.tool_calls: list[tuple[str, dict]] = []

    async def bedrock_tool_config(self) -> dict:
        return {"tools": [_spec(n) for n in (
            "get_session_transcript", "save_story", "record_answer",
            "add_question", "mark_question_asked",
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
        raise RuntimeError(f"Unknown tool: {name}")


def _make_agent(w, llm) -> tuple[ArchivistAgent, FakeArchiveBridge]:
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id)
    agent = ArchivistAgent(llm=llm, person_id=w.fatma.id,
                           circle_id=w.circle.id, bridge=bridge)
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
    agent, bridge = _make_agent(w, llm)
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
    assert names == {"get_session_transcript", "save_story", "record_answer", "add_question"}


@pytest.mark.anyio
async def test_chat_tool_call_is_rejected(w):
    llm = DynamicScriptedLLM([
        [_tool_use("mark_question_asked", {"question_id": w.q_waiting.id})],
        "done",
    ])
    agent, bridge = _make_agent(w, llm)
    result = await agent.run(w.sess.id)
    assert result.trace[0].is_error
    assert bridge.tool_calls == []
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
    # The guard looked up the transcript and waiting questions itself.
    assert [n for n, _ in bridge.tool_calls] == ["get_session_transcript", "get_pending_questions"]


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
