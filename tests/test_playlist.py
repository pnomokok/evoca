"""
Playing stories by voice (ARCHITECTURE.md A5): the get_linked_playlist tool
(core/services/chat_tools.py) and the device turn's playlist card
(server/routers/device.py).

Uses the world fixture from tests/test_panel_stories.py: Fatma (the center)
told "The Mulberry Tree", whose source spans a private part of her own session.

Coverage: the tool returns only stories the center can see, in period order,
with private parts cut out and at most 5 items; the model's result has no
audio ranges (the card rebuilds them); an invisible story gives the
same error as a missing one; the playlist card appears only in the turn where
get_linked_playlist ran; every card url passes GET /api/audio for the center;
another member's private linked story never appears anywhere in the response.
"""

from __future__ import annotations

import json
import wave

import pytest

from core.enums import AccessType, StoryStatus
from core.models import Circle, Story
from core.services.chat_tools import PLAYLIST_LIMIT, get_linked_playlist_data, playlist_ranges
from tests.test_api import _client, _make_silent_pcm, _make_wav_bytes, _set_llm_script, anyio_backend, test_app  # noqa: F401
from tests.test_chat_agent import _tool_use
from tests.test_panel_stories import SECRET, _link, _session, _story, world  # noqa: F401

ITEM_KEYS = {"story_id", "title", "teller", "period"}


def _ali_stories(world):
    """Stories by Ali linked to the mulberry story: two visible to Fatma, two not."""
    db, fatma, ali, circle = world["db"], world["fatma"], world["ali"], world["circle"]
    sess = _session(db, circle, ali)
    with wave.open(str(world["audio_dir"] / f"{sess.id}.wav"), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16_000)
        wf.writeframes(_make_silent_pcm(3000))
    src = [{"session_id": sess.id, "start_ms": 0, "end_ms": 3000}]
    earlier = _story(db, circle, ali, [(fatma, "childhood")], sources=src, title="Earlier",
                     created_offset_h=-10)
    later = _story(db, circle, ali, [(ali, "midlife")], sources=src, title="Workshop")
    secret = _story(db, circle, ali, [(ali, "youth")], sources=src, access=AccessType.private,
                    title="SecretTrip")
    hidden = _story(db, circle, ali, [(ali, "youth")], sources=src, status=StoryStatus.hidden,
                    title="HiddenTrip")
    m = world["mulberry"]
    for other in (later, earlier, secret, hidden):
        _link(db, m, other)
    return dict(sess=sess, earlier=earlier, later=later, secret=secret, hidden=hidden)


@pytest.fixture
def linked(world, test_app):
    world["audio_dir"] = test_app[-1]
    return {**world, **_ali_stories(world)}


# ---------------------------------------------------------------------------
# get_linked_playlist
# ---------------------------------------------------------------------------

def test_tool_returns_visible_stories_in_period_order_with_private_parts_cut(linked):
    w = linked
    args = (w["db"], w["fatma"].id, w["circle"].id, w["mulberry"].id)
    # The ranges (card side): each source is cut around its private part; capped at 5.
    ranges = playlist_ranges(*args)
    assert [r["story_id"] for r in ranges] == [w["earlier"].id, w["earlier"].id, w["mulberry"].id,
                                               w["mulberry"].id, w["later"].id]
    for r in ranges:   # never a private segment, in either session
        assert r["end_ms"] <= 1000 or r["start_ms"] >= 2000
    # What the model sees: one item per story, same order.
    out = get_linked_playlist_data(*args)
    assert out["story_id"] == w["mulberry"].id
    items = out["items"]
    assert [i["story_id"] for i in items] == [w["earlier"].id, w["mulberry"].id, w["later"].id]
    assert [i["teller"] for i in items] == ["Ali", "Fatma", "Ali"]
    assert [i["period"] for i in items] == ["childhood", "childhood", "midlife"]
    text = json.dumps(out) + json.dumps(ranges, default=str)
    for s in (w["secret"], w["hidden"]):
        assert s.id not in text and s.title not in text
    assert SECRET not in text


def test_tool_result_for_the_model_has_no_audio_ranges(linked):
    w = linked
    out = get_linked_playlist_data(w["db"], w["fatma"].id, w["circle"].id, w["mulberry"].id)
    assert out["items"] and all(set(i) == ITEM_KEYS for i in out["items"])
    text = json.dumps(out)
    for key in ("session_id", "start_ms", "end_ms", "url", w["sess"].id):
        assert key not in text


