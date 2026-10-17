"""
Panel story endpoints (server/routers/panel.py, core/services/stories.py).

Uses the test_app fixture from tests/test_api.py (temp SQLite DB, Fatma as the
circle center, Elif as a plain member) and adds a few more members:

  Ali   member, teller of the hide/access stories
  Bora  member, a subject of Ali's story
  Ayse  admin

Coverage: one happy path per endpoint; an invisible story gives the same 404 as
a missing one; private segment words and ranges never appear; the playlist
skips an invisible linked story without a trace; the lifeline leaves out
invisible stories; reactions are idempotent and never counted; a family period
correction wins; the hide permission matrix; an admin cannot change access; a
removed link disappears; /api/people needs no header (only ?circle_id=).
"""

from __future__ import annotations

import json
import wave
from datetime import timedelta

import pytest

from core.clock import now_utc
from core.enums import (
    AccessType, LinkReason, LinkSource, LinkStatus, PeriodSource, Role,
    SessionKind, SessionStart, StoryKind, StoryStatus,
)
from core.models import (
    Membership, Person, Reaction, Segment, Story, StoryLink, StorySubject,
    Session as OrmSession,
)

from tests.test_api import _client, _make_silent_pcm, anyio_backend, test_app  # noqa: F401  (fixtures)

SECRET = "zebracode"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _person(db, circle, name, role=Role.member, relation="grandson"):
    p = Person(name=name, birth_year=1990, language="en")
    db.add(p); db.flush()
    db.add(Membership(person_id=p.id, circle_id=circle.id, role=role, relation_to_center=relation))
    db.commit()
    return p


def _words(text, start, end):
    parts = text.split()
    step = (end - start) // len(parts)
    return [{"w": w, "start_ms": start + i * step, "end_ms": start + (i + 1) * step - 1}
            for i, w in enumerate(parts)]


def _session(db, circle, speaker):
    """Session with public [0,1000), private [1000,2000) holding SECRET, public [2000,3000)."""
    sess = OrmSession(circle_id=circle.id, kind=SessionKind.solo, started_by=SessionStart.invitation,
                      participant_ids=[speaker.id], started_at=now_utc().isoformat())
    db.add(sess); db.flush()
    for start, end, text, private in [
        (0, 1000, "we climbed the mulberry tree", False),
        (1000, 2000, f"the {SECRET} is under the floor", True),
        (2000, 3000, "our hands turned purple", False),
    ]:
        db.add(Segment(session_id=sess.id, speaker_id=speaker.id, start_ms=start, end_ms=end,
                       transcript=text, words=_words(text, start, end), is_private=private))
    db.commit()
    return sess


def _story(db, circle, teller, subjects, sources=(), status=StoryStatus.published,
           access=AccessType.circle, title="Story", created_offset_h=0):
    s = Story(
        circle_id=circle.id, teller_id=teller.id, kind=StoryKind.original, title=title,
        ai_summary=f"{title} summary", sources=list(sources),
        access={"type": access, "person_ids": []}, status=status,
        publish_at=(now_utc() - timedelta(hours=1)).isoformat(),
        created_at=(now_utc() + timedelta(hours=created_offset_h)).isoformat(),
    )
    db.add(s); db.flush()
    for person, period in subjects:
        db.add(StorySubject(story_id=s.id, person_id=person.id, period=period,
                            period_source=PeriodSource.ai))
    db.commit()
    return s


def _link(db, a, b, status=LinkStatus.suggested):
    link = StoryLink(from_story_id=a.id, to_story_id=b.id, reason=LinkReason.same_place,
                     source=LinkSource.ai, status=status)
    db.add(link); db.commit()
    return link


async def _req(app, method, url, person=None, body=None):
    headers = {"x-person-id": person.id} if person else {}
    async with _client(app) as c:
        return await c.request(method, url, headers=headers, json=body)


