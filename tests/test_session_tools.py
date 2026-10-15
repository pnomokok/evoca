"""
Tests for core.services.session_tools — pure service functions.

All tests use an in-memory SQLite database with FK enforcement.
No MCP context is needed: the service layer is tested directly.

Coverage:
  require_member          — valid member, missing person_id, missing circle_id,
                            person not in circle
  get_session_context     — center identity, invitation present/absent,
                            undelivered reactions filtered by can_see,
                            session summaries only from visible stories
  get_pending_questions   — ordering (family→follow_up→gap then oldest-first),
                            sensitive-topic filtering (no status change),
                            limit respected, asker name and relation included
  mark_question_asked     — happy path, wrong circle, already asked, not found
"""

from __future__ import annotations

import os
import pytest
from datetime import timedelta
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from core.models import (
    Base, Circle, Invitation, Membership, Person,
    Question, Reaction, Segment, SensitiveTopic,
    Session as OrmSession, Story, StorySubject,
)
from core.enums import (
    AccessType, CircleStatus, Emoji, InvitationStatus,
    LifePeriod, PeriodSource, QuestionSource, QuestionStatus,
    Role, SessionKind, SessionStart, StoryKind, StoryStatus,
)
from core.clock import now_utc
from core.services.session_tools import (
    get_pending_questions_data,
    get_session_context_data,
    mark_question_asked_data,
    require_member,
)


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


# ---------------------------------------------------------------------------
# Common setup helper
# ---------------------------------------------------------------------------

class _World:
    """A minimal but complete fixture world for testing."""


