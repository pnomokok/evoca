"""
Tests for core.services.archive_tools — pure service functions.

All tests use an in-memory SQLite database with FK enforcement.

Coverage:
  get_session_transcript  — non-private segments in order, private text and ids
                            never returned, agent segment has null speaker,
                            asked questions with asker name and relation,
                            session from another circle rejected
  save_story              — happy path (pending, circle access, publish_at +24h,
                            ai subjects), retelling kind, private-overlap rejection,
                            boundary touch allowed, invalid period / member /
                            session / range / duplicate subject / original story
  record_answer           — happy path, status rules (waiting, answered),
                            story from another circle, private-overlap rejection
  add_question            — waiting vs filtered, invalid source, center target
  mark_question_declined  — asked -> declined; status rules; range checks
  reopen_question         — asked -> waiting; status rules
  get_session_transcript  — a declined question is no longer listed as asked
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from core.clock import now_utc
from core.enums import (
    AccessType, CircleStatus, LifePeriod, PeriodSource, QuestionSource,
    QuestionStatus, Role, SessionKind, SessionStart, StoryKind, StoryStatus,
)
from core.models import (
    Base, Circle, Membership, Person, Question, Segment, SensitiveTopic,
    Session as OrmSession, Story, StorySubject,
)
from core.services.archive_tools import (
    add_question_data,
    get_session_transcript_data,
    mark_question_declined_data,
    extend_session_answers,
    merge_stories_data,
    record_answer_data,
    reopen_question_data,
    save_story_data,
)

PRIVATE_TEXT = "PRIVATE_ARCHIVE_SECRET_QWERTY"


# ---------------------------------------------------------------------------
# DB fixture
# ---------------------------------------------------------------------------

def _enable_fk(dbapi_conn, _record):
    c = dbapi_conn.cursor()
    c.execute("PRAGMA foreign_keys=ON")
    c.close()


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


class _World:
    pass


@pytest.fixture(scope="function")
def w(db) -> _World:
    """
    Circle with fatma (center) and elif (member, granddaughter).
    One ended session with segments:
      0–10 000       fatma, public
      10 000–12 000  agent
      12 000–20 000  fatma, PRIVATE
      20 000–30 000  fatma, public
    One asked family question, one waiting question, one sensitive topic.
    A second circle with its own session and story (for cross-circle checks).
    """
    w = _World()
    now = now_utc()

    fatma = Person(name="Fatma", birth_year=1948, language="en")
    elif_ = Person(name="Elif", birth_year=2003, language="en")
    stranger = Person(name="Stranger", birth_year=1960, language="en")
    db.add_all([fatma, elif_, stranger])
    db.flush()

    circle = Circle(name="Test Family", center_person_id=fatma.id,
                    status=CircleStatus.active, chat_time="10:00",
                    timezone="Europe/Istanbul")
    other_circle = Circle(name="Other Family", center_person_id=stranger.id,
                          status=CircleStatus.active, chat_time="10:00",
                          timezone="Europe/Istanbul")
    db.add_all([circle, other_circle])
    db.flush()

    db.add_all([
        Membership(person_id=fatma.id, circle_id=circle.id, role=Role.center),
        Membership(person_id=elif_.id, circle_id=circle.id, role=Role.member,
                   relation_to_center="granddaughter"),
        Membership(person_id=stranger.id, circle_id=other_circle.id, role=Role.center),
    ])
    db.flush()

    sess = OrmSession(circle_id=circle.id, kind=SessionKind.solo,
                      started_by=SessionStart.spontaneous, participant_ids=[fatma.id],
                      started_at=(now - timedelta(hours=1)).isoformat(),
                      ended_at=(now - timedelta(minutes=30)).isoformat())
    other_sess = OrmSession(circle_id=other_circle.id, kind=SessionKind.solo,
                            started_by=SessionStart.spontaneous,
                            participant_ids=[stranger.id],
                            started_at=now.isoformat(), ended_at=now.isoformat())
    db.add_all([sess, other_sess])
    db.flush()

    seg_a = Segment(session_id=sess.id, speaker_id=fatma.id, start_ms=0, end_ms=10_000,
                    transcript="I grew up next to the river.",
                    words=[{"w": "I", "start_ms": 0, "end_ms": 200}], is_private=False)
    seg_agent = Segment(session_id=sess.id, speaker_id=None, start_ms=10_000, end_ms=12_000,
                        transcript="What did you do by the river?", words=[], is_private=False)
    seg_private = Segment(session_id=sess.id, speaker_id=fatma.id, start_ms=12_000,
                          end_ms=20_000, transcript=PRIVATE_TEXT, words=[], is_private=True)
    seg_b = Segment(session_id=sess.id, speaker_id=fatma.id, start_ms=20_000, end_ms=30_000,
                    transcript="We fished there every summer.", words=[], is_private=False)
    # Inserted out of order to check ordering.
    db.add_all([seg_b, seg_private, seg_agent, seg_a])
    db.flush()

    other_story = Story(circle_id=other_circle.id, teller_id=stranger.id,
                        kind=StoryKind.original, title="Elsewhere",
                        sources=[{"session_id": other_sess.id, "start_ms": 0, "end_ms": 1}],
                        access={"type": AccessType.circle, "person_ids": []},
                        status=StoryStatus.published,
                        publish_at=now.isoformat(), created_at=now.isoformat())
    db.add(other_story)

    q_asked = Question(circle_id=circle.id, target_person_id=fatma.id, asker_id=elif_.id,
                       text="Where did you grow up?", source=QuestionSource.family,
                       status=QuestionStatus.asked,
                       created_at=(now - timedelta(days=1)).isoformat())
    q_waiting = Question(circle_id=circle.id, target_person_id=fatma.id, asker_id=elif_.id,
                         text="What was your first job?", source=QuestionSource.family,
                         status=QuestionStatus.waiting,
                         created_at=(now - timedelta(days=1)).isoformat())
    db.add_all([q_asked, q_waiting])

    db.add(SensitiveTopic(circle_id=circle.id, text="1977 traffic accident",
                          added_by=elif_.id, created_at=now.isoformat()))
    db.commit()

    w.db = db
    w.fatma, w.elif_, w.stranger = fatma, elif_, stranger
    w.circle, w.other_circle = circle, other_circle
    w.sess, w.other_sess = sess, other_sess
    w.seg_a, w.seg_agent, w.seg_private, w.seg_b = seg_a, seg_agent, seg_private, seg_b
    w.other_story = other_story
    w.q_asked, w.q_waiting = q_asked, q_waiting
    return w


def _save(w, **overrides) -> str:
    kwargs = dict(
        title="By the River",
        summary="Fatma remembers growing up next to the river.",
        teller_id=w.fatma.id,
        subjects=[{"person_id": w.fatma.id, "period": "childhood"}],
        sources=[{"session_id": w.sess.id, "start_ms": 0, "end_ms": 10_000}],
    )
    kwargs.update(overrides)
    story_id = save_story_data(w.db, w.fatma.id, w.circle.id, **kwargs)
    w.db.commit()
    return story_id


# ---------------------------------------------------------------------------
# get_session_transcript
# ---------------------------------------------------------------------------

def test_transcript_returns_public_segments_in_order(w):
    r = get_session_transcript_data(w.db, w.fatma.id, w.circle.id, w.sess.id)
    assert r.session_id == w.sess.id
    assert r.started_at == w.sess.started_at
    assert [s.start_ms for s in r.segments] == [0, 10_000, 20_000]
    assert r.segments[0].speaker_name == "Fatma"
    assert r.segments[0].words == [{"w": "I", "start_ms": 0, "end_ms": 200}]


def test_transcript_agent_segment_has_null_speaker(w):
    r = get_session_transcript_data(w.db, w.fatma.id, w.circle.id, w.sess.id)
    agent = [s for s in r.segments if s.start_ms == 10_000][0]
    assert agent.speaker_id is None
    assert agent.speaker_name is None


def test_transcript_never_contains_private_text_or_id(w):
    from dataclasses import asdict
    r = get_session_transcript_data(w.db, w.fatma.id, w.circle.id, w.sess.id)
    serialised = json.dumps(asdict(r))
    assert PRIVATE_TEXT not in serialised
    assert w.seg_private.id not in serialised


def test_transcript_lists_asked_questions_only(w):
    r = get_session_transcript_data(w.db, w.fatma.id, w.circle.id, w.sess.id)
    assert [q.question_id for q in r.asked_questions] == [w.q_asked.id]
    q = r.asked_questions[0]
    assert q.text == "Where did you grow up?"
    assert q.asker_name == "Elif"
    assert q.asker_relation_to_center == "granddaughter"


def test_transcript_rejects_session_from_other_circle(w):
    with pytest.raises(ValueError, match="not found in this circle"):
        get_session_transcript_data(w.db, w.fatma.id, w.circle.id, w.other_sess.id)


# ---------------------------------------------------------------------------
# save_story
# ---------------------------------------------------------------------------

def test_save_story_happy_path(w):
    story_id = _save(w, place="River village", stated_year=1955)
    s = w.db.get(Story, story_id)
    assert s.status == StoryStatus.pending
    assert s.kind == StoryKind.original
    assert s.original_story_id is None
    assert dict(s.access) == {"type": "circle", "person_ids": []}
    assert s.ai_summary == "Fatma remembers growing up next to the river."
    assert s.place == "River village"
    assert s.stated_year == 1955
    assert list(s.sources) == [{"session_id": w.sess.id, "start_ms": 0, "end_ms": 10_000}]
    created = datetime.fromisoformat(s.created_at)
    assert datetime.fromisoformat(s.publish_at) - created == timedelta(hours=24)

    subjects = w.db.query(StorySubject).filter(StorySubject.story_id == story_id).all()
    assert len(subjects) == 1
    assert subjects[0].person_id == w.fatma.id
    assert subjects[0].period == LifePeriod.childhood
    assert subjects[0].period_source == PeriodSource.ai


def test_save_story_uses_demo_now(w, monkeypatch):
    monkeypatch.setenv("DEMO_NOW", "2026-10-18T09:00:00+00:00")
    s = w.db.get(Story, _save(w))
    assert s.created_at == "2026-10-18T09:00:00+00:00"
    assert s.publish_at == "2026-10-19T09:00:00+00:00"


def test_save_story_retelling(w):
    original = _save(w)
    retold = _save(w, title="The River Again", original_story_id=original)
    s = w.db.get(Story, retold)
    assert s.kind == StoryKind.retelling
    assert s.original_story_id == original


def test_save_story_empty_subjects_allowed(w):
    story_id = _save(w, subjects=[])
    assert w.db.query(StorySubject).filter(StorySubject.story_id == story_id).count() == 0


def test_save_story_rejects_private_overlap(w):
    before = w.db.query(Story).count()
    with pytest.raises(ValueError, match="overlaps a private part") as exc:
        _save(w, sources=[{"session_id": w.sess.id, "start_ms": 5_000, "end_ms": 15_000}])
    assert w.seg_private.id not in str(exc.value)
    assert PRIVATE_TEXT not in str(exc.value)
    assert w.db.query(Story).count() == before


def test_save_story_rejects_range_inside_private(w):
    with pytest.raises(ValueError, match="overlaps a private part"):
        _save(w, sources=[{"session_id": w.sess.id, "start_ms": 13_000, "end_ms": 14_000}])


def test_save_story_rejects_one_bad_source_among_many(w):
    with pytest.raises(ValueError, match="overlaps a private part"):
        _save(w, sources=[
            {"session_id": w.sess.id, "start_ms": 0, "end_ms": 10_000},
            {"session_id": w.sess.id, "start_ms": 0, "end_ms": 30_000},
        ])


def test_save_story_boundary_touch_is_not_overlap(w):
    story_id = _save(w, sources=[
        {"session_id": w.sess.id, "start_ms": 0, "end_ms": 12_000},
        {"session_id": w.sess.id, "start_ms": 20_000, "end_ms": 30_000},
    ])
    assert w.db.get(Story, story_id) is not None


def test_save_story_rejects_invalid_period(w):
    with pytest.raises(ValueError, match="Invalid period"):
        _save(w, subjects=[{"person_id": w.fatma.id, "period": "old_age"}])


def test_save_story_rejects_teller_not_member(w):
    with pytest.raises(ValueError, match="Teller"):
        _save(w, teller_id=w.stranger.id)


def test_save_story_rejects_subject_not_member(w):
    with pytest.raises(ValueError, match="Subject"):
        _save(w, subjects=[{"person_id": w.stranger.id, "period": "youth"}])


def test_save_story_rejects_duplicate_subject(w):
    with pytest.raises(ValueError, match="more than once"):
        _save(w, subjects=[
            {"person_id": w.fatma.id, "period": "youth"},
            {"person_id": w.fatma.id, "period": "childhood"},
        ])


def test_save_story_rejects_session_from_other_circle(w):
    with pytest.raises(ValueError, match="not found in this circle"):
        _save(w, sources=[{"session_id": w.other_sess.id, "start_ms": 0, "end_ms": 10}])


def test_save_story_rejects_bad_range(w):
    with pytest.raises(ValueError, match="start_ms must be less than end_ms"):
        _save(w, sources=[{"session_id": w.sess.id, "start_ms": 5_000, "end_ms": 5_000}])


def test_save_story_rejects_empty_sources(w):
    with pytest.raises(ValueError, match="at least one source"):
        _save(w, sources=[])


def test_save_story_rejects_original_from_other_circle(w):
    with pytest.raises(ValueError, match="Original story"):
        _save(w, original_story_id=w.other_story.id)


# ---------------------------------------------------------------------------
# record_answer
# ---------------------------------------------------------------------------

def test_record_answer_happy_path(w):
    story_id = _save(w)
    answer = record_answer_data(w.db, w.fatma.id, w.circle.id,
                                w.q_asked.id, story_id, 0, 10_000)
    w.db.commit()
    q = w.db.get(Question, w.q_asked.id)
    assert q.status == QuestionStatus.answered
    expected = {"story_id": story_id, "session_id": w.sess.id,
                "start_ms": 0, "end_ms": 10_000}
    assert dict(q.answer) == expected
    assert answer == expected


def test_record_answer_accepts_unasked_family_question(w):
    # The speaker sometimes answers a waiting family question on her own.
    story_id = _save(w)
    answer = record_answer_data(w.db, w.fatma.id, w.circle.id, w.q_waiting.id, story_id, 0, 10_000)
    w.db.commit()
    q = w.db.get(Question, w.q_waiting.id)
    assert q.status == QuestionStatus.answered
    assert q.answer == answer and answer["story_id"] == story_id


@pytest.mark.parametrize("source", [QuestionSource.follow_up, QuestionSource.gap])
def test_record_answer_rejects_waiting_agent_question(w, source):
    story_id = _save(w)
    w.q_waiting.source = source
    w.db.commit()
    with pytest.raises(ValueError, match="expected 'asked'"):
        record_answer_data(w.db, w.fatma.id, w.circle.id,
                           w.q_waiting.id, story_id, 0, 10_000)


def test_record_answer_rejects_already_answered(w):
    story_id = _save(w)
    record_answer_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id, story_id, 0, 10_000)
    w.db.commit()
    with pytest.raises(ValueError, match="expected 'asked'"):
        record_answer_data(w.db, w.fatma.id, w.circle.id,
                           w.q_asked.id, story_id, 0, 10_000)


def test_record_answer_rejects_story_from_other_circle(w):
    with pytest.raises(ValueError, match="Story .* not found in this circle"):
        record_answer_data(w.db, w.fatma.id, w.circle.id,
                           w.q_asked.id, w.other_story.id, 0, 10)


def test_record_answer_rejects_private_overlap(w):
    story_id = _save(w)
    with pytest.raises(ValueError, match="overlaps a private part"):
        record_answer_data(w.db, w.fatma.id, w.circle.id,
                           w.q_asked.id, story_id, 0, 30_000)
    assert w.db.get(Question, w.q_asked.id).status == QuestionStatus.asked


# ---------------------------------------------------------------------------
# add_question
# ---------------------------------------------------------------------------

def test_add_question_waiting(w):
    r = add_question_data(w.db, w.fatma.id, w.circle.id,
                          "What fish did you catch in the river?", "follow_up", "childhood")
    w.db.commit()
    assert r["status"] == "waiting"
    q = w.db.get(Question, r["question_id"])
    assert q.status == QuestionStatus.waiting
    assert q.source == QuestionSource.follow_up
    assert q.period == LifePeriod.childhood
    assert q.asker_id is None
    assert q.target_person_id == w.fatma.id


def test_add_question_filtered_by_sensitive_topic(w):
    r = add_question_data(w.db, w.fatma.id, w.circle.id,
                          "Can you tell me about the accident?", "gap", "midlife")
    w.db.commit()
    assert r["status"] == "filtered"
    assert w.db.get(Question, r["question_id"]).status == QuestionStatus.filtered


def test_add_question_rejects_family_source(w):
    with pytest.raises(ValueError, match="Invalid source"):
        add_question_data(w.db, w.fatma.id, w.circle.id, "Anything?", "family")


def test_add_question_rejects_invalid_period(w):
    with pytest.raises(ValueError, match="Invalid period"):
        add_question_data(w.db, w.fatma.id, w.circle.id, "Anything?", "gap", "old_age")


# ---------------------------------------------------------------------------
# mark_question_declined / reopen_question
# ---------------------------------------------------------------------------

def test_mark_question_declined(w):
    mark_question_declined_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id, w.sess.id, 20_000, 30_000)
    w.db.commit()
    assert w.db.get(Question, w.q_asked.id).status == QuestionStatus.declined
    r = get_session_transcript_data(w.db, w.fatma.id, w.circle.id, w.sess.id)
    assert r.asked_questions == []


def test_mark_question_declined_status_and_range_rules(w):
    with pytest.raises(ValueError, match="expected 'asked'"):
        mark_question_declined_data(w.db, w.fatma.id, w.circle.id, w.q_waiting.id,
                                    w.sess.id, 20_000, 30_000)
    with pytest.raises(ValueError, match="overlaps a private part"):
        mark_question_declined_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id,
                                    w.sess.id, 10_000, 25_000)
    with pytest.raises(ValueError, match="not found in this circle"):
        mark_question_declined_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id,
                                    w.other_sess.id, 0, 10)
    assert w.db.get(Question, w.q_asked.id).status == QuestionStatus.asked


def test_reopen_question(w):
    reopen_question_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id)
    w.db.commit()
    assert w.db.get(Question, w.q_asked.id).status == QuestionStatus.waiting
    with pytest.raises(ValueError, match="expected 'asked'"):
        reopen_question_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id)   # now waiting


def test_reopen_refuses_declined_and_answered(w):
    mark_question_declined_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id, w.sess.id, 20_000, 30_000)
    w.db.commit()
    with pytest.raises(ValueError, match="expected 'asked'"):
        reopen_question_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id)
    assert w.db.get(Question, w.q_asked.id).status == QuestionStatus.declined


# ---------------------------------------------------------------------------
# record_answer: unasked family questions, server-side rules
# ---------------------------------------------------------------------------

def test_record_answer_rejects_unasked_sensitive_family_question(w):
    story_id = _save(w)
    w.q_waiting.text = "What happened in the 1977 traffic accident?"
    w.db.commit()
    with pytest.raises(ValueError, match="not found"):
        record_answer_data(w.db, w.fatma.id, w.circle.id, w.q_waiting.id, story_id, 0, 10_000)
    assert w.db.get(Question, w.q_waiting.id).status == QuestionStatus.waiting


def test_record_answer_rejects_unasked_question_for_someone_else(w):
    story_id = _save(w)
    w.q_waiting.target_person_id = w.elif_.id
    w.db.commit()
    with pytest.raises(ValueError, match="not found"):
        record_answer_data(w.db, w.fatma.id, w.circle.id, w.q_waiting.id, story_id, 0, 10_000)


# ---------------------------------------------------------------------------
# merge_stories
# ---------------------------------------------------------------------------

def _merge(w, ids, session_id=None):
    return merge_stories_data(w.db, w.fatma.id, w.circle.id, session_id or w.sess.id,
                              ids, "One Memory", "Fatma remembers the river.")


def test_merge_stories_unions_sources_and_moves_the_answer(w):
    first = _save(w)
    second = _save(w, title="Fishing", stated_year=1958,
                   sources=[{"session_id": w.sess.id, "start_ms": 20_000, "end_ms": 30_000}])
    record_answer_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id, second, 20_000, 30_000)
    out = _merge(w, [first, second])
    w.db.commit()
    assert out == {"story_id": first, "merged_ids": [second]}
    story = w.db.get(Story, first)
    assert story.title == "One Memory" and story.stated_year == 1958
    assert [(x["start_ms"], x["end_ms"]) for x in story.sources] == [(0, 10_000), (20_000, 30_000)]
    assert w.db.get(Story, second) is None
    assert w.db.get(Question, w.q_asked.id).answer["story_id"] == first
    assert w.db.query(StorySubject).filter(StorySubject.story_id == second).count() == 0


def _two_part_story_answered(w, *, merged: bool) -> str:
    """Fatma's answer is 0-10 000; the rest of her answer is 20 000-30 000."""
    if merged:
        first = _save(w)
        second = _save(w, title="Fishing",
                       sources=[{"session_id": w.sess.id, "start_ms": 20_000, "end_ms": 30_000}])
        record_answer_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id, first, 0, 10_000)
        _merge(w, [first, second])
    else:
        first = _save(w, sources=[{"session_id": w.sess.id, "start_ms": 0, "end_ms": 10_000},
                                  {"session_id": w.sess.id, "start_ms": 20_000, "end_ms": 30_000}])
        record_answer_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id, first, 0, 10_000)
    w.db.commit()
    return first