def test_cap_keeps_the_requested_story_when_linked_ones_come_first(linked):
    w = linked
    db, fatma, circle = w["db"], w["fatma"], w["circle"]
    src = w["later"].sources
    for n in range(2):   # two more childhood stories linked to "Workshop" (midlife)
        _link(db, w["later"], _story(db, circle, w["ali"], [(fatma, "childhood")], sources=src,
                                     title=f"Childhood {n}"))
    ranges = playlist_ranges(db, fatma.id, circle.id, w["later"].id)
    assert len(ranges) == PLAYLIST_LIMIT
    # Mulberry and two childhood stories would fill all 5 slots; Workshop keeps its 2.
    assert [r["story_id"] for r in ranges][-2:] == [w["later"].id, w["later"].id]
    items = get_linked_playlist_data(db, fatma.id, circle.id, w["later"].id)["items"]
    assert items[-1]["story_id"] == w["later"].id and items[-1]["period"] == "midlife"


def test_tool_rejects_invisible_story_like_a_missing_one(linked):
    w = linked
    db, fatma, circle = w["db"], w["fatma"], w["circle"]
    errors = {}
    for key, story_id in [("missing", "no-such-story"), ("private", w["secret"].id),
                          ("hidden", w["hidden"].id)]:
        with pytest.raises(ValueError) as exc:
            get_linked_playlist_data(db, fatma.id, circle.id, story_id)
        errors[key] = str(exc.value).replace(story_id, "<id>")
    # A visible story of another circle is not found in this one either.
    other = Circle(name="Other", center_person_id=fatma.id, status="active",
                   chat_time="10:00", timezone="Europe/Istanbul")
    db.add(other); db.commit()
    with pytest.raises(ValueError) as exc:
        get_linked_playlist_data(db, fatma.id, other.id, w["mulberry"].id)
    errors["other_circle"] = str(exc.value).replace(w["mulberry"].id, "<id>")
    assert len(set(errors.values())) == 1


# ---------------------------------------------------------------------------
# Device turn: playlist card
# ---------------------------------------------------------------------------

async def _turn(c, fatma, session_id):
    r = await c.post("/api/device/turn", headers={"x-person-id": fatma.id},
                     data={"session_id": session_id},
                     files={"audio": ("a.wav", _make_wav_bytes(_make_silent_pcm(300)), "audio/wav")})
    assert r.status_code == 200
    return r.json()


@pytest.mark.anyio
async def test_playlist_card_only_in_the_turn_that_ran_the_tool(linked, test_app):
    w = linked
    app, fatma, m = w["app"], w["fatma"], w["mulberry"]
    _set_llm_script(test_app, [
        "Is there a memory on your mind today?",                                  # opening
        "Tell me more about the tree.",                                           # turn 1
        [_tool_use("search_archive", {"query": "mulberry"})],                    # turn 2
        [_tool_use("get_linked_playlist", {"story_id": m.id})],
        "Here is your story The Mulberry Tree, and stories your grandson Ali told.",
        "What did you think of it?",                                              # turn 3
    ])
    async with _client(app) as c:
        start = (await c.post("/api/device/session/start", headers={"x-person-id": fatma.id})).json()
        sid = start["session_id"]
        first = await _turn(c, fatma, sid)
        played = await _turn(c, fatma, sid)
        after = await _turn(c, fatma, sid)

        assert not [x for x in start["cards"] + first["cards"] + after["cards"]
                    if x["type"] == "playlist"]
        cards = [x for x in played["cards"] if x["type"] == "playlist"]
        assert len(cards) == 1
        items = cards[0]["items"]
        assert all(set(i) == {"story_id", "title", "teller", "url"} for i in items)
        assert [i["story_id"] for i in items] == [w["earlier"].id, w["earlier"].id, m.id, m.id,
                                                  w["later"].id]
        # Every url plays for the center.
        for i in items:
            r = await c.get(i["url"], headers={"x-person-id": fatma.id})
            assert r.status_code == 200, i["url"]

    # Another member's private (or hidden) linked story is nowhere in the response.
    text = json.dumps(played)
    for s in (w["secret"], w["hidden"]):
        assert s.id not in text and s.title not in text
    assert SECRET not in text


@pytest.mark.anyio
async def test_failed_playlist_call_gives_no_card(linked, test_app):
    w = linked
    _set_llm_script(test_app, [
        "Hello.",
        [_tool_use("get_linked_playlist", {"story_id": w["secret"].id})],
        "I could not find that story. What else would you like to hear about?",
    ])
    async with _client(w["app"]) as c:
        sid = (await c.post("/api/device/session/start",
                            headers={"x-person-id": w["fatma"].id})).json()["session_id"]
        turn = await _turn(c, w["fatma"], sid)
    assert not [x for x in turn["cards"] if x["type"] == "playlist"]
    assert w["secret"].title not in json.dumps(turn)