def _build_world(db) -> _World:
    """
    Circle with:
      fatma  = center
      ayse   = admin     (relation: daughter)
      elif_  = member    (relation: granddaughter)
      can    = member    (relation: grandson)
      outsider = no membership

    One finished session with two non-private segments.
    Two published circle-access stories (mulberry, tailor) and one pending selected story.
    Two waiting family questions by Elif targeting Fatma.
    One sensitive topic.
    One undelivered reaction by Elif on the mulberry story.
    Today's invitation.
    """
    w = _World()
    now = now_utc()

    fatma    = Person(name="Fatma",    birth_year=1948, language="en")
    ayse     = Person(name="Ayse",     birth_year=1975, language="en")
    elif_    = Person(name="Elif",     birth_year=2003, language="en")
    can      = Person(name="Can",      birth_year=2006, language="en")
    outsider = Person(name="Outsider", birth_year=1990, language="en")
    db.add_all([fatma, ayse, elif_, can, outsider])
    db.flush()

    circle = Circle(
        name="The Yilmaz Family",
        center_person_id=fatma.id,
        status=CircleStatus.active,
        chat_time="10:00",
        timezone="Europe/Istanbul",
    )
    db.add(circle)
    db.flush()

    db.add_all([
        Membership(person_id=fatma.id, circle_id=circle.id,
                   role=Role.center, relation_to_center=None),
        Membership(person_id=ayse.id,  circle_id=circle.id,
                   role=Role.admin,  relation_to_center="daughter"),
        Membership(person_id=elif_.id, circle_id=circle.id,
                   role=Role.member, relation_to_center="granddaughter"),
        Membership(person_id=can.id,   circle_id=circle.id,
                   role=Role.member, relation_to_center="grandson"),
    ])
    db.flush()

    sess = OrmSession(
        circle_id=circle.id,
        kind=SessionKind.solo,
        started_by=SessionStart.spontaneous,
        participant_ids=[fatma.id],
        started_at=(now - timedelta(hours=2)).isoformat(),
        ended_at=(now - timedelta(hours=1)).isoformat(),
    )
    db.add(sess)
    db.flush()

    seg = Segment(
        session_id=sess.id, speaker_id=fatma.id,
        start_ms=0, end_ms=30_000,
        transcript="mulberry tree memory", words=[], is_private=False,
    )
    db.add(seg)
    db.flush()

    story_mulberry = Story(
        circle_id=circle.id, teller_id=fatma.id,
        kind=StoryKind.original,
        title="The Mulberry Tree",
        ai_summary="Fatma recalls the mulberry tree.",
        sources=[{"session_id": sess.id, "start_ms": 0, "end_ms": 30_000}],
        access={"type": AccessType.circle, "person_ids": []},
        status=StoryStatus.published,
        publish_at=(now - timedelta(hours=1)).isoformat(),
        created_at=(now - timedelta(hours=2)).isoformat(),
    )
    story_tailor = Story(
        circle_id=circle.id, teller_id=fatma.id,
        kind=StoryKind.original,
        title="The Tailor's Shop",
        ai_summary="Fatma remembers the tailor's shop.",
        sources=[{"session_id": sess.id, "start_ms": 30_001, "end_ms": 60_000}],
        access={"type": AccessType.circle, "person_ids": []},
        status=StoryStatus.published,
        publish_at=(now - timedelta(hours=1)).isoformat(),
        created_at=(now - timedelta(hours=1, minutes=50)).isoformat(),
    )
    # Private story — only fatma can see it.
    story_private = Story(
        circle_id=circle.id, teller_id=fatma.id,
        kind=StoryKind.original,
        title="Secret",
        ai_summary="This should not appear in session context for non-teller viewers.",
        sources=[{"session_id": sess.id, "start_ms": 60_001, "end_ms": 90_000}],
        access={"type": AccessType.private, "person_ids": []},
        status=StoryStatus.published,
        publish_at=(now - timedelta(hours=1)).isoformat(),
        created_at=(now - timedelta(hours=1, minutes=40)).isoformat(),
    )
    db.add_all([story_mulberry, story_tailor, story_private])
    db.flush()

    # Reaction by Elif on mulberry (undelivered).
    reaction = Reaction(
        story_id=story_mulberry.id, person_id=elif_.id,
        emoji=Emoji.laugh, delivered_to_center=False,
        created_at=now.isoformat(),
    )
    db.add(reaction)

    # Reaction already delivered — should not appear.
    reaction_delivered = Reaction(
        story_id=story_tailor.id, person_id=can.id,
        emoji=Emoji.heart, delivered_to_center=True,
        created_at=now.isoformat(),
    )
    db.add(reaction_delivered)
    db.flush()

    # Today's invitation (using UTC date that will match the fixture now_utc()).
    from zoneinfo import ZoneInfo
    today_str = now_utc().astimezone(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d")
    invitation = Invitation(
        circle_id=circle.id, person_id=fatma.id,
        date=today_str, reason="Elif has a question for you.",
        status=InvitationStatus.sent,
    )
    db.add(invitation)
    db.flush()

    # Two family questions by Elif; q1 is older.
    q1 = Question(
        circle_id=circle.id, target_person_id=fatma.id, asker_id=elif_.id,
        text="Grandma, what was school like when you were young?",
        source=QuestionSource.family,
        period=LifePeriod.childhood,
        status=QuestionStatus.waiting,
        answer=None,
        created_at=(now - timedelta(days=1)).isoformat(),
    )
    q2 = Question(
        circle_id=circle.id, target_person_id=fatma.id, asker_id=elif_.id,
        text="Did you ever meet anyone famous growing up?",
        source=QuestionSource.family,
        period=None,
        status=QuestionStatus.waiting,
        answer=None,
        created_at=(now - timedelta(hours=3)).isoformat(),
    )
    # One gap question (should come after family questions).
    q_gap = Question(
        circle_id=circle.id, target_person_id=fatma.id, asker_id=None,
        text="What do you remember about your retirement years?",
        source=QuestionSource.gap,
        period=LifePeriod.retirement,
        status=QuestionStatus.waiting,
        answer=None,
        created_at=(now - timedelta(hours=5)).isoformat(),
    )
    # One follow_up question (should come after family, before gap).
    q_follow = Question(
        circle_id=circle.id, target_person_id=fatma.id, asker_id=None,
        text="What games did you play as a child?",
        source=QuestionSource.follow_up,
        period=LifePeriod.childhood,
        status=QuestionStatus.waiting,
        answer=None,
        created_at=(now - timedelta(hours=4)).isoformat(),
    )
    db.add_all([q1, q2, q_gap, q_follow])
    db.flush()

    # Sensitive topic that overlaps with q2 ("famous" is only 6 letters, "growing"
    # is 7 letters — it will match if topic contains either).
    # We use a topic that matches q2 but NOT q1.
    sensitive = SensitiveTopic(
        circle_id=circle.id,
        text="famous people growing",
        added_by=ayse.id,
        created_at=(now - timedelta(days=2)).isoformat(),
    )
    db.add(sensitive)
    db.commit()

    w.db = db
    w.fatma    = fatma
    w.ayse     = ayse
    w.elif_    = elif_
    w.can      = can
    w.outsider = outsider
    w.circle   = circle
    w.sess     = sess
    w.story_mulberry = story_mulberry
    w.story_tailor   = story_tailor
    w.story_private  = story_private
    w.q1       = q1
    w.q2       = q2        # matches sensitive topic
    w.q_gap    = q_gap
    w.q_follow = q_follow
    return w


@pytest.fixture(scope="function")
def world(db):
    return _build_world(db)


# ---------------------------------------------------------------------------
# require_member
# ---------------------------------------------------------------------------

class TestRequireMember:
    def test_valid_member_returns_membership(self, world):
        w = world
        m = require_member(w.db, w.elif_.id, w.circle.id)
        assert m.person_id == w.elif_.id
        assert m.circle_id == w.circle.id
        assert m.role == Role.member

    def test_empty_person_id_raises(self, world):
        w = world
        with pytest.raises(ValueError, match="Person-Id"):
            require_member(w.db, "", w.circle.id)

    def test_none_person_id_raises(self, world):
        w = world
        with pytest.raises(ValueError, match="Person-Id"):
            require_member(w.db, None, w.circle.id)  # type: ignore[arg-type]

    def test_empty_circle_id_raises(self, world):
        w = world
        with pytest.raises(ValueError, match="Circle-Id"):
            require_member(w.db, w.elif_.id, "")

    def test_none_circle_id_raises(self, world):
        w = world
        with pytest.raises(ValueError, match="Circle-Id"):
            require_member(w.db, w.elif_.id, None)  # type: ignore[arg-type]

    def test_person_not_in_circle_raises(self, world):
        w = world
        with pytest.raises(ValueError, match="not a member"):
            require_member(w.db, w.outsider.id, w.circle.id)


# ---------------------------------------------------------------------------
# get_session_context
# ---------------------------------------------------------------------------

class TestGetSessionContext:
    def test_center_person_returned(self, world):
        w = world
        result = get_session_context_data(w.db, w.fatma.id, w.circle.id)
        assert result.center_person_id == w.fatma.id
        assert result.center_person_name == "Fatma"

    def test_todays_invitation_reason_returned(self, world):
        w = world
        result = get_session_context_data(w.db, w.fatma.id, w.circle.id)
        assert result.invitation_reason == "Elif has a question for you."

    def test_no_invitation_returns_none(self, world):
        w = world
        # Delete the invitation.
        inv = w.db.query(Invitation).filter(Invitation.circle_id == w.circle.id).first()
        w.db.delete(inv)
        w.db.commit()

        result = get_session_context_data(w.db, w.fatma.id, w.circle.id)
        assert result.invitation_reason is None

    def test_undelivered_reaction_has_relation_to_center(self, world):
        w = world
        result = get_session_context_data(w.db, w.fatma.id, w.circle.id)
        reaction_items = [r for r in result.undelivered_reactions
                          if r.story_title == "The Mulberry Tree"]
        assert reaction_items, "Expected at least one reaction on The Mulberry Tree"
        r = reaction_items[0]
        assert r.person_name == "Elif"
        assert r.relation_to_center == "granddaughter"

    def test_delivered_reaction_excluded(self, world):
        w = world
        result = get_session_context_data(w.db, w.fatma.id, w.circle.id)
        # "The Tailor's Shop" reaction was delivered → must not appear.
        titles = [r.story_title for r in result.undelivered_reactions]
        assert "The Tailor's Shop" not in titles

    def test_reaction_on_private_story_excluded_for_non_teller_viewer(self, world):
        """
        Add an undelivered reaction on the private story.
        A viewer who is not the teller (elif_) should not see it in the context
        because can_see() will block that story.
        """
        w = world
        # Add reaction on private story by can.
        priv_reaction = Reaction(
            story_id=w.story_private.id, person_id=w.can.id,
            emoji=Emoji.sad, delivered_to_center=False,
            created_at=now_utc().isoformat(),
        )
        w.db.add(priv_reaction)
        w.db.commit()

        # Viewer = elif_ (not the teller of the private story).
        result = get_session_context_data(w.db, w.elif_.id, w.circle.id)
        titles = [r.story_title for r in result.undelivered_reactions]
        assert "Secret" not in titles

    def test_private_story_summary_excluded_for_non_teller_viewer(self, world):
        """
        The private story's ai_summary must not appear in session summaries
        when the viewer is not the teller.
        """
        w = world
        result = get_session_context_data(w.db, w.elif_.id, w.circle.id)
        all_summaries = [
            s
            for item in result.recent_session_summaries
            for s in item.story_summaries
        ]
        assert not any("should not appear" in s for s in all_summaries)

    def test_private_story_visible_to_teller_viewer(self, world):
        """Fatma is the teller, so the private story appears in her context."""
        w = world
        result = get_session_context_data(w.db, w.fatma.id, w.circle.id)
        all_summaries = [
            s
            for item in result.recent_session_summaries
            for s in item.story_summaries
        ]
        assert any("should not appear" in s for s in all_summaries)

    def test_last_3_sessions_at_most(self, world):
        w = world
        now = now_utc()
        # Add two more finished sessions.
        for i in range(2):
            extra = OrmSession(
                circle_id=w.circle.id,
                kind=SessionKind.solo,
                started_by=SessionStart.spontaneous,
                participant_ids=[w.fatma.id],
                started_at=(now - timedelta(days=i + 2)).isoformat(),
                ended_at=(now - timedelta(days=i + 1, hours=22)).isoformat(),
            )
            w.db.add(extra)
        w.db.commit()

        result = get_session_context_data(w.db, w.fatma.id, w.circle.id)
        assert len(result.recent_session_summaries) <= 3


# ---------------------------------------------------------------------------
# get_pending_questions
# ---------------------------------------------------------------------------

class TestGetPendingQuestions:
    def test_family_before_follow_up_before_gap(self, world):
        w = world
        # q1 and q2 are family; q2 is sensitive so only q1 survives.
        # q_follow is follow_up; q_gap is gap.
        items = get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=10)
        sources = [i.source for i in items]
        # All family entries must precede all follow_up, which precede all gap.
        last_family = max((i for i, s in enumerate(sources) if s == QuestionSource.family),
                          default=-1)
        first_follow = min((i for i, s in enumerate(sources) if s == QuestionSource.follow_up),
                           default=9999)
        first_gap    = min((i for i, s in enumerate(sources) if s == QuestionSource.gap),
                           default=9999)
        assert last_family < first_follow < first_gap

    def test_oldest_first_within_same_source(self, world):
        """
        Add a second family question older than q1; it should appear before q1.
        """
        w = world
        now = now_utc()
        older_q = Question(
            circle_id=w.circle.id, target_person_id=w.fatma.id,
            asker_id=w.elif_.id,
            text="Tell me about your grandparents.",
            source=QuestionSource.family,
            period=None,
            status=QuestionStatus.waiting,
            answer=None,
            created_at=(now - timedelta(days=3)).isoformat(),
        )
        w.db.add(older_q)
        w.db.commit()

        items = get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=10)
        family_items = [i for i in items if i.source == QuestionSource.family]
        family_ids = [i.question_id for i in family_items]
        assert family_ids.index(older_q.id) < family_ids.index(w.q1.id)

    def test_sensitive_question_excluded(self, world):
        """q2 matches the sensitive topic 'famous people growing' → excluded."""
        w = world
        items = get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=10)
        ids = [i.question_id for i in items]
        assert w.q2.id not in ids

    def test_sensitive_question_status_unchanged(self, world):
        """Filtering here must not write 'filtered' status to the question."""
        w = world
        get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=10)
        q2 = w.db.get(Question, w.q2.id)
        assert q2.status == QuestionStatus.waiting

    def test_limit_respected(self, world):
        w = world
        items = get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=2)
        assert len(items) <= 2

    def test_asker_name_and_relation_included(self, world):
        w = world
        items = get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=10)
        # q1 is by Elif (granddaughter), should survive the filter.
        q1_item = next((i for i in items if i.question_id == w.q1.id), None)
        assert q1_item is not None
        assert q1_item.asker_name == "Elif"
        assert q1_item.asker_relation_to_center == "granddaughter"

    def test_agent_question_has_no_asker_name(self, world):
        w = world
        items = get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=10)
        gap_item = next((i for i in items if i.question_id == w.q_gap.id), None)
        assert gap_item is not None
        assert gap_item.asker_name is None
        assert gap_item.asker_relation_to_center is None

    def test_only_waiting_questions_returned(self, world):
        w = world
        # Mark q1 as asked.
        w.q1.status = QuestionStatus.asked
        w.db.commit()

        items = get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=10)
        ids = [i.question_id for i in items]
        assert w.q1.id not in ids

    def test_stop_words_do_not_trigger_filter(self, world):
        """
        "What did you learn from your father?" shares only stop words with
        "1972 separation from Hatice" (from, your, what) — it must NOT be filtered.

        Fix F: the old ASCII-only [a-zA-Z]{4,} regex would flag "from" and "your"
        (4 letters) but they are now in the stop-word list.
        """
        w = world
        # Replace the existing sensitive topic with one that tests stop-word boundary.
        for st in w.db.query(SensitiveTopic).all():
            w.db.delete(st)
        now = now_utc()
        w.db.add(SensitiveTopic(
            circle_id=w.circle.id,
            text="1972 separation from Hatice",
            added_by=w.ayse.id,
            created_at=now.isoformat(),
        ))
        # Add the question that should survive.
        safe_q = Question(
            circle_id=w.circle.id, target_person_id=w.fatma.id,
            asker_id=w.elif_.id,
            text="What did you learn from your father?",
            source=QuestionSource.family, period=None,
            status=QuestionStatus.waiting, answer=None,
            created_at=now.isoformat(),
        )
        w.db.add(safe_q)
        w.db.commit()

        items = get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=10)
        ids = [i.question_id for i in items]
        assert safe_q.id in ids, "Stop-word-only overlap must not trigger the filter"

    def test_name_overlap_triggers_filter(self, world):
        """
        "Why did Hatice leave?" shares the name "Hatice" (not a stop word, 6 letters)
        with the topic "1972 separation from Hatice" — it MUST be filtered.
        """
        w = world
        for st in w.db.query(SensitiveTopic).all():
            w.db.delete(st)
        now = now_utc()
        w.db.add(SensitiveTopic(
            circle_id=w.circle.id,
            text="1972 separation from Hatice",
            added_by=w.ayse.id,
            created_at=now.isoformat(),
        ))
        sensitive_q = Question(
            circle_id=w.circle.id, target_person_id=w.fatma.id,
            asker_id=w.elif_.id,
            text="Why did Hatice leave?",
            source=QuestionSource.family, period=None,
            status=QuestionStatus.waiting, answer=None,
            created_at=now.isoformat(),
        )
        w.db.add(sensitive_q)
        w.db.commit()

        items = get_pending_questions_data(w.db, w.fatma.id, w.circle.id, limit=10)
        ids = [i.question_id for i in items]
        assert sensitive_q.id not in ids, "Name overlap must trigger the filter"


