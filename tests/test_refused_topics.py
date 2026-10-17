"""
Topics the speaker refuses on her own ("I don't want to talk about Hatice today").

Coverage
--------
- Archivist: a refusal confirmed by the checker adds a SensitiveTopic with
  source "speaker", added_by the center; "no", "unsure", an empty reply or a
  checker error adds nothing.
- Range rules: a range reaching into a private part, or outside the session
  being archived, is rejected before the checker is asked; the service checks
  the session, the range and the speaker again (another circle's session, no
  session header, a private overlap, only agent words, only another
  participant's words, a panel recording, a viewer who is not the center).
- In a gathering, another participant's refusal never reaches the checker.
- Not offered in panel_recording mode.
- Matching: a follow-up about the topic in a later session is saved as
  "filtered". POST /api/questions matching only a speaker topic is stored as
  "filtered" but answered like an accepted question ("waiting"); a family-topic
  match keeps the generic filtered message.
- Panel endpoints (GET /api/circle, /api/feed, /api/stories/{id},
  /api/lifeline/{id}) never contain a speaker topic, for the admin either.
- get_session_context returns both sources in avoid_topics, without a label,
  to the center only; any other viewer gets [].
- A refusal is stored even when a family topic has the same text, so deleting
  that family topic leaves the refusal in place.
- add_missing_columns adds sensitive_topic.source to an older database file,
  keeps its rows and is idempotent.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text

from core.clock import now_utc
from core.db import add_missing_columns
from core.enums import QuestionStatus, Role, SessionKind, SessionStart, TopicSource
from core.models import Base, Membership, Question, Segment, SensitiveTopic, Session as OrmSession
from core.services import admin as admin_svc
from core.services.archive_tools import add_question_data, add_refused_topic_data
from core.services.session_tools import get_session_context_data
from server.agents.archivist_agent import ArchivistAgent
from tests.test_api import _client, anyio_backend, test_app  # noqa: F401  (fixtures)
from tests.test_archive_tools import PRIVATE_TEXT, db, w  # noqa: F401  (fixtures)
from tests.test_archivist_agent import DynamicScriptedLLM, FakeArchiveBridge
from tests.test_chat_agent import ScriptedLLM, _tool_use
from tests.test_panel_stories import world  # noqa: F401  (fixture)

REFUSAL_TEXT = "I don't want to talk about my sister Hatice today. Ask me about the garden."
TOPIC = "Hatice"


class RaisingLLM:
    """A checker whose call fails."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def converse(self, system, messages, tools=None) -> dict:
        self.calls.append({"system": system, "messages": messages})
        raise RuntimeError("Bedrock throttled")


def _set_speaker_text(w, text_):
    seg = w.db.query(Segment).filter(Segment.session_id == w.sess.id,
                                     Segment.start_ms == 20_000).one()
    seg.transcript = text_
    w.db.commit()


def _agent(w, llm, checker, session_id=None, **kwargs):
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=session_id or w.sess.id)
    agent = ArchivistAgent(llm=llm, person_id=w.fatma.id, circle_id=w.circle.id,
                           bridge=bridge, checker_llm=checker, **kwargs)
    return agent, bridge


def _refusal_script(w, start_ms=20_000, end_ms=30_000, topic=TOPIC):
    return [
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("add_refused_topic", {"text": topic, "start_ms": start_ms, "end_ms": end_ms})],
        "done",
    ]


def _make_gathering_with_elif_refusing(w):
    """Elif joins the session and refuses a topic herself at 30 000-35 000."""
    w.sess.kind = SessionKind.gathering
    w.sess.participant_ids = [w.fatma.id, w.elif_.id]
    w.db.add(Segment(session_id=w.sess.id, speaker_id=w.elif_.id, start_ms=30_000, end_ms=35_000,
                     transcript="I don't want to talk about my exam.", words=[], is_private=False))
    w.db.commit()


def _speaker_topics(w):
    w.db.expire_all()
    return w.db.query(SensitiveTopic).filter(SensitiveTopic.source == TopicSource.speaker).all()


