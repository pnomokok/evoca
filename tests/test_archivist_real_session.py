"""
Regression test from a real browser session (feeea8a0, data/browser.db, 17 Oct).

The real archivist made three mistakes there that the evals missed:
- it saved Fatma's refusal ("Please don't ask me about my murder Mustafa") as a
  story, "Declining to Discuss Mustafa";
- it split the games memory into three stories and the wedding into two;
- it never matched the games answer to Elif's waiting games question, because
  that question was never asked in the session.

The segments come from tests/fixtures/real_session_feeea8a0.json (with the
private range and its made-up secret). A scripted archivist repeats the real
run's calls; a rule-based fake checker stands in for the temperature-0
checker. The test covers the code paths: the refusal guard on save_story (and
the refused topic it sends down the add_refused_topic path), the automatic
merge of split stories that share a period, and the answer to an unasked
family question. No network, no real Bedrock.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.clock import now_utc
from core.enums import (
    CircleStatus, QuestionSource, QuestionStatus, Role, SessionKind, SessionStart, TopicSource,
)
from core.models import (
    Base, Circle, Membership, Person, Question, Segment, SensitiveTopic,
    Session as OrmSession, Story, StorySubject,
)
from server.agents.archivist_agent import (
    _ANSWER_CHECK_PROMPT,
    _MERGE_TEXT_PROMPT,
    _REFUSAL_CHECK_PROMPT,
    _STORY_REFUSAL_PROMPT,
    _TOPIC_NAME_PROMPT,
    ArchivistAgent,
)
from tests.test_archivist_agent import DynamicScriptedLLM, FakeArchiveBridge, last_tool_json
from tests.test_chat_agent import _tool_use

FIXTURE = Path(__file__).parent / "fixtures" / "real_session_feeea8a0.json"
SECRET_WORDS = ("istanbul", "train", "ticket")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def real(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    now = now_utc()

    fatma = Person(name="Fatma Yilmaz", birth_year=1948, language="en", created_at=now.isoformat())
    elif_ = Person(name="Elif Yilmaz", birth_year=2003, language="en", created_at=now.isoformat())
    db.add_all([fatma, elif_]); db.flush()
    circle = Circle(name="The Yilmaz Family", center_person_id=fatma.id, status=CircleStatus.active,
                    chat_time="10:00", timezone="Europe/Istanbul")
    db.add(circle); db.flush()
    db.add_all([Membership(person_id=fatma.id, circle_id=circle.id, role=Role.center),
                Membership(person_id=elif_.id, circle_id=circle.id, role=Role.member,
                           relation_to_center="granddaughter")])
    sess = OrmSession(circle_id=circle.id, kind=SessionKind.solo, started_by=SessionStart.invitation,
                      participant_ids=[fatma.id], started_at=(now - timedelta(minutes=12)).isoformat(),
                      ended_at=now.isoformat())
    db.add(sess); db.flush()
    for seg in data["segments"]:
        db.add(Segment(session_id=sess.id, speaker_id=fatma.id if seg["speaker"] == "center" else None,
                       start_ms=seg["start_ms"], end_ms=seg["end_ms"], transcript=seg["transcript"],
                       words=[], is_private=seg["is_private"]))
    # The school question was asked in the session; the games questions never were.
    school = Question(circle_id=circle.id, target_person_id=fatma.id, asker_id=elif_.id,
                      text="Grandma, what was school like when you were young?",
                      source=QuestionSource.family, period="childhood", status=QuestionStatus.asked,
                      created_at=(now - timedelta(days=1)).isoformat())
    games = [Question(circle_id=circle.id, target_person_id=fatma.id, asker_id=elif_.id, text=q["text"],
                      source=QuestionSource.family, period=q["period"], status=QuestionStatus.waiting,
                      created_at=(now - timedelta(hours=3 - i)).isoformat())
             for i, q in enumerate(data["games_questions"])]
    db.add_all([school, *games])
    db.commit()

    class W:
        pass
    w = W()
    w.db, w.fatma, w.elif_, w.circle, w.sess, w.school, w.games = db, fatma, elif_, circle, sess, school, games
    w.segments = data["segments"]
    yield w
    db.close()


def _range(w, startswith: str) -> tuple[int, int]:
    seg = next(s for s in w.segments if s["speaker"] == "center" and s["transcript"].startswith(startswith))
    return seg["start_ms"], seg["end_ms"]


class RuleChecker:
    """Stands in for the temperature-0 checker: answers by prompt, from the passage."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def converse(self, system, messages, tools=None) -> dict:
        self.calls.append({"system": system, "messages": messages})
        prompt, text = system[0]["text"], messages[-1]["content"][0]["text"].lower()
        if prompt == _STORY_REFUSAL_PROMPT:
            reply = "yes" if "don't ask me" in text else "no"
        elif prompt == _TOPIC_NAME_PROMPT:
            reply = "Mustafa"
        elif prompt == _REFUSAL_CHECK_PROMPT:
            reply = "yes" if "mustafa" in text and "don't" in text else "no"
        elif prompt == _ANSWER_CHECK_PROMPT:
            reply = "yes" if "games" in text.split("passage:")[0] and "hide and seek" in text else "no"
        else:
            reply = "no"
        return {"stopReason": "end_turn", "usage": {},
                "output": {"message": {"role": "assistant", "content": [{"text": reply}]}}}


