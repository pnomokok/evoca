"""
Tests for core.services.publisher and core.services.feed.

Uses the in-memory world from test_archive_tools (Fatma = center, Elif =
member who asked "Where did you grow up?", an ended session with a public
segment at 0-10000).

Coverage:
  publish_due_stories  — publishes only pending stories whose publish_at has
                         passed; uses now_utc() so DEMO_NOW moves time; leaves
                         hidden and future stories alone
  build_feed           — shape matches GET_feed.json; question_answered only
                         for the asker and only once the asker can_see() the
                         story (pending / private / hidden keep it back);
                         a declined question looks exactly like an unanswered
                         one (it never appears); story_published filtered by
                         can_see(); newest first
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.access import can_see
from core.clock import now_utc
from core.enums import AccessType, QuestionStatus, Role, StoryStatus
from core.models import Membership, Person, Question, Story
from core.services.archive_tools import mark_question_declined_data, record_answer_data, save_story_data
from core.services.feed import build_feed
from core.services.publisher import publish_due_stories
from tests.test_archive_tools import db, w  # noqa: F401  (fixtures)


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


def _answer(w, story_id):
    record_answer_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id, story_id, 0, 10_000)
    w.db.commit()


def _demo_now(monkeypatch, delta: timedelta):
    monkeypatch.setenv("DEMO_NOW", (datetime.now().astimezone() + delta).isoformat())


def _types(feed):
    return [item["type"] for item in feed["items"]]


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------

def test_publisher_waits_24_hours(w, monkeypatch):
    story_id = _save(w)                                     # publish_at = now + 24 h
    assert publish_due_stories(w.db) == []
    assert w.db.get(Story, story_id).status == StoryStatus.pending

    _demo_now(monkeypatch, timedelta(hours=23, minutes=59))
    assert publish_due_stories(w.db) == []

    _demo_now(monkeypatch, timedelta(hours=24, minutes=1))
    assert publish_due_stories(w.db) == [story_id]
    assert w.db.get(Story, story_id).status == StoryStatus.published
    assert publish_due_stories(w.db) == []                  # idempotent


def test_publisher_never_publishes_hidden_stories(w, monkeypatch):
    story_id = _save(w)
    w.db.get(Story, story_id).status = StoryStatus.hidden
    w.db.commit()
    _demo_now(monkeypatch, timedelta(days=2))
    assert publish_due_stories(w.db) == []
    assert w.db.get(Story, story_id).status == StoryStatus.hidden


# ---------------------------------------------------------------------------
# Feed: question_answered
# ---------------------------------------------------------------------------

def test_answer_appears_for_asker_after_publishing(w, monkeypatch):
    story_id = _save(w)
    _answer(w, story_id)

    # Pending: Elif (a member) cannot see the story yet, so no answer card.
    assert "question_answered" not in _types(build_feed(w.db, w.elif_.id, w.circle.id))

    _demo_now(monkeypatch, timedelta(hours=25))
    publish_due_stories(w.db)
    feed = build_feed(w.db, w.elif_.id, w.circle.id)

    card = [i for i in feed["items"] if i["type"] == "question_answered"][0]
    story = w.db.get(Story, story_id)
    assert card == {
        "type": "question_answered",
        "created_at": story.publish_at,
        "question": {"id": w.q_asked.id, "text": "Where did you grow up?", "asker_id": w.elif_.id},
        "answer": {
            "story_id": story_id,
            "story_title": "By the River",
            "teller": {"id": w.fatma.id, "name": "Fatma", "relation_to_center": None},
            "session_id": w.sess.id,
            "start_ms": 0,
            "end_ms": 10_000,
            "audio_url": f"/api/audio/{w.sess.id}?start=0&end=10000",
        },
    }


def test_answer_card_only_for_the_asker(w, monkeypatch):
    can = Person(name="Can", birth_year=2006, language="en")
    w.db.add(can); w.db.flush()
    w.db.add(Membership(person_id=can.id, circle_id=w.circle.id, role=Role.member,
                        relation_to_center="grandson"))
    w.db.commit()
    _answer(w, _save(w))
    _demo_now(monkeypatch, timedelta(hours=25))
    publish_due_stories(w.db)

    assert _types(build_feed(w.db, can.id, w.circle.id)) == ["story_published"]
    assert "question_answered" in _types(build_feed(w.db, w.elif_.id, w.circle.id))


@pytest.mark.parametrize("status,access_type", [
    (StoryStatus.published, AccessType.private),
    (StoryStatus.hidden, AccessType.circle),
])
def test_answer_hidden_when_story_not_visible(w, status, access_type):
    story_id = _save(w)
    _answer(w, story_id)
    story = w.db.get(Story, story_id)
    story.status = status
    story.access = {"type": access_type, "person_ids": []}
    w.db.commit()
    assert not can_see(w.db, w.elif_.id, story)
    assert build_feed(w.db, w.elif_.id, w.circle.id) == {"items": []}


def test_declined_question_looks_unanswered(w, monkeypatch):
    # Another story in the feed, so the feed is not trivially empty.
    _save(w, title="The Fishing Boat")
    _demo_now(monkeypatch, timedelta(hours=25))
    publish_due_stories(w.db)

    unanswered_feed = build_feed(w.db, w.elif_.id, w.circle.id)      # q_asked still "asked"
    mark_question_declined_data(w.db, w.fatma.id, w.circle.id, w.q_asked.id, w.sess.id, 20_000, 30_000)
    w.db.commit()
    assert w.db.get(Question, w.q_asked.id).status == QuestionStatus.declined
    declined_feed = build_feed(w.db, w.elif_.id, w.circle.id)

    assert declined_feed == unanswered_feed
    assert "declined" not in str(declined_feed)
    assert w.q_asked.id not in str(declined_feed)


# ---------------------------------------------------------------------------
# Feed: story_published
# ---------------------------------------------------------------------------

def test_story_published_card_and_filters(w, monkeypatch):
    visible = _save(w, title="By the River")
    private = _save(w, title="A Secret", sources=[{"session_id": w.sess.id, "start_ms": 0, "end_ms": 5_000}])
    w.db.get(Story, private).access = {"type": AccessType.private, "person_ids": []}
    w.db.commit()
    _demo_now(monkeypatch, timedelta(hours=25))
    publish_due_stories(w.db)
    still_pending = _save(w, title="Not Yet")   # created at DEMO_NOW, publishes a day later

    feed = build_feed(w.db, w.elif_.id, w.circle.id)
    assert [i["story"]["title"] for i in feed["items"]] == ["By the River"]
    card = feed["items"][0]
    assert card["story"]["subjects"] == [
        {"person_id": w.fatma.id, "period": "childhood", "period_source": "ai"}
    ]
    assert card["story"]["duration_ms"] == 10_000
    assert card["story"]["teller"]["name"] == "Fatma"

    # The teller sees her own private story; nobody sees the pending one as published.
    titles_for_fatma = [i["story"]["title"] for i in build_feed(w.db, w.fatma.id, w.circle.id)["items"]]
    assert sorted(titles_for_fatma) == ["A Secret", "By the River"]
    assert "Not Yet" not in titles_for_fatma and still_pending


def test_feed_is_newest_first(w, monkeypatch):
    _demo_now(monkeypatch, timedelta(hours=0))
    first = _save(w, title="First")
    _demo_now(monkeypatch, timedelta(hours=1))
    second = _save(w, title="Second")
    _demo_now(monkeypatch, timedelta(hours=26))
    publish_due_stories(w.db)
    titles = [i["story"]["title"] for i in build_feed(w.db, w.elif_.id, w.circle.id)["items"]]
    assert titles == ["Second", "First"] and first and second