def _answer_range(w):
    ans = w.db.get(Question, w.q_asked.id).answer
    return ans["start_ms"], ans["end_ms"]


def _agent_only_gap(w):
    w.seg_private.speaker_id, w.seg_private.is_private = None, False   # 10 000-20 000: the agent
    w.db.commit()


def test_merge_stories_extends_the_answer_to_the_merged_story(w):
    _agent_only_gap(w)
    first = _two_part_story_answered(w, merged=True)
    assert w.db.get(Question, w.q_asked.id).answer["story_id"] == first
    assert _answer_range(w) == (0, 30_000)


def test_merge_stories_never_extends_the_answer_over_a_private_part(w):
    _two_part_story_answered(w, merged=True)        # 12 000-20 000 is private
    assert _answer_range(w) == (0, 10_000)


def test_merge_stories_never_extends_the_answer_over_speech_left_out_of_the_story(w):
    # 12 000-20 000 is Fatma speaking (another story, a refused topic...):
    # the answer range must not let the asker hear it.
    w.seg_private.is_private = False
    w.db.commit()
    _two_part_story_answered(w, merged=True)
    assert _answer_range(w) == (0, 10_000)


def test_extend_session_answers_repairs_older_answers(w):
    _agent_only_gap(w)
    _two_part_story_answered(w, merged=False)
    assert extend_session_answers(w.db, w.other_sess.id) == []
    assert extend_session_answers(w.db, w.sess.id) == [w.q_asked.id]
    assert _answer_range(w) == (0, 30_000)
    assert extend_session_answers(w.db, w.sess.id) == []    # idempotent