def _story(w, title, ranges, period, year=None):
    args = {"title": title, "summary": f"Fatma Yilmaz remembers {title.lower()}.", "teller_id": w.fatma.id,
            "subjects": [{"person_id": w.fatma.id, "period": period}],
            "sources": [{"session_id": w.sess.id, "start_ms": a, "end_ms": b} for a, b in ranges]}
    if year:
        args["stated_year"] = year
    return args


def _real_run_script(w) -> list:
    """The calls the real archivist made, plus an answer to the unasked games question."""
    hop, five, hide = _range(w, "Oh games"), _range(w, "And they play"), _range(w, "In the evenings")
    wed1, wed2 = _range(w, "Let me tell you"), _range(w, "It went all morning")
    mustafa = _range(w, "Please don't ask")
    return [
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("save_story", _story(w, "Hopscotch and Stick Driving", [hop], "childhood")),
         _tool_use("save_story", _story(w, "Five Stones Game", [five], "childhood")),
         _tool_use("save_story", _story(w, "Hide and Seek Evenings", [hide], "childhood")),
         _tool_use("save_story", _story(w, "Early Wedding Days", [wed1], "marriage_early_years", 1971)),
         _tool_use("save_story", _story(w, "Wedding Morning and Red Scarf", [wed2], "marriage_early_years")),
         _tool_use("save_story", _story(w, "Declining to Discuss Mustafa", [mustafa], "midlife"))],
        # The answer points at the second games story; the merge must move it.
        lambda msgs: [_tool_use("record_answer", {
            "question_id": w.games[0].id, "story_id": last_tool_json(msgs, 1)["story_id"],
            "start_ms": hop[0], "end_ms": hide[1]})],
        "Saved the games and the wedding.",
        '{"title": "Games of Childhood", "summary": "Fatma Yilmaz remembers the games she played as a child."}',
        '{"title": "The Spring Wedding", "summary": "Fatma Yilmaz remembers her wedding in the spring of 1971."}',
    ]


