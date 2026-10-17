"""
Tests for core.services.chat_tools.

Uses the in-memory world from test_archive_tools: Fatma (center), Elif
(member), a stranger in another circle, an ended session with segments
  0–10 000 Fatma (public) · 10 000–12 000 agent · 12 000–20 000 Fatma (PRIVATE)
  20 000–30 000 Fatma (public)

Coverage:
  mark_private_data              — marks overlapping segments; participant only;
                                   needs a session; same circle; rejects empty ranges
  mark_reactions_delivered_data  — marks only undelivered reactions of those stories
  set_story_access_data          — teller only; private / circle only; same circle
  search_archive_data            — keyword match; can_see() filter; person / period
                                   filters; no transcript text in results
"""

from __future__ import annotations

import pytest

from core.clock import now_utc
from core.enums import AccessType, Emoji, StoryStatus
from core.models import Reaction, Segment, Story
from core.services.archive_tools import save_story_data
from core.services.chat_tools import (
    mark_private_data,
    mark_reactions_delivered_data,
    search_archive_data,
    set_story_access_data,
)
from tests.test_archive_tools import db, w  # noqa: F401  (fixtures)


def _story(w, title, summary, start=0, end=10_000, teller=None, period="childhood", publish=True):
    teller = teller or w.fatma
    story_id = save_story_data(
        w.db, teller.id, w.circle.id, title=title, summary=summary, teller_id=teller.id,
        subjects=[{"person_id": teller.id, "period": period}],
        sources=[{"session_id": w.sess.id, "start_ms": start, "end_ms": end}],
    )
    if publish:
        w.db.get(Story, story_id).status = StoryStatus.published
    w.db.commit()
    return story_id


# ---------------------------------------------------------------------------
# mark_private
# ---------------------------------------------------------------------------

def test_mark_private_marks_overlapping_segments(w):
    ids = mark_private_data(w.db, w.fatma.id, w.circle.id, w.sess.id, 0, 12_000)
    w.db.commit()
    assert set(ids) == {w.seg_a.id, w.seg_agent.id}
    assert w.db.get(Segment, w.seg_a.id).is_private
    assert w.db.get(Segment, w.seg_agent.id).is_private      # the agent's reply too
    assert not w.db.get(Segment, w.seg_b.id).is_private      # boundary at 20 000 untouched


def test_mark_private_only_by_a_participant(w):
    with pytest.raises(ValueError, match="participant"):
        mark_private_data(w.db, w.elif_.id, w.circle.id, w.sess.id, 0, 10_000)
    assert not w.db.get(Segment, w.seg_a.id).is_private


@pytest.mark.parametrize("session,start,end,error", [
    ("", 0, 10_000, "X-Evoca-Session-Id"),
    ("other", 0, 10, "not found in this circle"),
    ("sess", 5_000, 5_000, "Invalid range"),
    ("sess", 40_000, 50_000, "No speech"),
])
def test_mark_private_rejects(w, session, start, end, error):
    session_id = {"": "", "other": w.other_sess.id, "sess": w.sess.id}[session]
    with pytest.raises(ValueError, match=error):
        mark_private_data(w.db, w.fatma.id, w.circle.id, session_id, start, end)


# ---------------------------------------------------------------------------
# mark_reactions_delivered
# ---------------------------------------------------------------------------

def test_mark_reactions_delivered(w):
    story_id = _story(w, "The River", "Fatma remembers the river.")
    other_id = _story(w, "The Boat", "Fatma remembers the boat.", start=20_000, end=30_000)
    for sid in (story_id, other_id):
        w.db.add(Reaction(story_id=sid, person_id=w.elif_.id, emoji=Emoji.heart,
                          delivered_to_center=False, created_at=now_utc().isoformat()))
    w.db.commit()

    assert mark_reactions_delivered_data(w.db, w.fatma.id, w.circle.id, [story_id]) == 1
    w.db.commit()
    assert w.db.get(Reaction, (story_id, w.elif_.id, Emoji.heart.value)).delivered_to_center
    assert not w.db.get(Reaction, (other_id, w.elif_.id, Emoji.heart.value)).delivered_to_center
    assert mark_reactions_delivered_data(w.db, w.fatma.id, w.circle.id, [story_id]) == 0


def test_mark_reactions_delivered_rejects_unknown_story(w):
    with pytest.raises(ValueError, match="not found"):
        mark_reactions_delivered_data(w.db, w.fatma.id, w.circle.id, ["nope"])


# ---------------------------------------------------------------------------
# set_story_access
# ---------------------------------------------------------------------------

def test_set_story_access_private_and_back(w):
    story_id = _story(w, "The River", "Fatma remembers the river.")
    set_story_access_data(w.db, w.fatma.id, w.circle.id, story_id, "private")
    assert w.db.get(Story, story_id).access == {"type": AccessType.private.value, "person_ids": []}
    set_story_access_data(w.db, w.fatma.id, w.circle.id, story_id, "circle")
    assert w.db.get(Story, story_id).access["type"] == AccessType.circle.value


def test_set_story_access_rules(w):
    story_id = _story(w, "The River", "Fatma remembers the river.")
    with pytest.raises(ValueError, match="Only the person who told"):
        set_story_access_data(w.db, w.elif_.id, w.circle.id, story_id, "private")
    with pytest.raises(ValueError, match="'private' or 'circle'"):
        set_story_access_data(w.db, w.fatma.id, w.circle.id, story_id, "selected")
    with pytest.raises(ValueError, match="not found"):
        set_story_access_data(w.db, w.fatma.id, w.circle.id, "nope", "private")


# ---------------------------------------------------------------------------
# search_archive
# ---------------------------------------------------------------------------

def test_search_archive_matches_keywords_best_first(w):
    river = _story(w, "Fishing in the River", "Fatma remembers fishing in the river every summer.")
    _story(w, "The Wedding", "Fatma remembers her sister's wedding.", start=20_000, end=30_000)
    results = search_archive_data(w.db, w.fatma.id, w.circle.id, "fishing river summer")
    assert [r["story_id"] for r in results] == [river]
    assert set(results[0]) == {"story_id", "title", "ai_summary", "place", "periods", "sources"}
    assert search_archive_data(w.db, w.fatma.id, w.circle.id, "tractor") == []


def test_search_archive_filters_by_can_see(w):
    secret = _story(w, "Secret Garden", "Fatma remembers a garden.")
    w.db.get(Story, secret).access = {"type": AccessType.private.value, "person_ids": []}
    pending = _story(w, "Pending Garden", "Fatma remembers another garden.",
                     start=20_000, end=30_000, publish=False)
    w.db.commit()

    for_fatma = {r["story_id"] for r in search_archive_data(w.db, w.fatma.id, w.circle.id, "garden")}
    for_elif = {r["story_id"] for r in search_archive_data(w.db, w.elif_.id, w.circle.id, "garden")}
    assert for_fatma == {secret, pending}          # teller sees private; center sees pending
    assert for_elif == set()                       # member: neither


def test_search_archive_person_and_period_filters(w):
    young = _story(w, "Dancing", "Fatma remembers dancing.", period="youth")
    _story(w, "Dancing Again", "Fatma remembers dancing at a wedding.",
           start=20_000, end=30_000, period="midlife")
    assert [r["story_id"] for r in search_archive_data(
        w.db, w.fatma.id, w.circle.id, "dancing", period="youth")] == [young]
    assert search_archive_data(w.db, w.fatma.id, w.circle.id, "dancing", person_id=w.elif_.id) == []