def test_merge_stories_rejects_a_published_story(w):
    first, second = _save(w), _save(w, title="Fishing")
    w.db.get(Story, second).status = StoryStatus.published
    w.db.commit()
    with pytest.raises(ValueError, match="not pending"):
        _merge(w, [first, second])


def test_merge_stories_rejects_another_session(w):
    first, second = _save(w), _save(w, title="Fishing")
    with pytest.raises(ValueError, match="not from the session"):
        _merge(w, [first, second], session_id=w.other_sess.id)


def test_merge_stories_rejects_a_missing_session_header(w):
    first, second = _save(w), _save(w, title="Fishing")
    with pytest.raises(ValueError, match="No session"):
        merge_stories_data(w.db, w.fatma.id, w.circle.id, "", [first, second], "T", "S")


def test_merge_stories_rejects_another_teller(w):
    first = _save(w)
    second = _save(w, title="Elif's memory", teller_id=w.elif_.id,
                   subjects=[{"person_id": w.elif_.id, "period": "childhood"}])
    with pytest.raises(ValueError, match="same teller"):
        _merge(w, [first, second])


def test_merge_stories_rejects_another_circle(w):
    first = _save(w)
    with pytest.raises(ValueError, match="not found in this circle"):
        _merge(w, [first, w.other_story.id])
