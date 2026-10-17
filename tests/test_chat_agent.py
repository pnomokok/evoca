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
- Reply guards: quotes removed, only the last question kept; applied to the
  returned reply, the stored Segment and the history.
- end_conversation: local tool, never reaches the bridge, no second LLM call,
  session_should_end set, goodbye cleaned of questions (fallback text if empty).
- Stop fallback: a clear request to stop plus a reply without a question ends
  the session even without end_conversation; "I'm tired of ..." does not.
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
from core.services.chat_tools import (
    get_linked_playlist_data,
    mark_private_data,
    mark_reactions_delivered_data,
    search_archive_data,
    set_story_access_data,
)
from core.services.session_tools import (
    get_pending_questions_data,
    get_session_context_data,
    mark_question_asked_data,
)
from server.agents.archivist_agent import archivist_llm
from server.agents.chat_agent import (
    CHAT_TOOLS,
    GOODBYE_FALLBACK,
    LOCAL_TOOLS,
    ChatAgent,
    _MAX_TOOL_ROUNDS,
    asks_to_stop,
    chat_llm,
    clean_reply,
    first_names_only,
    keep_last_question,
    remove_questions,
    split_sentences,
    strip_quotes,
)
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

    def __init__(self, db, person_id: str, circle_id: str, session_id: str | None = None) -> None:
        self._db = db
        self._person_id = person_id
        self._circle_id = circle_id
        # Like the X-Evoca-Session-Id header. Tests whose agent creates its own
        # session set session_id_provider (e.g. lambda: agent._orm_session_id).
        self.session_id = session_id
        self.session_id_provider = None
        self.fail_tools: set[str] = set()   # tools that raise, to test failure paths
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
        elif name in self.fail_tools:
            raise RuntimeError(f"MCP tool '{name}' returned error: simulated failure")
        elif name == "mark_question_asked":
            mark_question_asked_data(
                self._db, self._person_id, self._circle_id,
                arguments["question_id"],
            )
            self._db.commit()
            return {"status": "ok", "question_id": arguments["question_id"]}
        elif name == "mark_private":
            session_id = self.session_id or (self.session_id_provider and self.session_id_provider())
            ids = mark_private_data(self._db, self._person_id, self._circle_id,
                                    session_id, arguments["start_ms"], arguments["end_ms"])
            self._db.commit()
            return {"status": "ok", "segments_marked": len(ids)}
        elif name == "mark_reactions_delivered":
            n = mark_reactions_delivered_data(self._db, self._person_id, self._circle_id,
                                              arguments["story_ids"])
            self._db.commit()
            return {"status": "ok", "reactions_marked": n}
        elif name == "set_story_access":
            set_story_access_data(self._db, self._person_id, self._circle_id,
                                  arguments["story_id"], arguments["type"])
            self._db.commit()
            return {"status": "ok"}
        elif name == "search_archive":
            return {"result": search_archive_data(self._db, self._person_id, self._circle_id,
                                                  arguments.get("query", ""))}
        elif name == "get_linked_playlist":
            try:
                return get_linked_playlist_data(self._db, self._person_id, self._circle_id,
                                                arguments["story_id"])
            except ValueError as exc:
                raise RuntimeError(f"MCP tool '{name}' returned error: {exc}") from exc
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
    assert offered == {"get_session_context", "get_pending_questions",
                       "mark_question_asked", "end_conversation", "keep_private"}
    assert offered <= CHAT_TOOLS | LOCAL_TOOLS


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


# ---------------------------------------------------------------------------
# Reply guards
# ---------------------------------------------------------------------------

def test_strip_quotes():
    assert strip_quotes('She said “hello” and "bye".') == "She said hello and bye."


def test_split_sentences_keeps_titles():
    assert split_sentences("Did Mr. Kemal teach you? He was kind.") == [
        "Did Mr. Kemal teach you?", "He was kind.",
    ]


def test_keep_last_question_drops_earlier_questions():
    text = "What a lovely garden. Who planted it? It sounds peaceful. Did you have roses?"
    assert keep_last_question(text) == "What a lovely garden. It sounds peaceful. Did you have roses?"


def test_keep_last_question_leaves_single_question_untouched():
    text = "That is touching.  Who was there?"
    assert keep_last_question(text) == text


def test_remove_questions():
    assert remove_questions("Thank you. Shall we talk tomorrow? Goodbye.") == "Thank you. Goodbye."


def test_clean_reply_goodbye_fallback():
    assert clean_reply("Shall we talk again tomorrow?", ending=True) == GOODBYE_FALLBACK
    assert clean_reply("", ending=True) == GOODBYE_FALLBACK


@pytest.mark.anyio
async def test_guards_applied_to_reply_segment_and_history(world):
    llm = ScriptedLLM(['What a “big” tree! Who planted it? Did you climb it?'])
    agent = _make_agent(world, llm)
    result = await agent.turn("We had a mulberry tree.")

    expected = "What a big tree! Did you climb it?"
    assert result.reply_text == expected
    assert result.session_should_end is False
    assert expected in [s.transcript for s in world.db.query(Segment).all()]
    assert agent._history[-1]["content"][0]["text"] == expected


