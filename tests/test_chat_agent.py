"""
Tests for server.agents.chat_agent.ChatAgent.

No network, no real Bedrock.  Uses:
  - ScriptedLLM : returns pre-canned Bedrock Converse response dicts in order.
  - FakeMCPBridge : calls the real service functions against an in-memory DB.

Coverage
--------
- Tool loop: model may request tools before returning text.
- mark_question_asked is called after a family question is asked by the agent.
- TurnResult has reply_text, trace, and latency fields.
- Segments are stored for both the user turn and the agent reply.
- <thinking> blocks are stripped from reply_text.
- max-rounds guard: loop exits after _MAX_TOOL_ROUNDS even without text reply.
- Tool allowlist: archivist tools are not offered, and a call to one is
  rejected without reaching the bridge.
- chat_llm / archivist_llm read model and temperature from the environment;
  BedrockLLM sends temperature only when set.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from core.clock import now_utc
from core.db import SessionLocal
from core.enums import (
    AccessType, CircleStatus, Emoji, InvitationStatus,
    LifePeriod, QuestionSource, QuestionStatus,
    Role, SessionKind, SessionStart, StoryKind, StoryStatus,
)
from core.models import (
    Base, Circle, Invitation, Membership, Person, Question,
    Reaction, Segment, Story,
    Session as OrmSession,
)
from core.services.session_tools import (
    get_pending_questions_data,
    get_session_context_data,
    mark_question_asked_data,
)
from server.agents.archivist_agent import archivist_llm
from server.agents.chat_agent import CHAT_TOOLS, ChatAgent, _MAX_TOOL_ROUNDS, chat_llm
from server.llm import BedrockLLM, RecordingLLM, strip_thinking


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _enable_fk(conn, _rec):
    c = conn.cursor(); c.execute("PRAGMA foreign_keys=ON"); c.close()


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
def world(db):
    """Minimal world: circle + 2 people + 1 waiting family question."""
    now = now_utc()
    fatma    = Person(name="Fatma", birth_year=1948, language="en")
    elif_    = Person(name="Elif",  birth_year=2003, language="en")
    db.add_all([fatma, elif_])
    db.flush()

    circle = Circle(
        name="Test Family", center_person_id=fatma.id,
        status=CircleStatus.active, chat_time="10:00", timezone="Europe/Istanbul",
    )
    db.add(circle)
    db.flush()

    db.add_all([
        Membership(person_id=fatma.id, circle_id=circle.id,
                   role=Role.center, relation_to_center=None),
        Membership(person_id=elif_.id, circle_id=circle.id,
                   role=Role.member, relation_to_center="granddaughter"),
    ])
    db.flush()

    q = Question(
        circle_id=circle.id, target_person_id=fatma.id,
        asker_id=elif_.id,
        text="What was school like for you?",
        source=QuestionSource.family,
        period=LifePeriod.childhood,
        status=QuestionStatus.waiting, answer=None,
        created_at=(now - timedelta(hours=1)).isoformat(),
    )
    db.add(q)
    db.commit()

    class W:
        pass
    w = W()
    w.db = db; w.fatma = fatma; w.elif_ = elif_
    w.circle = circle; w.q = q
    return w


# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------

class ScriptedLLM:
    """Returns pre-canned response dicts in sequence.

    Each entry in `script` is either:
    - a list of tool-use blocks  → stopReason = "tool_use"
    - a str                      → stopReason = "end_turn" with that text
    """

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self._idx = 0
        self.calls: list[dict] = []

    def converse(self, system, messages, tools=None) -> dict:
        self.calls.append({"system": system, "messages": messages, "tools": tools})
        entry = self._script[min(self._idx, len(self._script) - 1)]
        self._idx += 1

        if isinstance(entry, str):
            return {
                "stopReason": "end_turn",
                "output": {"message": {"role": "assistant",
                                       "content": [{"text": entry}]}},
                "usage": {},
            }
        # list of tool-use dicts
        return {
            "stopReason": "tool_use",
            "output": {"message": {"role": "assistant", "content": entry}},
            "usage": {},
        }


def _tool_use(name: str, args: dict, uid: str | None = None) -> dict:
    return {
        "toolUse": {
            "toolUseId": uid or str(uuid.uuid4()),
            "name": name,
            "input": args,
        }
    }


# ---------------------------------------------------------------------------
# Fake MCP bridge
# ---------------------------------------------------------------------------

class FakeMCPBridge:
    """Calls real service functions on the in-memory DB. No network."""

    def __init__(self, db, person_id: str, circle_id: str) -> None:
        self._db = db
        self._person_id = person_id
        self._circle_id = circle_id
        self.tool_calls: list[tuple[str, dict]] = []

    async def bedrock_tool_config(self) -> dict:
        return {
            "tools": [
                {"toolSpec": {"name": "get_session_context",
                              "description": "Get session context.",
                              "inputSchema": {"json": {"type": "object"}}}},
                {"toolSpec": {"name": "get_pending_questions",
                              "description": "Get pending questions.",
                              "inputSchema": {"json": {
                                  "type": "object",
                                  "properties": {"limit": {"type": "integer"}},
                              }}}},
                {"toolSpec": {"name": "mark_question_asked",
                              "description": "Mark a question as asked.",
                              "inputSchema": {"json": {
                                  "type": "object",
                                  "properties": {"question_id": {"type": "string"}},
                                  "required": ["question_id"],
                              }}}},
            ]
        }

    async def call_tool(self, name: str, arguments: dict) -> Any:
        self.tool_calls.append((name, arguments))
        if name == "get_session_context":
            from dataclasses import asdict
            return asdict(get_session_context_data(
                self._db, self._person_id, self._circle_id
            ))
        elif name == "get_pending_questions":
            from dataclasses import asdict
            items = get_pending_questions_data(
                self._db, self._person_id, self._circle_id,
                limit=arguments.get("limit", 5),
            )
            return [asdict(i) for i in items]
        elif name == "mark_question_asked":
            mark_question_asked_data(
                self._db, self._person_id, self._circle_id,
                arguments["question_id"],
            )
            self._db.commit()
            return {"status": "ok", "question_id": arguments["question_id"]}
        else:
            raise RuntimeError(f"Unknown tool: {name}")


def _make_agent(world, llm) -> ChatAgent:
    bridge = FakeMCPBridge(world.db, world.fatma.id, world.circle.id)
    return ChatAgent(
        llm=llm,
        person_id=world.fatma.id,
        circle_id=world.circle.id,
        db_session=world.db,
        bridge=bridge,
    )


# ---------------------------------------------------------------------------
# strip_thinking unit test (sync, no fixture needed)
# ---------------------------------------------------------------------------

def test_strip_thinking_removes_block():
    raw = "<thinking>I need to call a tool first.</thinking>Hello there!"
    assert strip_thinking(raw) == "Hello there!"


def test_strip_thinking_multiline():
    raw = "<thinking>\nsome\nmultiline\nthought\n</thinking>  Final answer."
    assert strip_thinking(raw) == "Final answer."


def test_strip_thinking_no_block():
    raw = "Just a plain reply."
    assert strip_thinking(raw) == "Just a plain reply."


# ---------------------------------------------------------------------------
# Tool loop
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_single_tool_round_then_text(world):
    """Model calls get_session_context once, then returns text."""
    uid = str(uuid.uuid4())
    llm = ScriptedLLM([
        [_tool_use("get_session_context", {}, uid)],
        "Hello, nice to see you!",
    ])
    agent = _make_agent(world, llm)
    result = await agent.turn("(session start)")

    assert result.reply_text == "Hello, nice to see you!"
    assert len(result.trace) == 1
    assert result.trace[0].tool == "get_session_context"
    assert result.trace[0].is_error is False


@pytest.mark.anyio
async def test_multiple_tool_rounds(world):
    """Model calls three different tools across two rounds, then replies."""
    uid1, uid2, uid3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    llm = ScriptedLLM([
        [_tool_use("get_session_context", {}, uid1),
         _tool_use("get_pending_questions", {"limit": 5}, uid2)],
        [_tool_use("mark_question_asked",
                   {"question_id": world.q.id}, uid3)],
        "What was school like for you?",
    ])
    agent = _make_agent(world, llm)
    result = await agent.turn("(session start)")

    assert result.reply_text == "What was school like for you?"
    tool_names = [t.tool for t in result.trace]
    assert "get_session_context" in tool_names
    assert "get_pending_questions" in tool_names
    assert "mark_question_asked" in tool_names


@pytest.mark.anyio
async def test_mark_question_asked_flips_status(world):
    """After the agent calls mark_question_asked, the DB row is updated."""
    uid = str(uuid.uuid4())
    llm = ScriptedLLM([
        [_tool_use("mark_question_asked", {"question_id": world.q.id}, uid)],
        "Here is your question.",
    ])
    agent = _make_agent(world, llm)
    await agent.turn("go")

    q = world.db.get(Question, world.q.id)
    assert q.status == QuestionStatus.asked


@pytest.mark.anyio
async def test_thinking_stripped_from_reply(world):
    """<thinking> tags in model output are stripped before returning."""
    llm = ScriptedLLM([
        "<thinking>Internal reasoning here.</thinking>Good morning, Fatma!"
    ])
    agent = _make_agent(world, llm)
    result = await agent.turn("hello")
    assert "<thinking>" not in result.reply_text
    assert result.reply_text == "Good morning, Fatma!"


@pytest.mark.anyio
async def test_latency_fields_present(world):
    llm = ScriptedLLM(["A short reply."])
    agent = _make_agent(world, llm)
    result = await agent.turn("hello")

    assert "llm_ms" in result.latency
    assert "tools_ms" in result.latency
    assert "total_ms" in result.latency
    assert result.latency["total_ms"] >= 0


@pytest.mark.anyio
async def test_segments_stored(world):
    """One segment for user input and one for agent reply are persisted."""
    llm = ScriptedLLM(["I remember the garden well."])
    agent = _make_agent(world, llm)
    await agent.turn("Tell me about the garden.")

    segs = world.db.query(Segment).all()
    transcripts = [s.transcript for s in segs]
    assert "Tell me about the garden." in transcripts
    assert "I remember the garden well." in transcripts


@pytest.mark.anyio
async def test_max_rounds_guard(world):
    """If the model keeps requesting tools beyond MAX_TOOL_ROUNDS, the loop exits."""
    # Script: always return a tool_use, never text.
    uid_factory = lambda: str(uuid.uuid4())
    script = [
        [_tool_use("get_session_context", {}, uid_factory())]
        for _ in range(_MAX_TOOL_ROUNDS + 2)
    ]
    llm = ScriptedLLM(script)
    agent = _make_agent(world, llm)
    result = await agent.turn("(test)")
    # Should not raise; reply_text is the fallback message.
    assert isinstance(result.reply_text, str)


@pytest.mark.anyio
async def test_tool_error_recorded_in_trace(world):
    """A tool that raises an exception is recorded as is_error=True in trace."""
    class ErrorBridge(FakeMCPBridge):
        async def call_tool(self, name, arguments):
            raise RuntimeError("simulated tool failure")

    uid = str(uuid.uuid4())
    llm = ScriptedLLM([
        [_tool_use("get_session_context", {}, uid)],
        "Recovered.",
    ])
    bridge = ErrorBridge(world.db, world.fatma.id, world.circle.id)
    agent = ChatAgent(
        llm=llm, person_id=world.fatma.id, circle_id=world.circle.id,
        db_session=world.db, bridge=bridge,
    )
    result = await agent.turn("hello")
    assert any(t.is_error for t in result.trace)


# ---------------------------------------------------------------------------
# RecordingLLM wraps ScriptedLLM correctly
# ---------------------------------------------------------------------------

def test_recording_llm_captures_requests():
    inner = ScriptedLLM(["reply"])
    recorder = RecordingLLM(inner)
    recorder.converse([{"text": "sys"}], [{"role": "user", "content": [{"text": "hi"}]}])
    assert len(recorder.requests) == 1
    assert recorder.requests[0]["messages"][0]["role"] == "user"


# ---------------------------------------------------------------------------
# Tool allowlist
# ---------------------------------------------------------------------------

class BridgeWithArchivistTools(FakeMCPBridge):
    """A bridge whose server also offers archivist tools, like the real one."""

    async def bedrock_tool_config(self) -> dict:
        config = await super().bedrock_tool_config()
        for name in ("save_story", "record_answer", "add_question", "get_session_transcript"):
            config["tools"].append({"toolSpec": {
                "name": name, "description": name,
                "inputSchema": {"json": {"type": "object"}},
            }})
        return config


@pytest.mark.anyio
async def test_archivist_tools_not_offered_to_chat_model(world):
    llm = ScriptedLLM(["Hello."])
    bridge = BridgeWithArchivistTools(world.db, world.fatma.id, world.circle.id)
    agent = ChatAgent(llm=llm, person_id=world.fatma.id, circle_id=world.circle.id,
                      db_session=world.db, bridge=bridge)
    await agent.turn("hello")

    offered = {t["toolSpec"]["name"] for t in llm.calls[0]["tools"]["tools"]}
    assert offered == {"get_session_context", "get_pending_questions", "mark_question_asked"}
    assert offered <= CHAT_TOOLS


@pytest.mark.anyio
async def test_tool_outside_allowlist_rejected_without_bridge_call(world):
    llm = ScriptedLLM([
        [_tool_use("save_story", {"title": "x", "teller_id": "invented-id"})],
        "Let us talk about something else.",
    ])
    bridge = BridgeWithArchivistTools(world.db, world.fatma.id, world.circle.id)
    agent = ChatAgent(llm=llm, person_id=world.fatma.id, circle_id=world.circle.id,
                      db_session=world.db, bridge=bridge)
    result = await agent.turn("hello")

    assert bridge.tool_calls == []
    assert result.trace[0].tool == "save_story"
    assert result.trace[0].is_error
    assert "not available to the chat agent" in result.trace[0].result_preview
    assert world.db.query(Story).count() == 0
    # The model got the error back as a tool result and could continue.
    assert result.reply_text == "Let us talk about something else."


# ---------------------------------------------------------------------------
# LLM factories and temperature
# ---------------------------------------------------------------------------

class _FakeBedrockClient:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def converse(self, **kwargs) -> dict:
        self.kwargs = kwargs
        return {"stopReason": "end_turn",
                "output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}}


def _with_fake_client(llm: BedrockLLM) -> _FakeBedrockClient:
    fake = _FakeBedrockClient()
    llm._client = fake
    return fake


def test_temperature_sent_only_when_set():
    llm = BedrockLLM(model_id="m")
    fake = _with_fake_client(llm)
    llm.converse([{"text": "s"}], [])
    assert "temperature" not in fake.kwargs["inferenceConfig"]

    llm = BedrockLLM(model_id="m", temperature=0.0)
    fake = _with_fake_client(llm)
    llm.converse([{"text": "s"}], [])
    assert fake.kwargs["inferenceConfig"]["temperature"] == 0.0


def test_chat_llm_defaults_and_env(monkeypatch):
    monkeypatch.delenv("EVOCA_CHAT_MODEL", raising=False)
    monkeypatch.delenv("EVOCA_CHAT_TEMPERATURE", raising=False)
    llm = chat_llm()
    assert llm.model_id == "us.amazon.nova-2-lite-v1:0"
    assert llm.temperature == 0.3

    monkeypatch.setenv("EVOCA_CHAT_TEMPERATURE", "0.7")
    assert chat_llm().temperature == 0.7


def test_archivist_llm_defaults_and_env(monkeypatch):
    monkeypatch.delenv("EVOCA_ARCHIVIST_MODEL", raising=False)
    monkeypatch.delenv("EVOCA_ARCHIVIST_TEMPERATURE", raising=False)
    llm = archivist_llm()
    assert llm.model_id == "us.amazon.nova-2-lite-v1:0"
    assert llm.temperature == 0.2
    assert llm.max_tokens == 4096

    monkeypatch.setenv("EVOCA_ARCHIVIST_TEMPERATURE", "0")
    assert archivist_llm().temperature == 0.0


def test_bedrock_client_uses_adaptive_retry():
    retries = BedrockLLM(model_id="m")._client.meta.config.retries
    assert retries["mode"] == "adaptive"
    # botocore's max_attempts=10 counts retries: 1 call + 10 retries.
    assert retries["total_max_attempts"] == 11