@pytest.fixture
def world(test_app):
    app, db, fatma, elif_, circle, *_, audio_dir = test_app
    ali = _person(db, circle, "Ali")
    bora = _person(db, circle, "Bora")
    ayse = _person(db, circle, "Ayse", role=Role.admin, relation="daughter")
    sess = _session(db, circle, fatma)
    with wave.open(str(audio_dir / f"{sess.id}.wav"), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16_000)
        wf.writeframes(_make_silent_pcm(3000))
    # The source deliberately spans the private part; it must be cut out on read.
    mulberry = _story(db, circle, fatma, [(fatma, "childhood")],
                      sources=[{"session_id": sess.id, "start_ms": 0, "end_ms": 3000}],
                      title="The Mulberry Tree")
    return dict(app=app, db=db, fatma=fatma, elif_=elif_, ali=ali, bora=bora, ayse=ayse,
                circle=circle, sess=sess, mulberry=mulberry)


def _assert_no_secret(payload, sess):
    text = json.dumps(payload)
    assert SECRET not in text
    for rng in _ranges(payload):
        if rng["session_id"] == sess.id:
            assert rng["end_ms"] <= 1000 or rng["start_ms"] >= 2000


def _ranges(payload):
    return payload.get("audio") or payload.get("items") or []


# ---------------------------------------------------------------------------
# GET /api/people
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_people_without_header(world):
    r = await _req(world["app"], "GET", f"/api/people?circle_id={world['circle'].id}")
    assert r.status_code == 200
    by_id = {p["id"]: p for p in r.json()}
    assert by_id[world["fatma"].id]["role"] == "center"
    assert set(by_id[world["ayse"].id]) == {"id", "name", "role", "relation_to_center", "birth_year"}
    assert by_id[world["ayse"].id]["relation_to_center"] == "daughter"
    assert (await _req(world["app"], "GET", "/api/people")).status_code == 400
    assert (await _req(world["app"], "GET", "/api/people?circle_id=nope")).status_code == 404


# ---------------------------------------------------------------------------
# GET /api/stories/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_story_page_happy_path_without_private_part(world):
    r = await _req(world["app"], "GET", f"/api/stories/{world['mulberry'].id}", world["elif_"])
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "The Mulberry Tree"
    assert body["teller"]["id"] == world["fatma"].id
    assert body["subjects"][0]["period"] == "childhood" and body["subjects"][0]["estimated"] is True
    sid = world["sess"].id
    assert [(a["start_ms"], a["end_ms"]) for a in body["audio"]] == [(0, 1000), (2000, 3000)]
    assert body["audio"][0]["url"] == f"/api/audio/{sid}?start=0&end=1000"
    assert [t["text"] for t in body["transcript"]] == ["we climbed the mulberry tree", "our hands turned purple"]
    assert body["has_private_part"] is False
    assert body["can_change_access"] is False and body["can_hide"] is False
    assert body["reactions"] == {"present": [], "mine": []}
    _assert_no_secret(body, world["sess"])


@pytest.mark.anyio
async def test_private_part_notice_only_for_teller(world):
    r = await _req(world["app"], "GET", f"/api/stories/{world['mulberry'].id}", world["fatma"])
    body = r.json()
    assert body["has_private_part"] is True
    assert body["can_change_access"] is True and body["can_hide"] is True
    # Even the teller gets no private words or ranges on the story page.
    _assert_no_secret(body, world["sess"])


@pytest.mark.anyio
async def test_private_part_notice_only_when_it_overlaps_this_storys_sources(world):
    db, fatma, sess = world["db"], world["fatma"], world["sess"]
    # Same session as the private part [1000, 2000), but this story's source stops before it.
    story = _story(db, world["circle"], fatma, [(fatma, "youth")],
                   sources=[{"session_id": sess.id, "start_ms": 0, "end_ms": 1000}])
    body = (await _req(world["app"], "GET", f"/api/stories/{story.id}", fatma)).json()
    assert body["has_private_part"] is False