def test_first_names_only():
    names = {"Elif Yilmaz", "Fatma Yilmaz", "Can"}
    assert first_names_only("Hello, Fatma Yilmaz! Your granddaughter Elif Yilmaz has a question.",
                            names) == "Hello, Fatma! Your granddaughter Elif has a question."
    assert first_names_only("Elif Yilmazlar came.", names) == "Elif Yilmazlar came."


@pytest.mark.anyio
async def test_reply_uses_first_names_from_the_tools(world):
    world.elif_.name = "Elif Yilmaz"
    world.fatma.name = "Fatma Yilmaz"
    world.db.commit()
    llm = ScriptedLLM([
        [_tool_use("get_session_context", {}), _tool_use("get_pending_questions", {})],
        "Hello, Fatma Yilmaz! Your granddaughter Elif Yilmaz has a question for you: "
        "what was school like?",
    ])
    result = await _make_agent(world, llm).turn("Hello")
    assert result.reply_text == ("Hello, Fatma! Your granddaughter Elif has a question for you: "
                                 "what was school like?")


# ---------------------------------------------------------------------------
# end_conversation (local tool)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_end_conversation_ends_session_without_second_llm_call(world):
    llm = ScriptedLLM([
        [{"text": "Thank you, it was lovely to hear about the garden. Shall we talk tomorrow?"},
         _tool_use("end_conversation", {})],
        "This should never be requested.",
    ])
    bridge = FakeMCPBridge(world.db, world.fatma.id, world.circle.id)
    agent = ChatAgent(llm=llm, person_id=world.fatma.id, circle_id=world.circle.id,
                      db_session=world.db, bridge=bridge)
    result = await agent.turn("I am tired, let us stop.")

    assert result.session_should_end is True
    assert result.reply_text == "Thank you, it was lovely to hear about the garden."
    assert len(llm.calls) == 1
    assert bridge.tool_calls == []
    assert [(t.tool, t.is_error) for t in result.trace] == [("end_conversation", False)]
    assert result.reply_text in [s.transcript for s in world.db.query(Segment).all()]


@pytest.mark.anyio
async def test_end_conversation_with_only_a_question_uses_fallback(world):
    llm = ScriptedLLM([[{"text": "Shall we talk again tomorrow?"}, _tool_use("end_conversation", {})]])
    agent = _make_agent(world, llm)
    result = await agent.turn("Goodbye.")
    assert result.session_should_end is True
    assert result.reply_text == GOODBYE_FALLBACK


@pytest.mark.anyio
async def test_end_conversation_without_text_uses_fallback(world):
    llm = ScriptedLLM([[_tool_use("end_conversation", {})]])
    agent = _make_agent(world, llm)
    result = await agent.turn("Goodbye.")
    assert result.reply_text == GOODBYE_FALLBACK


@pytest.mark.anyio
async def test_end_conversation_runs_other_tools_in_same_message(world):
    llm = ScriptedLLM([[
        {"text": "Goodbye for now."},
        _tool_use("mark_question_asked", {"question_id": world.q.id}),
        _tool_use("end_conversation", {}),
    ]])
    bridge = FakeMCPBridge(world.db, world.fatma.id, world.circle.id)
    agent = ChatAgent(llm=llm, person_id=world.fatma.id, circle_id=world.circle.id,
                      db_session=world.db, bridge=bridge)
    result = await agent.turn("Bye.")
    assert result.session_should_end is True
    assert [n for n, _ in bridge.tool_calls] == ["mark_question_asked"]


@pytest.mark.anyio
async def test_history_alternates_roles_after_end_conversation(world):
    llm = ScriptedLLM([
        [{"text": "Goodbye for now."}, _tool_use("end_conversation", {})],
        "Oh, hello again.",
    ])
    agent = _make_agent(world, llm)
    await agent.turn("Bye.")
    await agent.turn("Wait, one more thing.")

    roles = [m["role"] for m in llm.calls[-1]["messages"]]
    assert all(a != b for a, b in zip(roles, roles[1:]))


# ---------------------------------------------------------------------------
# Stop fallback (model says goodbye without calling end_conversation)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "I'm tired now, let's stop for today.",
    "I am very tired.",
    "Goodbye, dear.",
    "Thank you. Goodbye!",
    "That’s enough for today.",
    "We can continue tomorrow.",
    "Let us talk tomorrow.",
])
def test_asks_to_stop_detects_clear_requests(text):
    assert asks_to_stop(text)


@pytest.mark.parametrize("text", [
    "I'm tired of the rain.",
    "I am tired of waiting for the bus.",
    "He said goodbye to the village in 1960.",
    "That's enough money for a bicycle, he said.",
    "Please do not stop.",
    "(Session started.)",
])
def test_asks_to_stop_ignores_stories_and_other_uses(text):
    assert not asks_to_stop(text)


