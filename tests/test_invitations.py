"""
Invitation scheduler (core/services/invitations.py).

Circle "Test Family": Fatma (center), Elif and Ali (members), chat_time 10:00
Europe/Istanbul (UTC+3), so the light may go on from 07:00 UTC. The clock is
set with DEMO_NOW.

Coverage
--------
- Created after chat_time, not before; the local date across the timezone
  boundary (23:30 UTC is already the next day in Istanbul).
- One per circle per day: two passes, and two concurrent passes on a file DB.
- Skipped when the center already had a session that local day or one is live;
  a session the previous local day or a family member's panel recording does
  not count.
- Reason priority: reactions (one person / several), family question,
  follow_up or gap question, default. Never question text; filtered, declined
  and asked questions, and waiting ones matching a sensitive topic, do not count.
- GET /api/device/invitation is active after a pass; DEMO_NOW moves the clock.
- Opening context: session/start accepts the invitation, and the opening turn's
  get_session_context still carries its reason.
- add_missing_indexes adds the (circle_id, date) unique index to an older
  database, idempotently, and never deletes rows.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker

import core.services.invitations as inv_svc
from core.clock import now_utc
from core.db import add_missing_indexes
from core.enums import (
    CircleStatus, Emoji, InvitationStatus, QuestionSource, QuestionStatus, Role,
    SessionKind, SessionStart, StoryKind, StoryStatus, AccessType,
)
from core.models import (
    Base, Circle, Invitation, Membership, Person, Question, Reaction, SensitiveTopic,
    Session as OrmSession, Story,
)
from core.services.invitations import (
    REASON_AGENT_QUESTION, REASON_DEFAULT, REASON_REACTION_MANY, run_invitations,
)
from tests.test_api import _client, _set_llm_script, anyio_backend, test_app  # noqa: F401
from tests.test_archive_tools import db  # noqa: F401  (fixture)

DAY = "2026-10-18"
BEFORE = f"{DAY}T06:59:00+00:00"     # 09:59 in Istanbul
AFTER = f"{DAY}T07:05:00+00:00"      # 10:05 in Istanbul


class _World:
    pass


def _build(db) -> _World:
    w = _World()
    w.db = db
    w.fatma = Person(name="Fatma Yilmaz", birth_year=1948, language="en")
    w.elif_ = Person(name="Elif Yilmaz", birth_year=2003, language="en")
    w.ali = Person(name="Ali Yilmaz", birth_year=2005, language="en")
    db.add_all([w.fatma, w.elif_, w.ali]); db.flush()
    w.circle = Circle(name="Test Family", center_person_id=w.fatma.id, status=CircleStatus.active,
                      chat_time="10:00", timezone="Europe/Istanbul")
    db.add(w.circle); db.flush()
    db.add_all([
        Membership(person_id=w.fatma.id, circle_id=w.circle.id, role=Role.center),
        Membership(person_id=w.elif_.id, circle_id=w.circle.id, role=Role.member,
                   relation_to_center="granddaughter"),
        Membership(person_id=w.ali.id, circle_id=w.circle.id, role=Role.member,
                   relation_to_center="grandson"),
    ])
    db.commit()
    return w


@pytest.fixture
def w(db):
    return _build(db)


def _clock(monkeypatch, iso):
    monkeypatch.setenv("DEMO_NOW", iso)


def _invitations(w):
    w.db.expire_all()
    return w.db.query(Invitation).all()


def _question(w, text_, source=QuestionSource.family, status=QuestionStatus.waiting, asker=None):
    q = Question(circle_id=w.circle.id, target_person_id=w.fatma.id,
                 asker_id=(asker or w.elif_).id if source == QuestionSource.family else None,
                 text=text_, source=source, status=status,
                 created_at=(now_utc() - timedelta(days=1)).isoformat())
    w.db.add(q); w.db.commit()
    return q


def _react(w, person, title="The Umbrella"):
    story = Story(circle_id=w.circle.id, teller_id=w.fatma.id, kind=StoryKind.original,
                  title=title, sources=[], access={"type": AccessType.circle, "person_ids": []},
                  status=StoryStatus.published, publish_at=now_utc().isoformat(),
                  created_at=now_utc().isoformat())
    w.db.add(story); w.db.flush()
    w.db.add(Reaction(story_id=story.id, person_id=person.id, emoji=Emoji.laugh,
                      delivered_to_center=False, created_at=now_utc().isoformat()))
    w.db.commit()


def _session(w, started_at, ended_at=None, by=SessionStart.spontaneous, participants=None):
    w.db.add(OrmSession(circle_id=w.circle.id, kind=SessionKind.solo, started_by=by,
                        participant_ids=participants or [w.fatma.id],
                        started_at=started_at, ended_at=ended_at))
    w.db.commit()


def _reason(w, monkeypatch):
    _clock(monkeypatch, AFTER)
    run_invitations(w.db)
    return _invitations(w)[0].reason


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

def test_created_after_chat_time_not_before(w, monkeypatch):
    _clock(monkeypatch, BEFORE)
    assert run_invitations(w.db) == []
    _clock(monkeypatch, AFTER)
    created = run_invitations(w.db)
    [inv] = _invitations(w)
    assert created == [inv.id]
    assert (inv.date, inv.status, inv.person_id) == (DAY, InvitationStatus.sent, w.fatma.id)


def test_local_date_across_the_timezone_boundary(w, monkeypatch):
    w.circle.chat_time = "02:00"
    w.db.commit()
    _clock(monkeypatch, f"{DAY}T23:30:00+00:00")      # 02:30 on the 19th in Istanbul
    run_invitations(w.db)
    [inv] = _invitations(w)
    assert inv.date == "2026-10-19"


def test_not_created_for_a_memorial_circle(w, monkeypatch):
    w.circle.status = CircleStatus.memorial
    w.db.commit()
    _clock(monkeypatch, AFTER)
    assert run_invitations(w.db) == []


def test_two_passes_create_one(w, monkeypatch):
    _clock(monkeypatch, AFTER)
    assert len(run_invitations(w.db)) == 1
    _clock(monkeypatch, f"{DAY}T20:00:00+00:00")
    assert run_invitations(w.db) == []
    assert len(_invitations(w)) == 1


def test_demo_now_moves_the_clock_to_the_next_day(w, monkeypatch):
    _clock(monkeypatch, AFTER)
    run_invitations(w.db)
    _clock(monkeypatch, "2026-10-19T07:05:00+00:00")
    run_invitations(w.db)
    assert sorted(i.date for i in _invitations(w)) == [DAY, "2026-10-19"]


def test_concurrent_passes_create_one(tmp_path, monkeypatch):
    eng = create_engine(f"sqlite:///{tmp_path / 'race.db'}",
                        connect_args={"check_same_thread": False, "timeout": 10})
    Base.metadata.create_all(bind=eng)
    Sess = sessionmaker(bind=eng, autocommit=False, autoflush=False, expire_on_commit=False)
    with Sess() as setup:
        _build(setup)
    _clock(monkeypatch, AFTER)

    # Both passes see "no invitation yet" before either inserts.
    barrier = threading.Barrier(2, timeout=10)
    original = inv_svc._has_invitation

    def racing_check(db_, circle_id, date):
        found = original(db_, circle_id, date)
        barrier.wait()
        return found

    monkeypatch.setattr(inv_svc, "_has_invitation", racing_check)
    results: list[list[str]] = []
    errors: list[BaseException] = []

    def one_pass():
        try:
            with Sess() as s:
                results.append(run_invitations(s))
        except BaseException as exc:      # noqa: BLE001  (reported below)
            errors.append(exc)

    threads = [threading.Thread(target=one_pass) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert sorted(len(r) for r in results) == [0, 1]
    with Sess() as s:
        assert s.query(Invitation).count() == 1
    eng.dispose()


# ---------------------------------------------------------------------------
# Skip rule
# ---------------------------------------------------------------------------

def test_skipped_when_the_center_spoke_earlier_that_day(w, monkeypatch):
    _session(w, f"{DAY}T05:00:00+00:00", f"{DAY}T05:20:00+00:00")     # 08:00 local
    _clock(monkeypatch, AFTER)
    run_invitations(w.db)
    [inv] = _invitations(w)
    assert inv.status == InvitationStatus.skipped and inv.date == DAY


def test_skipped_when_a_session_is_live(w, monkeypatch):
    _session(w, "2026-10-17T12:00:00+00:00", ended_at=None)
    _clock(monkeypatch, AFTER)
    run_invitations(w.db)
    assert _invitations(w)[0].status == InvitationStatus.skipped


def test_sent_after_a_session_the_previous_local_day_or_a_panel_recording(w, monkeypatch):
    _session(w, "2026-10-17T20:00:00+00:00", "2026-10-17T20:30:00+00:00")   # 23:00 on the 17th
    _session(w, f"{DAY}T05:00:00+00:00", f"{DAY}T05:01:00+00:00",
             by=SessionStart.panel_recording, participants=[w.elif_.id])
    _clock(monkeypatch, AFTER)
    run_invitations(w.db)
    assert _invitations(w)[0].status == InvitationStatus.sent


# ---------------------------------------------------------------------------
# Reason
# ---------------------------------------------------------------------------

def test_reason_one_reactor_beats_questions(w, monkeypatch):
    _question(w, "What was your first job?")
    _react(w, w.elif_)
    assert _reason(w, monkeypatch) == "Elif reacted to your story"


def test_reason_several_reactors(w, monkeypatch):
    _react(w, w.elif_)
    _react(w, w.ali, title="The Bus")
    assert _reason(w, monkeypatch) == REASON_REACTION_MANY


def test_reason_family_question_beats_agent_question(w, monkeypatch):
    _question(w, "What did you see on the bus?", source=QuestionSource.follow_up)
    _question(w, "What was your first job at the flour mill?", asker=w.ali)
    reason = _reason(w, monkeypatch)
    assert reason == "Ali has a question for you"
    for word in ("job", "flour", "mill", "bus"):
        assert word not in reason.lower()


@pytest.mark.parametrize("source", [QuestionSource.follow_up, QuestionSource.gap])
def test_reason_agent_question(w, monkeypatch, source):
    _question(w, "What was the umbrella like?", source=source)
    reason = _reason(w, monkeypatch)
    assert reason == REASON_AGENT_QUESTION and "umbrella" not in reason.lower()


def test_reason_default(w, monkeypatch):
    assert _reason(w, monkeypatch) == REASON_DEFAULT


@pytest.mark.parametrize("status", [QuestionStatus.filtered, QuestionStatus.declined,
                                    QuestionStatus.asked, QuestionStatus.answered])
def test_questions_that_are_not_waiting_never_give_a_reason(w, monkeypatch, status):
    _question(w, "Why did Hatice leave?", status=status)
    _question(w, "What happened in Germany?", source=QuestionSource.follow_up, status=status)
    assert _reason(w, monkeypatch) == REASON_DEFAULT


def test_waiting_question_on_a_sensitive_topic_gives_no_reason(w, monkeypatch):
    w.db.add(SensitiveTopic(circle_id=w.circle.id, text="Hatice", added_by=w.elif_.id))
    w.db.commit()
    _question(w, "Why did Hatice leave?")
    assert _reason(w, monkeypatch) == REASON_DEFAULT


# ---------------------------------------------------------------------------
# Device endpoint and opening context
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_device_invitation_is_active_after_a_pass(test_app, monkeypatch):
    app, db, fatma, *_ = test_app
    db.query(Invitation).delete()           # the fixture's own invitation
    db.commit()
    _clock(monkeypatch, "2026-10-20T08:00:00+00:00")   # 11:00 in Istanbul
    async with _client(app) as c:
        before = (await c.get("/api/device/invitation", headers={"x-person-id": fatma.id})).json()
        run_invitations(db)
        after = (await c.get("/api/device/invitation", headers={"x-person-id": fatma.id})).json()
    assert {k: before[k] for k in ("active", "invitation")} == {"active": False, "invitation": None}
    for body in (before, after):            # the device clock follows DEMO_NOW
        assert body["now"].startswith("2026-10-20T08:00")
    assert after["active"] is True
    assert after["invitation"]["date"] == "2026-10-20"
    assert after["invitation"]["reason"] == "Elif has a question for you"


@pytest.mark.anyio
async def test_opening_context_has_the_accepted_invitations_reason(test_app):
    app, db, fatma, elif_, circle, *_ = test_app
    inv = db.query(Invitation).one()
    inv.date = now_utc().astimezone(ZoneInfo(circle.timezone)).strftime("%Y-%m-%d")
    db.commit()
    _set_llm_script(test_app, ["Hello, Fatma! Elif has a question."])   # the context is prefetched
    async with _client(app) as c:
        r = await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Invitation, inv.id).status == InvitationStatus.accepted
    llm = test_app[7][0]
    contexts = [
        block["toolResult"]["content"][0]["json"]
        for msg in llm.calls[-1]["messages"] if msg["role"] == "user"
        for block in msg["content"]
        if "toolResult" in block and block["toolResult"]["toolUseId"] == "prefetch_get_session_context"
    ]
    assert [c["invitation_reason"] for c in contexts] == ["Elif has a question."]


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def _old_db(tmp_path, rows):
    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    Base.metadata.create_all(bind=eng)
    with eng.begin() as conn:
        conn.execute(text("DROP INDEX uq_invitation_circle_date"))
        for i, date in enumerate(rows):
            conn.execute(text(
                "INSERT INTO invitation (id, circle_id, person_id, date, reason, status) "
                f"VALUES ('i{i}', 'c1', 'p1', '{date}', 'r', 'sent')"
            ))
    return eng


def _index_names(eng):
    return {ix["name"] for ix in inspect(eng).get_indexes("invitation")}


def test_unique_index_is_added_to_an_old_database(tmp_path):
    eng = _old_db(tmp_path, [DAY])
    assert add_missing_indexes(eng) == ["uq_invitation_circle_date"]
    assert add_missing_indexes(eng) == []
    assert "uq_invitation_circle_date" in _index_names(eng)
    eng.dispose()


def test_duplicate_rows_keep_the_index_off_and_are_not_deleted(tmp_path):
    eng = _old_db(tmp_path, [DAY, DAY])
    assert add_missing_indexes(eng) == []
    with eng.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM invitation")).scalar() == 2
    eng.dispose()


# ---------------------------------------------------------------------------
# Same rule as the opening: reactions on a story that touches a sensitive topic
# ---------------------------------------------------------------------------

def test_reaction_on_a_sensitive_story_does_not_count(w, monkeypatch):
    """The opening will not tell that reaction (get_session_context), so the device
    must not say "Elif reacted to your story", and Elif's waiting question wins."""
    from core.services.session_tools import get_session_context_data
    w.db.add(SensitiveTopic(circle_id=w.circle.id, text="the umbrella accident", added_by=w.fatma.id))
    w.db.commit()
    _react(w, w.elif_, title="The Umbrella")
    _question(w, "What was your first job?")
    assert get_session_context_data(w.db, w.fatma.id, w.circle.id).undelivered_reactions == []
    assert _reason(w, monkeypatch) == "Elif has a question for you"


def test_reaction_on_another_story_still_counts_next_to_a_sensitive_one(w, monkeypatch):
    w.db.add(SensitiveTopic(circle_id=w.circle.id, text="the umbrella accident", added_by=w.fatma.id))
    w.db.commit()
    _react(w, w.elif_, title="The Umbrella")
    _react(w, w.elif_, title="Picking Cherries")
    assert _reason(w, monkeypatch) == "Elif reacted to your story"