@pytest.mark.parametrize("status,access,viewer", [
    (StoryStatus.pending, AccessType.circle, "elif_"),     # pending, plain member
    (StoryStatus.published, AccessType.private, "elif_"),  # private, not the teller
    (StoryStatus.hidden, AccessType.circle, "fatma"),      # hidden, not the teller (even the center)
])
@pytest.mark.anyio
async def test_invisible_story_is_the_same_404_as_missing(world, status, access, viewer):
    db = world["db"]
    hidden = _story(db, world["circle"], world["ali"], [(world["fatma"], "youth")],
                    status=status, access=access, title="Invisible")
    app, who = world["app"], world[viewer]
    missing = await _req(app, "GET", "/api/stories/does-not-exist", who)
    assert missing.status_code == 404
    for suffix in ("", "/playlist"):
        r = await _req(app, "GET", f"/api/stories/{hidden.id}{suffix}", who)
        assert r.status_code == 404 and r.json() == missing.json()
    for method, suffix, body in [
        ("POST", "/reactions", {"emoji": "heart", "action": "add"}),
        ("PATCH", f"/subjects/{world['fatma'].id}", {"period": "midlife"}),
        ("PATCH", "", {"hidden": True}),
    ]:
        r = await _req(app, method, f"/api/stories/{hidden.id}{suffix}", who, body)
        assert r.status_code == 404 and r.json() == missing.json()


# ---------------------------------------------------------------------------
# GET /api/lifeline/{person_id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_lifeline_groups_visible_stories_and_excludes_invisible(world):
    db, fatma, circle = world["db"], world["fatma"], world["circle"]
    older = _story(db, circle, fatma, [(fatma, "childhood")], title="Older", created_offset_h=-5)
    _story(db, circle, fatma, [(fatma, "youth")], status=StoryStatus.pending, title="PendingOne")
    _story(db, circle, fatma, [(fatma, "youth")], access=AccessType.private, title="PrivateOne")
    _story(db, circle, world["ali"], [(fatma, "midlife")], status=StoryStatus.hidden, title="HiddenOne")

    r = await _req(world["app"], "GET", f"/api/lifeline/{fatma.id}", world["elif_"])
    assert r.status_code == 200
    body = r.json()
    assert [p["period"] for p in body["periods"]] == [
        "childhood", "youth", "marriage_early_years", "raising_children", "midlife", "retirement"]
    childhood = body["periods"][0]["stories"]
    assert [s["id"] for s in childhood] == [older.id, world["mulberry"].id]
    assert childhood[1]["duration_ms"] == 2000  # the private second is not counted
    assert all(not p["stories"] for p in body["periods"][1:])
    assert "youth" in body["gaps"] and "midlife" in body["gaps"]
    text = json.dumps(body)
    for title in ("PendingOne", "PrivateOne", "HiddenOne"):
        assert title not in text


@pytest.mark.anyio
async def test_lifeline_404_for_person_outside_viewers_circles(world):
    db = world["db"]
    stranger = Person(name="Stranger", birth_year=1950, language="en")
    db.add(stranger); db.commit()
    r = await _req(world["app"], "GET", f"/api/lifeline/{stranger.id}", world["elif_"])
    assert r.status_code == 404


@pytest.mark.anyio
async def test_period_correction_wins_over_ai_in_lifeline(world):
    app, fatma, elif_, story = world["app"], world["fatma"], world["elif_"], world["mulberry"]
    r = await _req(app, "PATCH", f"/api/stories/{story.id}/subjects/{fatma.id}", elif_, {"period": "youth"})
    assert r.status_code == 200
    assert r.json() == {"person_id": fatma.id, "name": "Fatma", "period": "youth",
                        "period_source": "family", "estimated": False, "corrected_by": elif_.id}

    body = (await _req(app, "GET", f"/api/lifeline/{fatma.id}", elif_)).json()
    periods = {p["period"]: p["stories"] for p in body["periods"]}
    assert periods["childhood"] == []
    assert [(s["id"], s["period_source"], s["estimated"]) for s in periods["youth"]] == \
        [(story.id, "family", False)]