@pytest.mark.anyio
async def test_stop_request_and_goodbye_without_tool_ends_session(world):
    llm = ScriptedLLM(["Thank you for these lovely stories. Rest well."])
    agent = _make_agent(world, llm)
    result = await agent.turn("I'm tired now, let's stop for today.")
    assert result.session_should_end is True
    assert result.reply_text == "Thank you for these lovely stories. Rest well."
    assert result.trace == []


@pytest.mark.anyio
async def test_tired_of_something_with_question_does_not_end(world):
    llm = ScriptedLLM(["Rainy days can feel long. What did you do on rainy days as a child?"])
    agent = _make_agent(world, llm)
    result = await agent.turn("I'm tired of the rain.")
    assert result.session_should_end is False
    assert result.reply_text.endswith("?")


@pytest.mark.anyio
async def test_stop_request_but_agent_asks_question_does_not_end(world):
    llm = ScriptedLLM(["Of course. Shall we talk again tomorrow?"])
    agent = _make_agent(world, llm)
    result = await agent.turn("I'm tired now, let's stop for today.")
    assert result.session_should_end is False


@pytest.mark.anyio
async def test_no_stop_request_and_no_question_does_not_end(world):
    llm = ScriptedLLM(["That sounds like a wonderful summer."])
    agent = _make_agent(world, llm)
    result = await agent.turn("We swam in the river every day.")
    assert result.session_should_end is False


def test_answer_check_llm_is_archivist_model_at_temperature_zero(monkeypatch):
    from server.agents.archivist_agent import answer_check_llm
    monkeypatch.setenv("EVOCA_ARCHIVIST_MODEL", "us.amazon.nova-2-lite-v1:0")
    llm = answer_check_llm()
    assert llm.model_id == "us.amazon.nova-2-lite-v1:0"
    assert llm.temperature == 0.0


# ---------------------------------------------------------------------------
# Privacy: keep_private scopes, history scrub, pending marks, auto-mark
# ---------------------------------------------------------------------------

import logging


class SnapshotLLM(ScriptedLLM):
    """ScriptedLLM that also keeps a JSON snapshot of every request as it was
    sent (the live history is scrubbed later, so references are not enough)."""

    def __init__(self, script):
        super().__init__(script)
        self.sent: list[str] = []

    def converse(self, system, messages, tools=None):
        self.sent.append(json.dumps({"system": system, "messages": messages}))
        return super().converse(system, messages, tools)


def _private_agent(world, llm, checker=None):
    """checker: the privacy gate's LLM; by default it always confirms ("yes")."""
    bridge = FakeMCPBridge(world.db, world.fatma.id, world.circle.id)
    agent = ChatAgent(llm=llm, person_id=world.fatma.id, circle_id=world.circle.id,
                      db_session=world.db, bridge=bridge,
                      checker_llm=checker or ScriptedLLM(["yes"]))
    bridge.session_id_provider = lambda: agent._orm_session_id
    return agent, bridge


def _segments(world, agent):
    world.db.expire_all()
    return (world.db.query(Segment)
            .filter(Segment.session_id == agent._orm_session_id)
            .order_by(Segment.start_ms, Segment.speaker_id.is_(None)).all())


def _private_flags(world, agent):
    """[(speaker, transcript-prefix, is_private)] in time order."""
    return [("user" if s.speaker_id else "agent", s.transcript[:12], s.is_private)
            for s in _segments(world, agent)]


def _keep(scope):
    return [_tool_use("keep_private", {"scope": scope})]


@pytest.mark.anyio
async def test_keep_private_this_turn(world):
    llm = SnapshotLLM([
        "Lovely. What grew there?",
        _keep("this_turn"),
        "Of course, that part will stay private. What else do you remember?",
        "Roses! Who planted them?",
    ])
    agent, _ = _private_agent(world, llm)
    await agent.turn("We had a garden.")
    r2 = await agent.turn("SECRET_ONE my father lost money. Please don't tell anyone.")
    after_mark = len(llm.sent)
    await agent.turn("The garden had roses.")

    assert r2.marked_private
    assert agent.pending_private == []
    assert _private_flags(world, agent) == [
        ("user", "We had a gar", False), ("agent", "Lovely. What", False),
        ("user", "SECRET_ONE m", True), ("agent", "Of course, t", True),
        ("user", "The garden h", False), ("agent", "Roses! Who p", False),
    ]
    assert all("SECRET_ONE" not in req for req in llm.sent[after_mark:])
    assert "SECRET_ONE" in llm.sent[after_mark - 1]   # live: the turn itself had to hear it


@pytest.mark.anyio
async def test_keep_private_previous_turn_hides_both_turns(world):
    llm = SnapshotLLM([
        "That must have been hard. What happened then?",
        _keep("previous_turn"),
        "Of course, that will stay private.",
        "What a lovely tree.",
    ])
    agent, _ = _private_agent(world, llm)
    await agent.turn("SECRET_TWO my brother went to prison.")
    await agent.turn("Don't tell anyone that.")
    after_mark = len(llm.sent)
    await agent.turn("We also had a mulberry tree.")

    assert _private_flags(world, agent) == [
        ("user", "SECRET_TWO m", True), ("agent", "That must ha", True),
        ("user", "Don't tell a", True), ("agent", "Of course, t", True),
        ("user", "We also had ", False), ("agent", "What a lovel", False),
    ]
    assert all("SECRET_TWO" not in req for req in llm.sent[after_mark:])