@pytest.mark.anyio
async def test_real_session_refusal_merge_and_unasked_answer(real, caplog):
    w = real
    llm = DynamicScriptedLLM(_real_run_script(w))
    checker = RuleChecker()
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=w.sess.id)
    agent = ArchivistAgent(llm=llm, person_id=w.fatma.id, circle_id=w.circle.id, bridge=bridge,
                           checker_llm=checker)
    with caplog.at_level("INFO", logger="server.agents.archivist_agent"):
        result = await agent.run(w.sess.id)
    w.db.expire_all()

    # The model was shown the unasked games questions in the first message and with the transcript.
    first = llm.calls[0]["messages"][0]["content"][0]["text"]
    assert all(g.text in first and g.id in first for g in w.games)
    transcript = next(t for t in result.trace if t.tool == "get_session_transcript").result
    shown = {q["question_id"] for q in transcript["waiting_family_questions"]}
    assert {g.id for g in w.games} <= shown

    # 1. The refusal is not a story; Mustafa is a speaker's refused topic.
    stories = w.db.query(Story).filter(Story.circle_id == w.circle.id).all()
    assert not any("mustafa" in (s.title + (s.ai_summary or "")).lower() for s in stories)
    assert result.stories_refused == 1
    save_mustafa = [t for t in result.trace if t.tool == "save_story" and "Mustafa" in t.input["title"]]
    assert save_mustafa[0].is_error
    topics = w.db.query(SensitiveTopic).filter(SensitiveTopic.circle_id == w.circle.id).all()
    assert [(t.text, t.source) for t in topics] == [("Mustafa", TopicSource.speaker)]
    assert result.topics_refused == [topics[0].id]

    # 2. Games = one childhood story, wedding = one story in marriage_early_years, 1971.
    assert len(stories) == 2 and len(result.story_ids) == 2
    by_period = {w.db.query(StorySubject).filter(StorySubject.story_id == s.id).one().period: s
                 for s in stories}
    games_story, wedding = by_period["childhood"], by_period["marriage_early_years"]
    assert games_story.title == "Games of Childhood"
    assert len(games_story.sources) == 3
    assert wedding.title == "The Spring Wedding" and wedding.stated_year == 1971
    assert len(wedding.sources) == 2
    assert len(result.stories_merged) == 2

    # 3. The unasked games question is answered, and the answer moved to the merged story.
    q = w.db.get(Question, w.games[0].id)
    assert q.status == QuestionStatus.answered
    assert q.answer["story_id"] == games_story.id
    assert (q.answer["start_ms"], q.answer["end_ms"]) == (games_story.sources[0]["start_ms"],
                                                          games_story.sources[-1]["end_ms"])
    assert w.db.get(Question, w.games[1].id).status == QuestionStatus.waiting
    # The asked school question was not answered: back to waiting.
    assert w.db.get(Question, w.school.id).status == QuestionStatus.waiting

    # The secret is nowhere: not saved, not sent to any LLM, not logged.
    saved = " ".join([s.title + " " + (s.ai_summary or "") for s in w.db.query(Story).all()]
                     + [x.text for x in w.db.query(Question).all()]
                     + [t.text for t in w.db.query(SensitiveTopic).all()]).lower()
    sent = json.dumps([c["messages"] for c in llm.calls + checker.calls]).lower()
    logged = " ".join(r.getMessage() for r in caplog.records).lower()
    for word in SECRET_WORDS:
        assert word not in saved and word not in sent and word not in logged
    # Logs carry ids only: no titles, topics or words of the speaker.
    assert "mustafa" not in logged and "wedding" not in logged and "games" not in logged

    # The merge text was written from the merged transcript, one call per merged story.
    merge_calls = [c for c in llm.calls if c["system"][0]["text"] == _MERGE_TEXT_PROMPT]
    assert len(merge_calls) == 2
    assert "hide and seek" in json.dumps(merge_calls[0]["messages"]).lower()


@pytest.mark.anyio
async def test_unasked_follow_up_question_cannot_be_answered(real):
    w = real
    follow = Question(circle_id=w.circle.id, target_person_id=w.fatma.id, asker_id=None,
                      text="What games did you play with your friends?", source=QuestionSource.follow_up,
                      status=QuestionStatus.waiting, created_at=now_utc().isoformat())
    w.db.add(follow); w.db.commit()
    hop = _range(w, "Oh games")
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("save_story", _story(w, "Games", [hop], "childhood"))],
        lambda msgs: [_tool_use("record_answer", {
            "question_id": follow.id, "story_id": last_tool_json(msgs)["story_id"],
            "start_ms": hop[0], "end_ms": hop[1]})],
        "done",
    ])
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=w.sess.id)
    agent = ArchivistAgent(llm=llm, person_id=w.fatma.id, circle_id=w.circle.id, bridge=bridge,
                           checker_llm=RuleChecker())
    result = await agent.run(w.sess.id)
    assert result.trace[-1].tool == "record_answer" and result.trace[-1].is_error
    w.db.expire_all()
    assert w.db.get(Question, follow.id).status == QuestionStatus.waiting