@pytest.mark.anyio
async def test_period_correction_rejects_bad_period(world):
    r = await _req(world["app"], "PATCH",
                   f"/api/stories/{world['mulberry'].id}/subjects/{world['fatma'].id}",
                   world["elif_"], {"period": "old_age"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/stories/{id}/playlist
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_playlist_orders_by_period_and_skips_invisible_links_silently(world):
    db, fatma, ali, circle = world["db"], world["fatma"], world["ali"], world["circle"]
    sess2 = _session(db, circle, ali)
    src = [{"session_id": sess2.id, "start_ms": 0, "end_ms": 1000}]
    later = _story(db, circle, ali, [(ali, "midlife")], sources=src, title="Workshop")
    earlier = _story(db, circle, ali, [(fatma, "childhood"), (ali, "retirement")], sources=src,
                     title="Earlier", created_offset_h=-10)
    secret = _story(db, circle, ali, [(ali, "youth")], sources=src, access=AccessType.private,
                    title="SecretTrip")
    pending = _story(db, circle, ali, [(ali, "youth")], sources=src, status=StoryStatus.pending,
                     title="PendingTrip")
    removed = _story(db, circle, ali, [(ali, "youth")], sources=src, title="RemovedTrip")
    m = world["mulberry"]
    for other in (later, earlier, secret, pending):
        _link(db, m, other)
    _link(db, removed, m, status=LinkStatus.removed)

    r = await _req(world["app"], "GET", f"/api/stories/{m.id}/playlist", world["elif_"])
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"story_id", "items"}
    order = [i["story_id"] for i in body["items"]]
    # Earlier (childhood, older) before mulberry (childhood); mulberry has two ranges.
    assert order == [earlier.id, m.id, m.id, later.id]
    assert body["items"][0]["period"] == "childhood" and body["items"][0]["estimated"] is True
    text = json.dumps(body)
    for s in (secret, pending, removed):
        assert s.id not in text and s.title not in text
    assert "skipped" not in text
    _assert_no_secret(body, world["sess"])
    for item in body["items"]:
        assert item["url"] == f"/api/audio/{item['session_id']}?start={item['start_ms']}&end={item['end_ms']}"


# ---------------------------------------------------------------------------
# POST /api/stories/{id}/reactions
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_reactions_are_idempotent_and_never_counted(world):
    app, db, elif_, story = world["app"], world["db"], world["elif_"], world["mulberry"]
    url = f"/api/stories/{story.id}/reactions"
    db.add(Reaction(story_id=story.id, person_id=world["ali"].id, emoji="laugh",
                    delivered_to_center=True, created_at=now_utc().isoformat()))
    db.commit()

    for _ in range(2):
        r = await _req(app, "POST", url, elif_, {"emoji": "heart", "action": "add"})
        assert r.status_code == 200
        assert r.json() == {"story_id": story.id, "present": ["heart", "laugh"], "mine": ["heart"]}
    db.expire_all()
    rows = db.query(Reaction).filter(Reaction.story_id == story.id, Reaction.person_id == elif_.id).all()
    assert [(x.emoji, x.delivered_to_center) for x in rows] == [("heart", False)]

    page = (await _req(app, "GET", f"/api/stories/{story.id}", elif_)).json()
    assert page["reactions"] == {"present": ["heart", "laugh"], "mine": ["heart"]}

    for _ in range(2):
        r = await _req(app, "POST", url, elif_, {"emoji": "heart", "action": "remove"})
        assert r.json() == {"story_id": story.id, "present": ["laugh"], "mine": []}
    assert "count" not in json.dumps(page) and "count" not in r.text

    bad = await _req(app, "POST", url, elif_, {"emoji": "thumbs", "action": "add"})
    assert bad.status_code == 400


# ---------------------------------------------------------------------------
# PATCH /api/stories/{id}
# ---------------------------------------------------------------------------

def _ali_story(world):
    return _story(world["db"], world["circle"], world["ali"], [(world["bora"], "youth")],
                  title="Ali's story")


@pytest.mark.parametrize("hider,allowed", [
    ("ali", True),     # teller
    ("bora", True),    # subject
    ("fatma", True),   # center
    ("ayse", True),    # admin
    ("elif_", False),  # plain member
])
@pytest.mark.anyio
async def test_hide_permission_matrix(world, hider, allowed):
    story = _ali_story(world)
    r = await _req(world["app"], "PATCH", f"/api/stories/{story.id}", world[hider], {"hidden": True})
    world["db"].expire_all()
    if allowed:
        assert r.status_code == 200 and r.json()["status"] == "hidden"
        assert world["db"].get(Story, story.id).status == StoryStatus.hidden
    else:
        assert r.status_code == 403
        assert world["db"].get(Story, story.id).status == StoryStatus.published


@pytest.mark.parametrize("who", ["ali", "bora", "fatma", "ayse"])
@pytest.mark.anyio
async def test_hiding_is_final(world, who):
    story = _ali_story(world)
    app, url = world["app"], f"/api/stories/{story.id}"
    assert (await _req(app, "PATCH", url, world[who], {"hidden": True})).status_code == 200
    # Nobody can unhide: the teller (who still sees it) gets 400, everyone else
    # the same 404 as a missing story.
    r = await _req(app, "PATCH", url, world["ali"], {"hidden": False})
    assert r.status_code == 400
    if who != "ali":
        assert (await _req(app, "PATCH", url, world[who], {"hidden": False})).status_code == 404
    world["db"].expire_all()
    assert world["db"].get(Story, story.id).status == StoryStatus.hidden
    page = (await _req(app, "GET", url, world["ali"])).json()
    assert page["can_hide"] is False


@pytest.mark.anyio
async def test_unhide_refused_even_on_a_visible_story(world):
    story = _ali_story(world)
    r = await _req(world["app"], "PATCH", f"/api/stories/{story.id}", world["ali"], {"hidden": False})
    assert r.status_code == 400


@pytest.mark.anyio
async def test_teller_changes_access_but_admin_cannot(world):
    story = _ali_story(world)
    app, url = world["app"], f"/api/stories/{story.id}"
    r = await _req(app, "PATCH", url, world["ayse"], {"access": "private"})
    assert r.status_code == 403
    r = await _req(app, "PATCH", url, world["ayse"], {"access": "private", "hidden": True})
    assert r.status_code == 403
    world["db"].expire_all()
    s = world["db"].get(Story, story.id)
    assert s.access["type"] == "circle" and s.status == StoryStatus.published

    r = await _req(app, "PATCH", url, world["ali"], {"access": "private"})
    assert r.status_code == 200 and r.json()["access"]["type"] == "private"
    assert (await _req(app, "GET", url, world["elif_"])).status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/links/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_removed_link_disappears_from_story_and_playlist(world):
    db, app, elif_, m = world["db"], world["app"], world["elif_"], world["mulberry"]
    other = _story(db, world["circle"], world["ali"], [(world["ali"], "youth")], title="Linked")
    link = _link(db, m, other)

    page = (await _req(app, "GET", f"/api/stories/{m.id}", elif_)).json()
    assert [l["link_id"] for l in page["linked_stories"]] == [link.id]

    r = await _req(app, "DELETE", f"/api/links/{link.id}", elif_)
    assert r.status_code == 200 and r.json() == {"id": link.id, "status": "removed"}
    db.expire_all()
    assert db.get(StoryLink, link.id).status == LinkStatus.removed  # the row stays

    page = (await _req(app, "GET", f"/api/stories/{m.id}", elif_)).json()
    assert page["linked_stories"] == []
    playlist = (await _req(app, "GET", f"/api/stories/{m.id}/playlist", elif_)).json()
    assert other.id not in json.dumps(playlist)


@pytest.mark.anyio
async def test_link_delete_needs_both_stories_visible(world):
    db = world["db"]
    secret = _story(db, world["circle"], world["ali"], [(world["ali"], "youth")],
                    access=AccessType.private, title="Secret")
    link = _link(db, world["mulberry"], secret)
    r = await _req(world["app"], "DELETE", f"/api/links/{link.id}", world["elif_"])
    missing = await _req(world["app"], "DELETE", "/api/links/nope", world["elif_"])
    assert r.status_code == 404 and r.json() == missing.json()
    db.expire_all()
    assert db.get(StoryLink, link.id).status == LinkStatus.suggested


@pytest.mark.anyio
async def test_linked_story_list_drops_invisible_story(world):
    db = world["db"]
    secret = _story(db, world["circle"], world["ali"], [(world["ali"], "youth")],
                    access=AccessType.private, title="Secret")
    _link(db, world["mulberry"], secret)
    page = (await _req(world["app"], "GET", f"/api/stories/{world['mulberry'].id}", world["elif_"])).json()
    assert page["linked_stories"] == []
    assert secret.id not in json.dumps(page)


# ---------------------------------------------------------------------------
# Review follow-ups
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_returned_audio_urls_pass_the_audio_checks(world):
    app, elif_ = world["app"], world["elif_"]
    body = (await _req(app, "GET", f"/api/stories/{world['mulberry'].id}", elif_)).json()
    async with _client(app) as c:
        for rng in body["audio"]:
            r = await c.get(rng["url"], headers={"x-person-id": elif_.id})
            assert r.status_code == 200
        # The uncut source would cover the private part and is refused.
        r = await c.get(f"/api/audio/{world['sess'].id}?start=0&end=3000",
                        headers={"x-person-id": elif_.id})
        assert r.status_code == 403


@pytest.mark.anyio
async def test_partial_segment_without_word_timings_shows_nothing(world):
    db, circle, fatma = world["db"], world["circle"], world["fatma"]
    sess = OrmSession(circle_id=circle.id, kind=SessionKind.solo, started_by=SessionStart.invitation,
                      participant_ids=[fatma.id], started_at=now_utc().isoformat())
    db.add(sess); db.flush()
    db.add(Segment(session_id=sess.id, speaker_id=fatma.id, start_ms=1000, end_ms=2000,
                   transcript="text of another story", words=[], is_private=False))
    db.commit()
    story = _story(db, circle, fatma, [(fatma, "youth")],
                   sources=[{"session_id": sess.id, "start_ms": 0, "end_ms": 1500}])
    body = (await _req(world["app"], "GET", f"/api/stories/{story.id}", world["elif_"])).json()
    assert body["transcript"] == []


@pytest.mark.anyio
async def test_retelling_of_invisible_original_looks_like_an_original(world):
    db, circle, fatma = world["db"], world["circle"], world["fatma"]
    original = _story(db, circle, world["ali"], [(fatma, "youth")], access=AccessType.private)
    retelling = _story(db, circle, fatma, [(fatma, "youth")])
    retelling.kind, retelling.original_story_id = StoryKind.retelling, original.id
    db.commit()
    body = (await _req(world["app"], "GET", f"/api/stories/{retelling.id}", world["elif_"])).json()
    assert body["kind"] == "original" and body["original_story_id"] is None
    assert original.id not in json.dumps(body)
    teller_view = (await _req(world["app"], "GET", f"/api/stories/{retelling.id}", world["ali"])).json()
    assert teller_view["kind"] == "retelling" and teller_view["original_story_id"] == original.id