@pytest.mark.anyio
async def test_keep_private_next_hides_the_following_turn(world):
    llm = SnapshotLLM([
        _keep("next"),
        "Of course. Go ahead, it will stay private.",
        "Thank you for trusting me with that.",
        "Tell me more about the garden.",
    ])
    agent, _ = _private_agent(world, llm)
    r1 = await agent.turn("I'll tell you something, but keep it secret.")
    r2 = await agent.turn("SECRET_THREE I once took money from my aunt.")
    after_mark = len(llm.sent)
    await agent.turn("Anyway, the garden.")

    assert not r1.marked_private and r2.marked_private
    assert _private_flags(world, agent) == [
        ("user", "I'll tell yo", False), ("agent", "Of course. G", False),
        ("user", "SECRET_THREE", True), ("agent", "Thank you fo", True),
        ("user", "Anyway, the ", False), ("agent", "Tell me more", False),
    ]
    assert all("SECRET_THREE" not in req for req in llm.sent[after_mark:])


@pytest.mark.anyio
async def test_failed_mark_stays_pending_until_it_succeeds(world):
    llm = SnapshotLLM([_keep("this_turn"), "Of course, that stays private.", "Go on."])
    agent, bridge = _private_agent(world, llm)
    bridge.fail_tools = {"mark_private"}
    result = await agent.turn("SECRET_FOUR keep this between us.")

    assert len(agent.pending_private) == 2
    assert [t.is_error for t in result.trace if t.tool == "mark_private"] == [True, True]
    assert not any(p for *_, p in _private_flags(world, agent))   # not private yet in the DB ...
    await agent.turn("Something else.")
    assert all("SECRET_FOUR" not in req for req in llm.sent[2:])  # ... but gone from the history

    bridge.fail_tools = set()
    traces = await agent.flush_private_marks()
    assert agent.pending_private == [] and not any(t.is_error for t in traces)
    assert [p for *_, p in _private_flags(world, agent)][:2] == [True, True]


@pytest.mark.anyio
async def test_privacy_claim_without_mark_is_made_true(world, caplog):
    llm = SnapshotLLM(["That will stay between us, I promise.", "Go on."])
    agent, bridge = _private_agent(world, llm)
    with caplog.at_level(logging.WARNING, logger="server.agents.chat_agent"):
        result = await agent.turn("SECRET_FIVE I never loved him.")
    await agent.turn("Anyway.")

    assert result.marked_private
    assert result.reply_text == "That will stay between us, I promise."   # the reply is kept
    assert [p for *_, p in _private_flags(world, agent)] == [True, True, False, False]
    assert "promised privacy without keep_private" in caplog.text
    assert "SECRET_FIVE" not in llm.sent[-1]


@pytest.mark.anyio
async def test_no_request_no_claim_nothing_private(world):
    llm = SnapshotLLM(["What a lovely memory. Who was there?"])
    agent, _ = _private_agent(world, llm)
    result = await agent.turn("We swam in the river.")
    assert not result.marked_private
    assert not any(p for *_, p in _private_flags(world, agent))


@pytest.mark.anyio
async def test_keep_private_bad_scope_is_an_error(world):
    llm = SnapshotLLM([[_tool_use("keep_private", {"scope": "everything"})], "Hmm."])
    agent, _ = _private_agent(world, llm)
    result = await agent.turn("Don't tell anyone.")
    assert result.trace[0].is_error
    assert "scope must be one of" in result.trace[0].result_preview


@pytest.mark.anyio
async def test_mark_private_is_not_offered_to_the_model(world):
    llm = SnapshotLLM(["Hello."])
    agent, bridge = _private_agent(world, llm)
    await agent.turn("hi")
    offered = {t["toolSpec"]["name"] for t in llm.calls[0]["tools"]["tools"]}
    assert "keep_private" in offered
    assert "mark_private" not in offered and "mark_reactions_delivered" not in offered


# ---------------------------------------------------------------------------
# Reactions are announced once
# ---------------------------------------------------------------------------

def _story_with_reaction(world):
    story = Story(circle_id=world.circle.id, teller_id=world.fatma.id, kind=StoryKind.original,
                  title="The Mulberry Tree", ai_summary="s", sources=[],
                  access={"type": AccessType.circle, "person_ids": []},
                  status=StoryStatus.published, publish_at=now_utc().isoformat(),
                  created_at=now_utc().isoformat())
    world.db.add(story); world.db.flush()
    world.db.add(Reaction(story_id=story.id, person_id=world.elif_.id, emoji=Emoji.laugh,
                          delivered_to_center=False, created_at=now_utc().isoformat()))
    world.db.commit()
    return story