@pytest.mark.anyio
async def test_refusal_guard_unsure_or_error_blocks_the_story(real):
    w = real
    hop = _range(w, "Oh games")

    class Unsure(RuleChecker):
        def converse(self, system, messages, tools=None):
            if system[0]["text"] == _STORY_REFUSAL_PROMPT:
                raise RuntimeError("throttled")
            return super().converse(system, messages, tools)

    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("save_story", _story(w, "Games", [hop], "childhood"))],
        "done",
    ])
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=w.sess.id)
    agent = ArchivistAgent(llm=llm, person_id=w.fatma.id, circle_id=w.circle.id, bridge=bridge,
                           checker_llm=Unsure())
    result = await agent.run(w.sess.id)
    assert result.story_ids == [] and result.stories_refused == 1
    # Not a refusal by the refusal checker's own rule, so no topic is added either.
    assert w.db.query(SensitiveTopic).count() == 0


@pytest.mark.anyio
async def test_refusal_guard_reads_every_speaker_not_the_models_teller(real):
    # The model names the wrong teller: the guard still sees Fatma's refusal.
    w = real
    mustafa = _range(w, "Please don't ask")
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("save_story", {**_story(w, "About Mustafa", [mustafa], "midlife"), "teller_id": w.elif_.id})],
        "done",
    ])
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=w.sess.id)
    agent = ArchivistAgent(llm=llm, person_id=w.fatma.id, circle_id=w.circle.id, bridge=bridge,
                           checker_llm=RuleChecker())
    result = await agent.run(w.sess.id)
    assert result.story_ids == [] and result.stories_refused == 1
    w.db.expire_all()
    assert w.db.query(Story).count() == 0
    assert [t.text for t in w.db.query(SensitiveTopic).all()] == ["Mustafa"]


@pytest.mark.anyio
async def test_refusal_guard_retries_once_after_a_checker_error(real):
    w = real
    hop = _range(w, "Oh games")

    class FlakyOnce(RuleChecker):
        failed = False

        def converse(self, system, messages, tools=None):
            if system[0]["text"] == _STORY_REFUSAL_PROMPT and not FlakyOnce.failed:
                FlakyOnce.failed = True
                raise RuntimeError("throttled")
            return super().converse(system, messages, tools)

    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("save_story", _story(w, "Games", [hop], "childhood"))],
        "done",
    ])
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=w.sess.id)
    agent = ArchivistAgent(llm=llm, person_id=w.fatma.id, circle_id=w.circle.id, bridge=bridge,
                           checker_llm=FlakyOnce())
    result = await agent.run(w.sess.id)
    assert len(result.story_ids) == 1 and result.stories_refused == 0


@pytest.mark.anyio
async def test_sensitive_waiting_question_is_never_shown_or_answered(real):
    w = real
    w.db.add(SensitiveTopic(circle_id=w.circle.id, text="games", source=TopicSource.family,
                            added_by=w.elif_.id, created_at=now_utc().isoformat()))
    w.db.commit()
    hop = _range(w, "Oh games")
    llm = DynamicScriptedLLM([
        [_tool_use("get_session_transcript", {"session_id": w.sess.id})],
        [_tool_use("save_story", _story(w, "Games", [hop], "childhood"))],
        lambda msgs: [_tool_use("record_answer", {
            "question_id": w.games[0].id, "story_id": last_tool_json(msgs)["story_id"],
            "start_ms": hop[0], "end_ms": hop[1]})],
        "done",
    ])
    bridge = FakeArchiveBridge(w.db, w.fatma.id, w.circle.id, session_id=w.sess.id)
    agent = ArchivistAgent(llm=llm, person_id=w.fatma.id, circle_id=w.circle.id, bridge=bridge,
                           checker_llm=RuleChecker())
    result = await agent.run(w.sess.id)
    first = llm.calls[0]["messages"][0]["content"][0]["text"]
    assert all(g.text not in first and g.id not in first for g in w.games)
    transcript = next(t for t in result.trace if t.tool == "get_session_transcript").result
    assert not ({g.id for g in w.games} & {q["question_id"] for q in transcript["waiting_family_questions"]})
    assert result.trace[-1].tool == "record_answer" and result.trace[-1].is_error
    w.db.expire_all()
    assert all(w.db.get(Question, g.id).status == QuestionStatus.waiting for g in w.games)