# ---------------------------------------------------------------------------
# Archivist
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_confirmed_refusal_adds_a_speaker_topic(w):
    _set_speaker_text(w, REFUSAL_TEXT)
    checker = ScriptedLLM(["yes"])
    agent, _ = _agent(w, DynamicScriptedLLM(_refusal_script(w)), checker)
    result = await agent.run(w.sess.id)

    topics = _speaker_topics(w)
    assert len(topics) == 1
    t = topics[0]
    assert (t.text, t.added_by, t.circle_id) == (TOPIC, w.fatma.id, w.circle.id)
    assert result.topics_refused == [t.id]
    seen = checker.calls[0]["messages"][0]["content"][0]["text"]
    assert TOPIC in seen and REFUSAL_TEXT in seen
    assert PRIVATE_TEXT not in seen


@pytest.mark.anyio
@pytest.mark.parametrize("checker", [
    ScriptedLLM(["no"]), ScriptedLLM(["unsure"]), ScriptedLLM([""]), RaisingLLM(),
], ids=["no", "unsure", "empty", "error"])
async def test_unconfirmed_refusal_adds_nothing(w, checker):
    _set_speaker_text(w, "We fished there every summer.")
    agent, bridge = _agent(w, DynamicScriptedLLM(_refusal_script(w)), checker)
    result = await agent.run(w.sess.id)

    call = [t for t in result.trace if t.tool == "add_refused_topic"][0]
    assert call.is_error and "Topic not saved" in call.result_preview
    assert result.topics_refused == []
    assert _speaker_topics(w) == []
    assert "add_refused_topic" not in [n for n, _ in bridge.tool_calls]


@pytest.mark.anyio
@pytest.mark.parametrize("start_ms,end_ms", [
    (12_000, 20_000),    # exactly the private part
    (10_000, 25_000),    # spans into it
    (30_000, 40_000),    # outside the session being archived
], ids=["private", "overlaps_private", "outside_session"])
async def test_rejected_range_never_reaches_the_checker(w, start_ms, end_ms):
    _set_speaker_text(w, REFUSAL_TEXT)
    checker = ScriptedLLM(["yes"])
    agent, bridge = _agent(w, DynamicScriptedLLM(_refusal_script(w, start_ms, end_ms)), checker)
    result = await agent.run(w.sess.id)

    call = [t for t in result.trace if t.tool == "add_refused_topic"][0]
    assert call.is_error
    assert checker.calls == []
    assert _speaker_topics(w) == []
    assert "add_refused_topic" not in [n for n, _ in bridge.tool_calls]


@pytest.mark.anyio
async def test_another_participants_refusal_never_reaches_the_checker(w):
    _make_gathering_with_elif_refusing(w)
    checker = ScriptedLLM(["yes"])
    agent, bridge = _agent(w, DynamicScriptedLLM(_refusal_script(w, 30_000, 35_000, "exam")), checker)
    result = await agent.run(w.sess.id)

    call = [t for t in result.trace if t.tool == "add_refused_topic"][0]
    assert call.is_error
    assert checker.calls == []
    assert _speaker_topics(w) == []


@pytest.mark.anyio
async def test_not_offered_for_a_panel_recording(w):
    llm = DynamicScriptedLLM(["done"])
    agent, _ = _agent(w, llm, ScriptedLLM(["yes"]), panel_recording=True)
    await agent.run(w.sess.id)
    names = {t["toolSpec"]["name"] for t in llm.calls[0]["tools"]["tools"]}
    assert "add_refused_topic" not in names


@pytest.mark.anyio
async def test_follow_up_about_the_topic_in_a_later_session_is_filtered(w):
    _set_speaker_text(w, REFUSAL_TEXT)
    agent1, _ = _agent(w, DynamicScriptedLLM(_refusal_script(w)), ScriptedLLM(["yes"]))
    await agent1.run(w.sess.id)

    sess2 = OrmSession(circle_id=w.circle.id, kind=SessionKind.solo,
                       started_by=SessionStart.spontaneous, participant_ids=[w.fatma.id],
                       started_at=now_utc().isoformat(), ended_at=now_utc().isoformat())
    w.db.add(sess2); w.db.flush()
    w.db.add(Segment(session_id=sess2.id, speaker_id=w.fatma.id, start_ms=0, end_ms=5_000,
                     transcript="My sister and I picked figs in the garden.", words=[],
                     is_private=False))
    w.db.commit()

    llm2 = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": sess2.id})],
        [_tool_use("add_question", {"text": "What was your sister Hatice like?",
                                    "source": "follow_up"})],
        "done",
    ])
    agent2, _ = _agent(w, llm2, ScriptedLLM(["yes"]), session_id=sess2.id)
    result2 = await agent2.run(sess2.id)
    assert [q["status"] for q in result2.questions_added] == [QuestionStatus.filtered.value]


