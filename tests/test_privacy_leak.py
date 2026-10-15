"""
Privacy leak test.

Scope of the assertion
----------------------
The rule is that Segments from EARLIER sessions that are marked is_private=True
must never appear in anything sent to the LLM (system prompt or messages).

The center person's utterances in the CURRENT live session necessarily pass
through the LLM — that is the whole point of the chat agent. So we only assert
on private segments that belong to a DIFFERENT (earlier) session.

This test keeps protecting us as new tools are added: it runs a full scripted
session that calls every MCP tool that currently exists (get_session_context,
get_pending_questions, mark_question_asked), wraps the LLM in RecordingLLM,
and checks that no private transcript from a prior session appears in any of
the recorded requests.
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
from core.enums import (
    AccessType, CircleStatus, QuestionSource, QuestionStatus,
    Role, SessionKind, SessionStart, StoryKind, StoryStatus,
)
from core.models import (
    Base, Circle, Membership, Person, Question, Segment,
    Session as OrmSession, Story,
)
from core.services.session_tools import (
    get_pending_questions_data,
    get_session_context_data,
    mark_question_asked_data,
)
from server.agents.chat_agent import ChatAgent
from server.llm import RecordingLLM

# Re-use helpers from test_chat_agent.
from tests.test_chat_agent import FakeMCPBridge, ScriptedLLM, _tool_use


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
def world_with_prior_private_segment(db):
    """
    Build a world that includes a FINISHED session with a private segment.

    The private transcript is the string we will later assert is absent from
    all LLM requests made during the current (new) session.
    """
    now = now_utc()
    fatma = Person(name="Fatma", birth_year=1948, language="en")
    elif_ = Person(name="Elif",  birth_year=2003, language="en")
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

    # --- EARLIER (finished) session with a private segment ---
    prior_session = OrmSession(
        circle_id=circle.id,
        kind=SessionKind.solo,
        started_by=SessionStart.spontaneous,
        participant_ids=[fatma.id],
        started_at=(now - timedelta(hours=3)).isoformat(),
        ended_at=(now - timedelta(hours=2)).isoformat(),
    )
    db.add(prior_session)
    db.flush()

    private_text = "SECRET_PRIVATE_CONTENT_XYZ_UNIQUE"
    private_seg = Segment(
        session_id=prior_session.id,
        speaker_id=fatma.id,
        start_ms=0, end_ms=30_000,
        transcript=private_text,
        words=[], is_private=True,
    )
    public_seg = Segment(
        session_id=prior_session.id,
        speaker_id=fatma.id,
        start_ms=30_001, end_ms=60_000,
        transcript="This is public and fine to share.",
        words=[], is_private=False,
    )
    db.add_all([private_seg, public_seg])
    db.flush()

    # One waiting question so get_pending_questions has something to return.
    q = Question(
        circle_id=circle.id, target_person_id=fatma.id,
        asker_id=elif_.id, text="What was your first job?",
        source=QuestionSource.family, period=None,
        status=QuestionStatus.waiting, answer=None,
        created_at=(now - timedelta(hours=1)).isoformat(),
    )
    db.add(q)
    db.commit()

    class W:
        pass
    w = W()
    w.db = db; w.fatma = fatma; w.circle = circle
    w.q = q; w.private_text = private_text
    w.prior_session_id = prior_session.id
    return w


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_text_in_request(req: dict) -> str:
    """Serialise a full LLM request to a single string for substring search."""
    return json.dumps(req, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Leak test
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_private_segment_from_prior_session_never_reaches_llm(
    world_with_prior_private_segment,
):
    """
    Run a scripted session that exercises every current MCP tool.

    Assert that the private_text from the prior session never appears in any
    of the requests RecordingLLM captured.  Public text from the same session
    is allowed to appear (via get_session_context summaries) — only private
    transcripts are blocked.

    Note: the center person's utterances in THIS live session do reach the LLM
    as user messages; that is intentional and correct.  We assert only on
    prior-session private segments.
    """
    w = world_with_prior_private_segment

    uid1 = str(uuid.uuid4())
    uid2 = str(uuid.uuid4())
    uid3 = str(uuid.uuid4())

    # Script: call all three tools in order, then reply.
    script = [
        # Round 1: get_session_context + get_pending_questions
        [_tool_use("get_session_context", {}, uid1),
         _tool_use("get_pending_questions", {"limit": 5}, uid2)],
        # Round 2: mark_question_asked
        [_tool_use("mark_question_asked", {"question_id": w.q.id}, uid3)],
        # Final text reply
        "What was your first job, Fatma?",
    ]

    inner_llm = ScriptedLLM(script)
    recording_llm = RecordingLLM(inner_llm)

    bridge = FakeMCPBridge(w.db, w.fatma.id, w.circle.id)
    agent = ChatAgent(
        llm=recording_llm,
        person_id=w.fatma.id,
        circle_id=w.circle.id,
        db_session=w.db,
        bridge=bridge,
    )

    result = await agent.turn("(session start)")
    assert result.reply_text == "What was your first job, Fatma?"

    # Assert: the unique private transcript text must not appear in ANY request.
    for i, req in enumerate(recording_llm.requests):
        serialised = _all_text_in_request(req)
        assert w.private_text not in serialised, (
            f"Private transcript leaked into LLM request #{i}.\n"
            f"Private text: {w.private_text!r}\n"
            f"Request (truncated): {serialised[:500]}"
        )

    # Sanity: we did actually record some requests.
    assert len(recording_llm.requests) >= 1


# ---------------------------------------------------------------------------
# Optional live Bedrock test (skipped unless RUN_BEDROCK_TESTS=1)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.skipif(
    __import__("os").environ.get("RUN_BEDROCK_TESTS") != "1",
    reason="Set RUN_BEDROCK_TESTS=1 to run live Bedrock tests",
)
async def test_live_two_turn_conversation(world_with_prior_private_segment):
    """
    Two-turn live conversation using real Bedrock (Nova 2 Lite).

    Prerequisites:
      - AWS credentials configured (aws login)
      - MCP server running at EVOCA_MCP_URL
      - RUN_BEDROCK_TESTS=1 environment variable set
    """
    from server.llm import BedrockLLM

    w = world_with_prior_private_segment

    recording_llm = RecordingLLM(BedrockLLM())
    bridge = FakeMCPBridge(w.db, w.fatma.id, w.circle.id)
    agent = ChatAgent(
        llm=recording_llm,
        person_id=w.fatma.id,
        circle_id=w.circle.id,
        db_session=w.db,
        bridge=bridge,
    )

    result1 = await agent.turn("(Session started. I am Fatma.)")
    assert result1.reply_text, "First turn should produce a reply"

    result2 = await agent.turn("I worked at a tailor's shop when I was young.")
    assert result2.reply_text, "Second turn should produce a reply"

    # Privacy check still holds on live requests.
    for i, req in enumerate(recording_llm.requests):
        serialised = _all_text_in_request(req)
        assert w.private_text not in serialised, (
            f"Private transcript leaked in live request #{i}"
        )