@pytest.mark.anyio
async def test_reaction_delivered_after_it_is_said(world):
    story = _story_with_reaction(world)
    llm = SnapshotLLM([[_tool_use("get_session_context", {})],
                       "Your granddaughter Elif laughed at your mulberry tree story."])
    agent, _ = _private_agent(world, llm)
    result = await agent.turn("(Session started.)", store_user=False)

    assert [t.tool for t in result.trace] == ["get_session_context", "mark_reactions_delivered"]
    world.db.expire_all()
    assert world.db.get(Reaction, (story.id, world.elif_.id, Emoji.laugh.value)).delivered_to_center

    # The next session's context no longer has it.
    llm2 = SnapshotLLM([[_tool_use("get_session_context", {})], "Hello again."])
    agent2, _ = _private_agent(world, llm2)
    result2 = await agent2.turn("(Session started.)", store_user=False)
    assert result2.trace[0].result["undelivered_reactions"] == []


@pytest.mark.anyio
async def test_reaction_not_delivered_if_not_said(world):
    story = _story_with_reaction(world)
    llm = SnapshotLLM([[_tool_use("get_session_context", {})], "Good morning! How are you today?"])
    agent, _ = _private_agent(world, llm)
    result = await agent.turn("(Session started.)", store_user=False)
    assert "mark_reactions_delivered" not in [t.tool for t in result.trace]
    world.db.expire_all()
    assert not world.db.get(Reaction, (story.id, world.elif_.id, Emoji.laugh.value)).delivered_to_center


# ---------------------------------------------------------------------------
# Privacy guard: a reply must not touch a hidden part
# ---------------------------------------------------------------------------

from server.agents.chat_agent import GUARD_SAFE_REPLY, salient_terms

SECRET = ("My brother Selim borrowed money from my husband and never paid it back. "
          "Please don't tell anyone.")
SECRET_TERMS = salient_terms([SECRET], [])


def test_secret_terms_are_what_we_expect():
    assert SECRET_TERMS == {"brother", "selim", "borrowed", "money", "husband", "paid"}


def _no_terms(requests):
    """Requests must carry none of the hidden turn's terms."""
    from server.agents.chat_agent import mentions_any
    return all(not mentions_any(req, SECRET_TERMS) for req in requests)


@pytest.mark.anyio
async def test_later_reply_touching_hidden_part_is_regenerated(world, caplog):
    llm = SnapshotLLM([
        "Lovely. What grew there?",
        _keep("this_turn"),
        "Of course, that stays between us. Tell me about your garden.",
        "Did Selim ever pay you back?",                                     # blocked
        "Your roses sound lovely. Which colour did you like best?",         # regenerated
    ])
    agent, _ = _private_agent(world, llm)
    await agent.turn("We had a garden.")
    await agent.turn(SECRET)
    after_mark = len(llm.sent)
    with caplog.at_level(logging.WARNING, logger="server.agents.chat_agent"):
        r3 = await agent.turn("I grew red roses.")

    assert r3.privacy_guard == "regenerated"
    assert r3.reply_text == "Your roses sound lovely. Which colour did you like best?"
    # Nothing after the mark carried a hidden term: not the history, not the
    # blocked reply, not the regeneration instruction.
    assert len(llm.sent) == after_mark + 2
    assert _no_terms(llm.sent[after_mark:])
    assert "System note, not from the person" in llm.sent[-1]
    # Spoken / stored / remembered: the regenerated reply only.
    world.db.expire_all()
    assert _segments(world, agent)[-1].transcript == r3.reply_text
    assert "regenerated it (session" in caplog.text
    assert not any(term in caplog.text.lower() for term in SECRET_TERMS)


@pytest.mark.anyio
async def test_second_touch_uses_the_safe_reply(world, caplog):
    llm = SnapshotLLM([
        _keep("this_turn"),
        "Of course, that stays between us. Tell me about your garden.",
        "Did your brother visit often?",          # blocked
        "And what about the money?",              # regenerated, still touches it
    ])
    agent, _ = _private_agent(world, llm)
    await agent.turn(SECRET)
    with caplog.at_level(logging.WARNING, logger="server.agents.chat_agent"):
        result = await agent.turn("Anyway, the garden.")

    assert result.privacy_guard == "safe_reply"
    assert result.reply_text == GUARD_SAFE_REPLY
    assert "used the safe reply (session" in caplog.text
    assert not any(term in caplog.text.lower() for term in SECRET_TERMS)


@pytest.mark.anyio
async def test_guard_applies_in_the_same_turn_as_keep_private(world):
    # The prompt_v4 failure: acknowledging, then asking about the brother.
    llm = SnapshotLLM([
        _keep("this_turn"),
        "Of course, that stays between us. What was your brother's name again?",   # blocked
        "Of course, that stays between us. Tell me about your garden.",
    ])
    agent, _ = _private_agent(world, llm)
    result = await agent.turn(SECRET)

    assert result.privacy_guard == "regenerated"
    assert result.reply_text == "Of course, that stays between us. Tell me about your garden."
    assert "brother's name again" not in llm.sent[-1]       # the blocked reply was removed
    assert result.marked_private