# ---------------------------------------------------------------------------
# Service: the same range rules, checked again on the server
# ---------------------------------------------------------------------------

def _add(w, session_id=None, start_ms=20_000, end_ms=30_000, viewer=None):
    return add_refused_topic_data(w.db, (viewer or w.fatma).id, w.circle.id,
                                  w.sess.id if session_id is None else session_id,
                                  TOPIC, start_ms, end_ms)


def test_service_adds_a_speaker_topic_once(w):
    first = _add(w)
    again = _add(w)
    assert first["added"] is True and again == {"topic_id": first["topic_id"], "added": False}
    assert len(_speaker_topics(w)) == 1


def test_refusal_outlives_a_deleted_family_topic_with_the_same_text(w):
    w.db.query(Membership).filter(Membership.person_id == w.elif_.id).update({"role": Role.admin})
    w.db.commit()
    family = admin_svc.add_family_topic(w.db, w.elif_.id, w.circle.id, TOPIC)
    assert _add(w)["added"] is True            # the family row is not the center's refusal
    admin_svc.delete_family_topic(w.db, w.elif_.id, w.circle.id, family["id"])

    assert [t.text for t in _speaker_topics(w)] == [TOPIC]
    assert TOPIC in get_session_context_data(w.db, w.fatma.id, w.circle.id).avoid_topics
    q = add_question_data(w.db, w.fatma.id, w.circle.id, "What was Hatice like?", "follow_up")
    assert q["status"] == QuestionStatus.filtered.value


def test_service_rejects_a_topic_that_would_filter_nothing(w):
    with pytest.raises(ValueError):
        add_refused_topic_data(w.db, w.fatma.id, w.circle.id, w.sess.id, "the war", 20_000, 30_000)
    assert _speaker_topics(w) == []


@pytest.mark.anyio
async def test_non_string_topic_is_rejected_before_the_checker(w):
    _set_speaker_text(w, REFUSAL_TEXT)
    checker = ScriptedLLM(["yes"])
    script = [[_tool_use("add_refused_topic", {"text": ["Hatice"], "start_ms": 20_000,
                                               "end_ms": 30_000})], "done"]
    agent, _ = _agent(w, DynamicScriptedLLM(script), checker)
    await agent.run(w.sess.id)
    assert checker.calls == [] and _speaker_topics(w) == []


@pytest.mark.parametrize("case", [
    "other_circle_session", "no_session", "private_overlap", "agent_only",
    "participant_only", "panel_recording", "not_center",
])
def test_service_rejects_bad_ranges(w, case):
    kwargs = {}
    if case == "participant_only":
        _make_gathering_with_elif_refusing(w)
        kwargs.update(start_ms=30_000, end_ms=35_000)
    if case == "other_circle_session":
        kwargs["session_id"] = w.other_sess.id
    elif case == "no_session":
        kwargs["session_id"] = ""
    elif case == "private_overlap":
        kwargs.update(start_ms=10_000, end_ms=25_000)
    elif case == "agent_only":
        kwargs.update(start_ms=10_000, end_ms=12_000)
    elif case == "panel_recording":
        w.sess.started_by = SessionStart.panel_recording
        w.db.commit()
    elif case == "not_center":
        kwargs["viewer"] = w.elif_
    with pytest.raises(ValueError) as exc:
        _add(w, **kwargs)
    assert PRIVATE_TEXT not in str(exc.value)
    assert _speaker_topics(w) == []


# ---------------------------------------------------------------------------
# get_session_context: avoid_topics
# ---------------------------------------------------------------------------

def test_session_context_lists_both_sources_without_a_label(w):
    _add(w)
    ctx = get_session_context_data(w.db, w.fatma.id, w.circle.id)
    assert sorted(ctx.avoid_topics) == sorted(["1977 traffic accident", TOPIC])
    assert all(isinstance(t, str) for t in ctx.avoid_topics)