# ---------------------------------------------------------------------------
# mark_question_asked
# ---------------------------------------------------------------------------

class TestMarkQuestionAsked:
    def test_happy_path(self, world):
        w = world
        mark_question_asked_data(w.db, w.fatma.id, w.circle.id, w.q1.id)
        w.db.commit()
        q = w.db.get(Question, w.q1.id)
        assert q.status == QuestionStatus.asked

    def test_question_not_found_raises(self, world):
        w = world
        with pytest.raises(ValueError, match="not found"):
            mark_question_asked_data(
                w.db, w.fatma.id, w.circle.id,
                "00000000-0000-0000-0000-000000000000",
            )

    def test_wrong_circle_raises(self, world):
        w = world
        # Create a second circle.
        other_circle = Circle(
            name="Other Circle",
            center_person_id=w.fatma.id,
            status=CircleStatus.active,
            chat_time="09:00",
            timezone="Europe/Istanbul",
        )
        w.db.add(other_circle)
        w.db.flush()

        with pytest.raises(ValueError, match="does not belong"):
            mark_question_asked_data(
                w.db, w.fatma.id, other_circle.id, w.q1.id
            )

    def test_already_asked_raises(self, world):
        w = world
        w.q1.status = QuestionStatus.asked
        w.db.commit()

        with pytest.raises(ValueError, match="waiting"):
            mark_question_asked_data(w.db, w.fatma.id, w.circle.id, w.q1.id)

    def test_answered_question_raises(self, world):
        w = world
        w.q1.status = QuestionStatus.answered
        w.db.commit()

        with pytest.raises(ValueError, match="waiting"):
            mark_question_asked_data(w.db, w.fatma.id, w.circle.id, w.q1.id)