@pytest.mark.anyio
async def test_words_the_speaker_used_openly_are_not_blocked(world):
    llm = SnapshotLLM([
        "How lovely. What did he catch?",
        _keep("this_turn"),
        "Of course, that stays between us.",
        "Your husband sounds like a patient man.",     # "husband" was said openly in turn 1
    ])
    agent, _ = _private_agent(world, llm)
    await agent.turn("My husband loved fishing on Sundays.")
    await agent.turn(SECRET)
    result = await agent.turn("He caught carp.")
    assert result.privacy_guard is None
    assert result.reply_text == "Your husband sounds like a patient man."


@pytest.mark.anyio
async def test_no_guard_without_hidden_part(world):
    llm = SnapshotLLM(["Did your brother Selim visit often?"])
    agent, _ = _private_agent(world, llm)
    result = await agent.turn("My brother Selim lived in Izmir.")
    assert result.privacy_guard is None


# ---------------------------------------------------------------------------
# Parenthetical asides are not spoken, stored or remembered
# ---------------------------------------------------------------------------

def test_strip_parentheticals():
    from server.agents.chat_agent import strip_parentheticals
    assert strip_parentheticals(
        "I was wondering, what was Zehra like?\n\n(When you're ready, I'd love to hear about her.)"
    ) == "I was wondering, what was Zehra like?"
    assert strip_parentheticals("What a lovely garden (and roses!). Who planted it?") == \
        "What a lovely garden. Who planted it?"
    assert strip_parentheticals("(Just an aside.)") == "Just an aside."


@pytest.mark.anyio
async def test_parenthetical_removed_from_reply_segment_and_history(world):
    llm = SnapshotLLM(["I was wondering, what was Zehra like? (When you're ready, I'm here to listen.)"])
    agent, _ = _private_agent(world, llm)
    result = await agent.turn("Hello.")
    assert result.reply_text == "I was wondering, what was Zehra like?"
    assert _segments(world, agent)[-1].transcript == "I was wondering, what was Zehra like?"
    assert agent._history[-1]["content"][0]["text"] == "I was wondering, what was Zehra like?"


# ---------------------------------------------------------------------------
# Guard terms: only sentences about a person (+ the next one); safe replies rotate
# ---------------------------------------------------------------------------

def test_terms_come_from_sentences_about_a_person_and_the_next_one():
    text = ("I need to tell you something important. My brother Selim borrowed money. "
            "He never paid it back. Our lovely garden had roses. We sewed curtains.")
    assert salient_terms([text], []) == {"brother", "selim", "borrowed", "money", "paid"}


def test_terms_fall_back_to_the_whole_turn_without_a_person():
    assert salient_terms(["I had an operation in 1970. Nobody may know."], []) == {"operation"}


def test_capitalised_sentence_starters_are_not_names():
    from server.agents.chat_agent import _names_a_person
    assert not _names_a_person("Now, the garden was lovely.")
    assert not _names_a_person("Please keep it quiet.")
    assert _names_a_person("Selim never paid.")
    assert _names_a_person("It was my grandmother's ring.")


@pytest.mark.anyio
async def test_safe_reply_is_never_repeated_twice_in_a_row(world):
    from server.agents.chat_agent import GUARD_SAFE_REPLIES
    llm = SnapshotLLM([
        _keep("this_turn"),
        "Of course, that stays between us.",
        "Did Selim pay?", "And the money?",           # turn 2: blocked twice
        "Did Selim pay?", "And the money?",           # turn 3: blocked twice
    ])
    agent, _ = _private_agent(world, llm)
    await agent.turn(SECRET)
    r2 = await agent.turn("Anyway.")
    r3 = await agent.turn("Let us go on.")
    assert r2.privacy_guard == r3.privacy_guard == "safe_reply"
    assert r2.reply_text in GUARD_SAFE_REPLIES and r3.reply_text in GUARD_SAFE_REPLIES
    assert r2.reply_text != r3.reply_text


# ---------------------------------------------------------------------------
# Guard terms: the next sentence counts only if it continues the same subject
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    # A topic change right after the secret is not part of it.
    ("My brother Selim borrowed money. Now, my wedding was lovely.",
     {"brother", "selim", "borrowed", "money"}),
    ("My brother Selim borrowed money. But oh, the roses were beautiful.",       # no marker: counts
     {"brother", "selim", "borrowed", "money", "rose", "beautiful"}),
    ("My brother Selim borrowed money. Speaking of roses, they bloomed.",          # marker
     {"brother", "selim", "borrowed", "money"}),
    ("My brother Selim borrowed money. Anyway, the roses bloomed.",                # marker
     {"brother", "selim", "borrowed", "money"}),
    ("My brother Selim borrowed money. The debt ruined us.",                       # no pronoun needed
     {"brother", "selim", "borrowed", "money", "debt", "ruined"}),
    # A pronoun continues the subject, also after and/but/so/then.
    ("My brother Selim borrowed money. And he never paid the debt.",
     {"brother", "selim", "borrowed", "money", "paid", "debt"}),
    ("My brother Selim borrowed money. That ruined my husband.",
     {"brother", "selim", "borrowed", "money", "ruined", "husband"}),
    # A sentence that names the person again qualifies on its own.
    ("My brother Selim borrowed money. Selim lost it at cards. We had roses.",
     {"brother", "selim", "borrowed", "money", "lost", "card", "rose"}),
])
def test_next_sentence_counts_unless_topic_change(text, expected):
    assert salient_terms([text], []) == expected