def test_session_context_gives_no_avoid_topics_to_anyone_but_the_center(w):
    _add(w)
    ctx = get_session_context_data(w.db, w.elif_.id, w.circle.id)
    assert ctx.avoid_topics == []


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

SPEAKER_TOPIC = "her sister Zuleyhanur"


def _add_speaker_topic(db, circle, center):
    db.add(SensitiveTopic(circle_id=circle.id, text=SPEAKER_TOPIC, source=TopicSource.speaker,
                          added_by=center.id, created_at=now_utc().isoformat()))
    db.commit()


async def _ask(app, asker, target, text_):
    async with _client(app) as c:
        return await c.post("/api/questions", headers={"x-person-id": asker.id},
                            json={"target_person_id": target.id, "text": text_})


@pytest.mark.anyio
async def test_question_matching_only_a_speaker_topic_looks_accepted_but_is_filtered(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    _add_speaker_topic(db, circle, fatma)
    blocked = await _ask(app, elif_, fatma, "What happened with Zuleyhanur?")
    normal = await _ask(app, elif_, fatma, "Did you have a favourite teacher?")

    b, n = blocked.json(), normal.json()
    assert blocked.status_code == normal.status_code == 200
    # Same shape and values as a normal accepted question: nothing tells the asker.
    assert b["status"] == n["status"] == "waiting"
    assert set(b) == set(n) and set(b["question"]) == set(n["question"])
    assert b["question"]["status"] == "waiting" and "message" not in b
    db.expire_all()
    assert db.get(Question, b["question"]["id"]).status == QuestionStatus.filtered
    assert db.get(Question, n["question"]["id"]).status == QuestionStatus.waiting


@pytest.mark.anyio
async def test_question_matching_a_family_topic_keeps_the_generic_message(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    _add_speaker_topic(db, circle, fatma)
    db.add(SensitiveTopic(circle_id=circle.id, text="Zuleyhanur wedding quarrel",
                          added_by=fatma.id, created_at=now_utc().isoformat()))   # family
    db.commit()
    data = (await _ask(app, elif_, fatma, "What happened with Zuleyhanur?")).json()
    assert data["status"] == "filtered" and data["question"] is None
    assert "Zuleyhanur" not in data["message"] and "sister" not in data["message"]


@pytest.mark.anyio
async def test_panel_endpoints_never_return_a_speaker_topic(world):
    db, circle, fatma = world["db"], world["circle"], world["fatma"]
    _add_speaker_topic(db, circle, fatma)
    urls = ["/api/circle", "/api/feed", f"/api/stories/{world['mulberry'].id}",
            f"/api/lifeline/{fatma.id}"]
    async with _client(world["app"]) as c:
        for viewer in (world["ayse"], fatma, world["elif_"]):     # admin, center, member
            for url in urls:
                r = await c.get(url, headers={"x-person-id": viewer.id})
                assert r.status_code == 200, (url, r.text)
                assert "Zuleyhanur" not in r.text, (viewer.name, url)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def test_source_column_is_added_to_an_old_database_and_rows_are_kept(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:      # the table as it was before the source column
        conn.execute(text("DROP TABLE sensitive_topic"))
        conn.execute(text(
            "CREATE TABLE sensitive_topic (id VARCHAR PRIMARY KEY, circle_id VARCHAR NOT NULL, "
            "text TEXT NOT NULL, added_by VARCHAR NOT NULL, created_at VARCHAR NOT NULL)"
        ))
        conn.execute(text(
            "INSERT INTO sensitive_topic VALUES ('t1', 'c1', '1977 traffic accident', 'p1', '2026-10-01')"
        ))

    assert add_missing_columns(eng) == ["sensitive_topic.source"]
    assert add_missing_columns(eng) == []          # idempotent
    assert "source" in {c["name"] for c in inspect(eng).get_columns("sensitive_topic")}
    with eng.connect() as conn:
        rows = conn.execute(text("SELECT id, text, source FROM sensitive_topic")).all()
    assert rows == [("t1", "1977 traffic accident", "family")]
    eng.dispose()