def test_private_scenario_first_line_terms():
    from evals.scenarios import SCENARIOS
    scenario = next(s for s in SCENARIOS if s.name == "private_then_move_on")
    assert scenario.first_person_line
    assert salient_terms([scenario.first_person_line], []) == {
        "borrowed", "brother", "husband", "money", "paid", "selim",
    }


# ---------------------------------------------------------------------------
# A spoken promise is always true: explicit keep_private marks; the final rule checks the rest
# ---------------------------------------------------------------------------

from server.agents.chat_agent import NEUTRAL_REPLY, checker_said_no

DECLINE = "I don't want to talk about my brother. That chapter is closed."
PROMISE = "Of course, that chapter stays between us."


@pytest.mark.parametrize("verdict,is_no", [
    ("no", True), ("**no**", True), ("No.", True),
    ("yes", False), ("unsure", False), ("**Unsure**", False), ("", False), ("not sure", False),
])
def test_checker_said_no(verdict, is_no):
    assert checker_said_no(verdict) is is_no


@pytest.mark.anyio
async def test_explicit_keep_private_always_marks_without_a_check(world):
    checker = SnapshotLLM(["no"])                   # would refuse, but is never asked
    llm = SnapshotLLM([_keep("previous_turn"), "Of course, that stays between us."])
    agent, _ = _private_agent(world, llm, checker)
    result = await agent.turn(DECLINE)
    assert result.marked_private
    assert result.privacy_check is None
    assert checker.sent == []


@pytest.mark.anyio
async def test_no_check_on_a_turn_already_hidden_by_next(world):
    checker = SnapshotLLM(["no"])
    llm = SnapshotLLM([_keep("next"), "Go ahead.", "Of course, that stays between us."])
    agent, _ = _private_agent(world, llm, checker)
    await agent.turn("I'll tell you something, keep it secret.")
    result = await agent.turn(SECRET)
    assert checker.sent == []                              # no extra request with the secret
    assert result.reply_text == "Of course, that stays between us."   # the true promise stays
    assert result.marked_private


@pytest.mark.anyio
async def test_no_check_without_a_promise(world):
    checker = SnapshotLLM(["yes"])
    llm = SnapshotLLM(["What a lovely garden. Who planted it?"])
    agent, _ = _private_agent(world, llm, checker)
    result = await agent.turn("We had a garden.")
    assert result.privacy_check is None
    assert checker.sent == []


@pytest.mark.anyio
@pytest.mark.parametrize("verdict", ["yes", "unsure", "", "**yes**", "maybe"])
async def test_final_rule_promise_confirmed_or_unsure_marks_previous_turn(world, verdict):
    checker = SnapshotLLM([verdict])
    llm = SnapshotLLM(["What a lovely garden. Who planted it?",
                       "That will stay between us, I promise."])
    agent, _ = _private_agent(world, llm, checker)
    await agent.turn("We had a garden.")
    result = await agent.turn(SECRET)
    assert result.privacy_check == "confirmed" and result.marked_private
    assert all(p for *_, p in _private_flags(world, agent))            # both turns hidden
    # The check saw the speaker's own words of this and the previous turn, nothing else
    # (its system prompt quotes "keep this between us" as an example, so look at messages).
    assert len(checker.sent) == 1
    sent = json.dumps(json.loads(checker.sent[0])["messages"])
    assert "never paid it back" in sent and "We had a garden" in sent
    assert "lovely garden" not in sent and "between us" not in sent


@pytest.mark.anyio
async def test_final_rule_checker_error_marks_previous_turn(world, caplog):
    class FailingChecker:
        def converse(self, *a, **kw):
            raise RuntimeError("ThrottlingException")

    llm = SnapshotLLM(["What a lovely garden. Who planted it?",
                       "That will stay between us, I promise."])
    agent, _ = _private_agent(world, llm, FailingChecker())
    await agent.turn("We had a garden.")
    with caplog.at_level(logging.WARNING, logger="server.agents.chat_agent"):
        result = await agent.turn(SECRET)                  # does not raise
    assert result.privacy_check == "confirmed" and result.marked_private
    assert all(p for *_, p in _private_flags(world, agent))
    assert "Privacy check failed; marking (session" in caplog.text
    assert "Selim" not in caplog.text


@pytest.mark.anyio
async def test_final_rule_unreadable_checker_answer_marks(world):
    class BrokenChecker:
        def converse(self, *a, **kw):
            return {"output": {}}                          # no message: unparsable

    llm = SnapshotLLM(["That will stay between us, I promise."])
    agent, _ = _private_agent(world, llm, BrokenChecker())
    result = await agent.turn(SECRET)
    assert result.privacy_check == "confirmed" and result.marked_private


@pytest.mark.anyio
async def test_final_rule_no_removes_promise_without_sounding_like_agreement(world, caplog):
    llm = SnapshotLLM([PROMISE, "Tell me about your garden instead."])
    agent, _ = _private_agent(world, llm, SnapshotLLM(["no"]))
    with caplog.at_level(logging.WARNING, logger="server.agents.chat_agent"):
        result = await agent.turn(DECLINE)
    assert result.privacy_check == "not_confirmed"
    assert not result.marked_private and agent.pending_private == []
    assert not any(p for *_, p in _private_flags(world, agent))
    assert result.reply_text == "Tell me about your garden instead."
    assert "stays between us" not in json.dumps(json.loads(llm.sent[-1])["messages"])
    assert "Privacy request not confirmed" in caplog.text
    assert "brother" not in caplog.text and "chapter" not in caplog.text


@pytest.mark.anyio
@pytest.mark.parametrize("regenerated", [
    "I understand. Tell me about your garden.",          # sounds like agreement
    "Of course. What else do you remember?",             # sounds like agreement
    "Don't worry, it will stay between us.",             # still a promise
])
async def test_final_rule_no_replacement_never_sounds_like_agreement(world, regenerated):
    from server.agents.chat_agent import _AGREEMENT
    llm = SnapshotLLM([PROMISE, regenerated])
    agent, _ = _private_agent(world, llm, SnapshotLLM(["no"]))
    result = await agent.turn(DECLINE)
    assert result.reply_text == NEUTRAL_REPLY
    assert not _AGREEMENT.search(NEUTRAL_REPLY)
    assert not result.marked_private


# --- the three privacy-reviewer scenarios ------------------------------------

@pytest.mark.anyio
async def test_reviewer_1_request_in_one_turn_secret_in_the_next(world):
    # "Just between us?" -> the model forgets keep_private("next") ->
    # the secret comes next and the reply promises privacy.
    checker = SnapshotLLM(["yes"])
    llm = SnapshotLLM(["Go ahead, I am listening.", "That stays between us."])
    agent, _ = _private_agent(world, llm, checker)
    await agent.turn("Can I tell you something, just between us?")
    result = await agent.turn("Selim took our savings and never paid it back.")
    sent = json.dumps(json.loads(checker.sent[0])["messages"])
    assert "just between us" in sent and "Selim took our savings" in sent   # both turns checked
    assert result.marked_private
    assert all(p for *_, p in _private_flags(world, agent))                  # both turns hidden


@pytest.mark.anyio
async def test_reviewer_2_promise_added_by_the_guard_rewrite(world):
    llm = SnapshotLLM([
        _keep("this_turn"), "Of course, that stays between us.",   # turn 1: the secret, marked
        "Your husband sounds hard-working.",                        # turn 2: touches a hidden term
        "Of course, that stays between us. What did you cook?",    # guard rewrite adds a promise
        "What did you like to cook for your family?",              # promise removed
    ])
    agent, _ = _private_agent(world, llm, SnapshotLLM(["no"]))
    await agent.turn(SECRET)
    result = await agent.turn("He worked at the bank for thirty years.")
    assert result.privacy_guard == "regenerated"
    assert result.privacy_check == "not_confirmed"
    assert result.reply_text == "What did you like to cook for your family?"
    assert not result.marked_private


@pytest.mark.anyio
async def test_reviewer_3_secret_in_the_previous_turn_is_hidden(world):
    # Turn N: the secret (no request). Turn N+1: "keep that to yourself",
    # and the reply promises privacy without keep_private.
    llm = SnapshotLLM(["That must have been hard.", "It stays between us."])
    agent, _ = _private_agent(world, llm, SnapshotLLM(["yes"]))
    await agent.turn("Selim took our savings and never paid it back.")
    result = await agent.turn("Please keep that to yourself.")
    assert result.marked_private
    flags = _private_flags(world, agent)
    assert flags[0][1].startswith("Selim took") and flags[0][2] is True       # the secret itself
    assert all(p for *_, p in flags)


def test_capitalised_first_word_is_a_name_only_if_used_as_one_elsewhere():
    # "Speaking"/"Tending" open a sentence; "Selim" is also used mid-sentence.
    assert salient_terms(["Tending roses calms me. Speaking of roses, they bloom."], []) == {
        "tending", "rose", "calm", "speaking", "bloom"}                  # no name: whole turn
    assert "lost" in salient_terms(["My brother Selim borrowed money. Selim lost it."], [])


def test_next_sentence_naming_a_different_person_is_not_a_continuation():
    from server.agents.chat_agent import _continues_subject
    assert not _continues_subject("Leyla loved the roses.", "My brother Selim borrowed money.",
                                  {"selim", "leyla"})
    assert _continues_subject("The debt ruined us.", "My brother Selim borrowed money.", {"selim"})
