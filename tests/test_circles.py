"""
Circles beyond the demo family (core/services/circles.py, server/routers/panel.py,
core/services/admin.py members, core/services/questions.my_questions).

Uses the test_app fixture from tests/test_api.py; its circle is marked as the
demo circle, with Ayse as its admin and one published story.

Coverage
--------
- GET /api/questions/mine: declined, asked and speaker-filtered questions show
  as "waiting"; a family-filtered one is not listed; "answered" carries the
  story id only once the asker can see the story; nobody else's questions.
- GET /api/people?circle_id= lists only that circle's people; GET /api/circles/demo.
- X-Circle-Id selects the circle on panel and device endpoints; a circle the
  person is not a member of (or not the center of, on the device) gets the same 403.
- POST /api/circles validation (400 naming the field) and the created rows.
- A new circle end to end: create, add two members, a member asks, the center's
  device session sees only that circle's question, feed and lifeline show
  nothing from the demo family, and the demo family sees nothing of it.
- Member rules: admin only; the center and the last admin are protected;
  removing a member keeps their stories.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from core.clock import now_utc
from core.enums import (
    AccessType, QuestionSource, QuestionStatus, Role, StoryKind, StoryStatus, TopicSource,
)
from core.models import Circle, Membership, Person, Question, SensitiveTopic, Story, StorySubject
from core.models import Session as OrmSession
from tests.test_api import _client, _set_llm_script, anyio_backend, test_app  # noqa: F401  (fixtures)
from tests.test_chat_agent import _tool_use
from tests.test_panel_stories import _person

DEMO_STORY = "The Mulberry Tree"


@pytest.fixture
def cw(test_app, monkeypatch):
    app, db, fatma, elif_, circle, q, store, *_ = test_app
    import server.routers.admin as adm_r
    from core.db import SessionLocal
    monkeypatch.setattr(adm_r, "SessionLocal", SessionLocal)   # patched by test_app
    circle.is_demo = True
    ayse = _person(db, circle, "Ayse", role=Role.admin, relation="daughter")
    story = _story(db, circle.id, fatma.id, DEMO_STORY)
    return dict(app=app, db=db, fatma=fatma, elif_=elif_, ayse=ayse, circle=circle, q=q,
                store=store, story=story, fixture=test_app)


def _story(db, circle_id, teller_id, title, status=StoryStatus.published, access=AccessType.circle):
    s = Story(circle_id=circle_id, teller_id=teller_id, kind=StoryKind.original, title=title,
              ai_summary=f"About {title}.", sources=[], status=status,
              access={"type": access, "person_ids": []},
              publish_at=now_utc().isoformat(), created_at=now_utc().isoformat())
    db.add(s); db.flush()
    db.add(StorySubject(story_id=s.id, person_id=teller_id, period="childhood"))
    db.commit()
    return s


def _question(db, circle_id, asker_id, target_id, text, status, answer=None, offset_min=0):
    q = Question(circle_id=circle_id, target_person_id=target_id, asker_id=asker_id, text=text,
                 source=QuestionSource.family, status=status, answer=answer,
                 created_at=(now_utc() + timedelta(minutes=offset_min)).isoformat())
    db.add(q); db.commit()
    return q


async def _req(app, method, url, person=None, body=None, circle=None):
    headers = {}
    if person is not None:
        headers["x-person-id"] = person if isinstance(person, str) else person.id
    if circle is not None:
        headers["x-circle-id"] = circle
    async with _client(app) as c:
        return await c.request(method, url, headers=headers, json=body)


def _new_circle_body(**over):
    body = {
        "circle_name": "The Demir Family",
        "timezone": "Europe/Berlin",
        "chat_time": "09:30",
        "center": {"name": "Hasan Demir", "birth_year": 1944},
        "creator": {"name": "Selin Demir", "birth_year": 1975, "relation_to_center": "daughter"},
    }
    body.update(over)
    return body


# ---------------------------------------------------------------------------
# GET /api/questions/mine
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_my_questions_statuses(cw):
    db, c, elif_, fatma, ayse = cw["db"], cw["circle"].id, cw["elif_"], cw["fatma"], cw["ayse"]
    db.add_all([
        SensitiveTopic(circle_id=c, text="Zuleyhanur", source=TopicSource.speaker,
                       added_by=fatma.id, created_at=now_utc().isoformat()),
        SensitiveTopic(circle_id=c, text="traffic accident", source=TopicSource.family,
                       added_by=ayse.id, created_at=now_utc().isoformat()),
    ]); db.commit()
    asked = _question(db, c, elif_.id, fatma.id, "Asked one?", QuestionStatus.asked, offset_min=1)
    declined = _question(db, c, elif_.id, fatma.id, "Declined one?", QuestionStatus.declined, offset_min=2)
    refused = _question(db, c, elif_.id, fatma.id, "Who was Zuleyhanur?", QuestionStatus.filtered, offset_min=3)
    family = _question(db, c, elif_.id, fatma.id, "The traffic accident?", QuestionStatus.filtered, offset_min=4)
    answered = _question(db, c, elif_.id, fatma.id, "The mulberry tree?", QuestionStatus.answered,
                         answer={"story_id": cw["story"].id, "session_id": "s", "start_ms": 0, "end_ms": 1},
                         offset_min=5)
    pending = _story(db, c, fatma.id, "Not yet", status=StoryStatus.pending)
    early = _question(db, c, elif_.id, fatma.id, "Pending answer?", QuestionStatus.answered,
                      answer={"story_id": pending.id, "session_id": "s", "start_ms": 0, "end_ms": 1},
                      offset_min=6)
    other = _question(db, c, ayse.id, fatma.id, "Ayse's question?", QuestionStatus.waiting, offset_min=7)

    r = await _req(cw["app"], "GET", "/api/questions/mine", elif_)
    assert r.status_code == 200, r.text
    items = r.json()
    assert [i["id"] for i in items] == [early.id, answered.id, refused.id, declined.id, asked.id, cw["q"].id]
    by_id = {i["id"]: i for i in items}
    for q in (early, refused, declined, asked, cw["q"]):
        assert by_id[q.id]["status"] == "waiting" and by_id[q.id]["answer_story_id"] is None
    assert by_id[answered.id]["status"] == "answered"
    assert by_id[answered.id]["answer_story_id"] == cw["story"].id
    assert set(items[0]) == {"id", "text", "target_person_id", "period", "status", "created_at",
                             "answer_story_id"}
    assert family.id not in r.text and other.id not in r.text and pending.id not in r.text

    mine = (await _req(cw["app"], "GET", "/api/questions/mine", ayse)).json()
    assert [i["id"] for i in mine] == [other.id]
    assert (await _req(cw["app"], "GET", "/api/questions/mine")).status_code == 403


# ---------------------------------------------------------------------------
# People, demo circle, X-Circle-Id
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_people_scoped_by_circle_and_demo_circle(cw):
    app = cw["app"]
    created = (await _req(app, "POST", "/api/circles", body=_new_circle_body())).json()

    demo = (await _req(app, "GET", "/api/circles/demo")).json()
    assert demo == {"id": cw["circle"].id, "name": "Test Family"}

    demo_people = (await _req(app, "GET", f"/api/people?circle_id={demo['id']}")).json()
    assert sorted(p["name"] for p in demo_people) == ["Ayse", "Elif", "Fatma"]
    new_people = (await _req(app, "GET", f"/api/people?circle_id={created['circle_id']}")).json()
    assert {p["name"]: p["role"] for p in new_people} == {"Hasan Demir": "center", "Selin Demir": "admin"}
    assert "Fatma" not in str(new_people) and "Demir" not in str(demo_people)

    cw["circle"].is_demo = False
    cw["db"].commit()
    assert (await _req(app, "GET", "/api/circles/demo")).status_code == 404


@pytest.mark.anyio
async def test_x_circle_id_selects_circle_and_rejects_non_membership(cw):
    app, db, elif_ = cw["app"], cw["db"], cw["elif_"]
    created = (await _req(app, "POST", "/api/circles", body=_new_circle_body())).json()
    new_id, demo_id = created["circle_id"], cw["circle"].id
    db.add(Membership(person_id=elif_.id, circle_id=new_id, role=Role.member, relation_to_center="neighbour"))
    db.commit()

    for cid, name in ((new_id, "The Demir Family"), (demo_id, "Test Family")):
        r = await _req(app, "GET", "/api/circle", elif_, circle=cid)
        assert r.status_code == 200 and r.json()["circle"]["name"] == name
    feed = (await _req(app, "GET", "/api/feed", elif_, circle=new_id)).json()
    assert DEMO_STORY not in str(feed)
    assert DEMO_STORY in str((await _req(app, "GET", "/api/feed", elif_, circle=demo_id)).json())

    # Not a member: the same 403 as no membership, on panel, admin and device endpoints.
    other = (await _req(app, "POST", "/api/circles", body=_new_circle_body(circle_name="Other"))).json()
    no_member = (await _req(app, "GET", "/api/circle", "nobody")).json()["detail"]
    for method, url in (("GET", "/api/circle"), ("GET", "/api/feed"), ("GET", "/api/questions/mine"),
                        ("GET", f"/api/lifeline/{cw['fatma'].id}"), ("GET", f"/api/stories/{cw['story'].id}")):
        r = await _req(app, method, url, elif_, circle=other["circle_id"])
        assert r.status_code == 403 and r.json()["detail"] == no_member, url
    r = await _req(app, "GET", "/api/admin/sensitive-topics", cw["ayse"], circle=other["circle_id"])
    assert r.status_code == 403

    fatma = cw["fatma"]
    ok = await _req(app, "GET", "/api/device/invitation", fatma, circle=demo_id)
    assert ok.status_code == 200
    for cid in (new_id, other["circle_id"]):
        assert (await _req(app, "GET", "/api/device/invitation", fatma, circle=cid)).status_code == 403
        assert (await _req(app, "POST", "/api/device/session/start", fatma, circle=cid)).status_code == 403


# ---------------------------------------------------------------------------
# POST /api/circles
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_circle_rows(cw):
    r = await _req(cw["app"], "POST", "/api/circles", body=_new_circle_body())
    assert r.status_code == 200, r.text
    ids = r.json()
    assert set(ids) == {"circle_id", "center_id", "creator_id", "session_token", "invite_url_path"}
    db = cw["db"]
    db.expire_all()
    circle = db.get(Circle, ids["circle_id"])
    assert (circle.name, circle.timezone, circle.chat_time, circle.is_demo) == \
        ("The Demir Family", "Europe/Berlin", "09:30", False)
    assert circle.center_person_id == ids["center_id"]
    assert db.get(Membership, (ids["center_id"], circle.id)).role == Role.center
    creator = db.get(Membership, (ids["creator_id"], circle.id))
    assert (creator.role, creator.relation_to_center) == (Role.admin, "daughter")
    assert db.get(Person, ids["center_id"]).birth_year == 1944


@pytest.mark.anyio
@pytest.mark.parametrize("over, field", [
    ({"circle_name": ""}, "circle_name"),
    ({"circle_name": "   "}, "circle_name"),
    ({"circle_name": "x" * 61}, "circle_name"),
    ({"timezone": "Mars/Olympus"}, "timezone"),
    ({"timezone": None}, "timezone"),
    ({"chat_time": "25:00"}, "chat_time"),
    ({"chat_time": "9:30"}, "chat_time"),
    ({"center": None}, "center"),
    ({"center": {"name": "Hasan", "birth_year": 1899}}, "center.birth_year"),
    ({"center": {"name": "Hasan", "birth_year": "1944"}}, "center.birth_year"),
    ({"center": {"birth_year": 1944}}, "center.name"),
    ({"creator": {"name": "Selin", "birth_year": 3000, "relation_to_center": "daughter"}},
     "creator.birth_year"),
    ({"creator": {"name": "Selin", "birth_year": 1975}}, "creator.relation_to_center"),
    ({"creator": {"name": "y" * 61, "birth_year": 1975, "relation_to_center": "son"}}, "creator.name"),
])
async def test_create_circle_validation(cw, over, field):
    before = cw["db"].query(Circle).count()
    r = await _req(cw["app"], "POST", "/api/circles", body=_new_circle_body(**over))
    assert r.status_code == 400, r.text
    assert field in r.json()["detail"]
    assert cw["db"].query(Circle).count() == before
    assert (await _req(cw["app"], "POST", "/api/circles", body=["not", "an", "object"])).status_code == 400


# ---------------------------------------------------------------------------
# A new circle end to end
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_new_circle_end_to_end(cw):
    app, db = cw["app"], cw["db"]
    ids = (await _req(app, "POST", "/api/circles", body=_new_circle_body())).json()
    cid, center, creator = ids["circle_id"], ids["center_id"], ids["creator_id"]

    members = []
    for name, rel in (("Deniz Demir", "grandson"), ("Ece Demir", "granddaughter")):
        r = await _req(app, "POST", "/api/admin/members", creator,
                       {"name": name, "birth_year": 2001, "relation_to_center": rel, "role": "member"})
        assert r.status_code == 200, r.text
        assert r.json()["role"] == "member"
        members.append(r.json()["id"])
    deniz = members[0]

    r = await _req(app, "POST", "/api/questions", deniz,
                   {"target_person_id": center, "text": "Where did you grow up?"})
    assert r.status_code == 200 and r.json()["status"] == "waiting"
    qid = r.json()["question"]["id"]
    # The demo family's center is not in this circle.
    bad = await _req(app, "POST", "/api/questions", deniz,
                     {"target_person_id": cw["fatma"].id, "text": "Hello?"})
    assert bad.status_code == 400

    # The center's device session sees only this circle's question.
    _set_llm_script(cw["fixture"], [
        [_tool_use("get_pending_questions", {"limit": 5}, str(uuid.uuid4()))],
        "Good morning, Hasan! Where did you grow up?",
    ])
    r = await _req(app, "POST", "/api/device/session/start", center)
    assert r.status_code == 200, r.text
    session_id = r.json()["session_id"]
    db.expire_all()
    assert db.get(OrmSession, session_id).circle_id == cid
    live = cw["store"].get(session_id)
    assert set(live.seen_questions) == {qid}
    inv = await _req(app, "GET", "/api/device/invitation", center)
    assert inv.status_code == 200

    # A story of the new circle (as the archivist would save it), published.
    new_story = _story(db, cid, center, "The House in Trabzon")

    feed = (await _req(app, "GET", "/api/feed", deniz)).json()
    assert "The House in Trabzon" in str(feed) and DEMO_STORY not in str(feed)
    life = (await _req(app, "GET", f"/api/lifeline/{center}", deniz)).json()
    titles = [s["title"] for p in life["periods"] for s in p["stories"]]
    assert titles == ["The House in Trabzon"]
    assert (await _req(app, "GET", f"/api/lifeline/{cw['fatma'].id}", deniz)).status_code == 404
    assert (await _req(app, "GET", f"/api/stories/{cw['story'].id}", deniz)).status_code == 404
    circle = (await _req(app, "GET", "/api/circle", deniz)).json()
    assert sorted(m["name"] for m in circle["members"]) == \
        ["Deniz Demir", "Ece Demir", "Hasan Demir", "Selin Demir"]

    # The demo family sees nothing of the new circle.
    elif_ = cw["elif_"]
    demo_views = [
        (await _req(app, "GET", "/api/feed", elif_)).text,
        (await _req(app, "GET", "/api/circle", elif_)).text,
        (await _req(app, "GET", "/api/questions/mine", elif_)).text,
        (await _req(app, "GET", f"/api/lifeline/{cw['fatma'].id}", elif_)).text,
        (await _req(app, "GET", f"/api/people?circle_id={cw['circle'].id}")).text,
    ]
    for text in demo_views:
        assert "Demir" not in text and "Trabzon" not in text and qid not in text
    assert (await _req(app, "GET", f"/api/stories/{new_story.id}", elif_)).status_code == 404
    assert (await _req(app, "GET", f"/api/lifeline/{center}", elif_)).status_code == 404


# ---------------------------------------------------------------------------
# Member rules
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_member_rules(cw):
    app, db = cw["app"], cw["db"]
    ids = (await _req(app, "POST", "/api/circles", body=_new_circle_body())).json()
    cid, center, creator = ids["circle_id"], ids["center_id"], ids["creator_id"]
    url = "/api/admin/members"
    member = (await _req(app, "POST", url, creator, {"name": "Deniz", "birth_year": 2001,
                                                     "relation_to_center": "grandson"})).json()["id"]

    # Admin only: a member and the center get the same 403.
    forbidden = (await _req(app, "POST", url, member, {"name": "X", "birth_year": 2000,
                                                       "relation_to_center": "son"})).json()
    for who in (member, center):
        for method, u, body in (("POST", url, {"name": "X", "birth_year": 2000, "relation_to_center": "son"}),
                                ("PATCH", f"{url}/{creator}", {"role": "member"}),
                                ("DELETE", f"{url}/{creator}", None)):
            r = await _req(app, method, u, who, body)
            assert r.status_code == 403 and r.json() == forbidden
    # An admin of the demo circle is not an admin here.
    assert (await _req(app, "DELETE", f"{url}/{member}", cw["ayse"], circle=cid)).status_code == 403

    # Validation.
    for body in ({"name": "", "birth_year": 2000, "relation_to_center": "son"},
                 {"name": "X", "birth_year": 1800, "relation_to_center": "son"},
                 {"name": "X", "birth_year": 2000, "relation_to_center": "son", "role": "center"}):
        assert (await _req(app, "POST", url, creator, body)).status_code == 400
    assert (await _req(app, "PATCH", f"{url}/{member}", creator, {"role": "center"})).status_code == 400
    assert (await _req(app, "PATCH", f"{url}/{cw['elif_'].id}", creator, {"role": "admin"})).status_code == 404

    # The center: never removed or changed.
    assert (await _req(app, "DELETE", f"{url}/{center}", creator)).status_code == 400
    assert (await _req(app, "PATCH", f"{url}/{center}", creator, {"role": "admin"})).status_code == 400
    assert (await _req(app, "PATCH", f"{url}/{center}", creator, {"relation_to_center": "x"})).status_code == 400

    # The last admin: never removed or demoted.
    assert (await _req(app, "DELETE", f"{url}/{creator}", creator)).status_code == 400
    assert (await _req(app, "PATCH", f"{url}/{creator}", creator, {"role": "member"})).status_code == 400

    # With a second admin the first can step down.
    r = await _req(app, "PATCH", f"{url}/{member}", creator, {"role": "admin", "relation_to_center": "eldest grandson"})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert r.json()["relation_to_center"] == "eldest grandson"
    assert (await _req(app, "PATCH", f"{url}/{creator}", creator, {"role": "member"})).json()["role"] == "member"
    assert (await _req(app, "DELETE", f"{url}/{member}", member)).status_code == 400   # now the last admin

    # Removing a member keeps their stories; they lose access to the circle.
    story = _story(db, cid, creator, "Selin's Story")
    r = await _req(app, "DELETE", f"{url}/{creator}", member)
    assert r.status_code == 200 and r.json() == {"id": creator, "removed": True}
    db.expire_all()
    assert db.get(Membership, (creator, cid)) is None
    assert db.get(Story, story.id) is not None and db.get(Person, creator) is not None
    assert (await _req(app, "GET", "/api/circle", creator)).status_code == 403
    people = (await _req(app, "GET", f"/api/people?circle_id={cid}")).json()
    assert creator not in {p["id"] for p in people}


# ---------------------------------------------------------------------------
# Privacy review follow-ups
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_family_topic_added_later_does_not_reveal_a_speaker_refusal(cw):
    """A waiting question and a question filtered only by a topic Fatma refused
    herself look the same before and after the family adds a matching topic."""
    app, db, c, elif_, fatma, ayse = cw["app"], cw["db"], cw["circle"].id, cw["elif_"], cw["fatma"], cw["ayse"]
    db.add(SensitiveTopic(circle_id=c, text="Mustafa", source=TopicSource.speaker,
                          added_by=fatma.id, created_at=now_utc().isoformat()))
    db.commit()
    waiting = _question(db, c, elif_.id, fatma.id, "Tell me about the Mustafa farm?", QuestionStatus.waiting, offset_min=1)
    refused = _question(db, c, elif_.id, fatma.id, "Who was Mustafa?", QuestionStatus.filtered, offset_min=2)

    def statuses(items):
        return {i["id"]: i["status"] for i in items if i["id"] in (waiting.id, refused.id)}

    before = (await _req(app, "GET", "/api/questions/mine", elif_)).json()
    assert statuses(before) == {waiting.id: "waiting", refused.id: "waiting"}

    r = await _req(app, "POST", "/api/admin/sensitive-topics", ayse, {"text": "Mustafa"})
    assert r.status_code == 200, r.text
    after = (await _req(app, "GET", "/api/questions/mine", elif_)).json()
    assert statuses(after) == {}          # both left out, alike
    # Sending either again gives the same "not sent" answer.
    for q in (waiting, refused):
        r = await _req(app, "POST", "/api/questions", elif_, {"target_person_id": fatma.id, "text": q.text})
        assert r.json()["status"] == "filtered", q.text


@pytest.mark.anyio
async def test_audio_tts_and_device_reject_another_circles_header(cw):
    app, fatma = cw["app"], cw["fatma"]
    other = (await _req(app, "POST", "/api/circles", body=_new_circle_body())).json()["circle_id"]
    demo = cw["circle"].id
    _set_llm_script(cw["fixture"], ["Hello, Fatma!", "Nice.", "Nice."])
    start = await _req(app, "POST", "/api/device/session/start", fatma, circle=demo)
    assert start.status_code == 200, start.text
    session_id, tts_url = start.json()["session_id"], start.json()["reply_audio_url"]

    async with _client(app) as c:
        def h(cid):
            return {"x-person-id": fatma.id, "x-circle-id": cid}
        ok = await c.get(tts_url, headers=h(demo))
        assert ok.status_code == 200
        denied = await c.get(tts_url, headers=h(other))
        assert denied.status_code == 403
        audio_denied = await c.get(f"/api/audio/{session_id}?start=0&end=100", headers=h(other))
        assert audio_denied.status_code == 403 and audio_denied.json() == denied.json()

        turn = await c.post("/api/device/turn", headers=h(other), data={"session_id": session_id},
                            files={"audio": ("a.wav", b"RIFF", "audio/wav")})
        assert turn.status_code == 403
        end = await c.post("/api/device/session/end", headers=h(other), json={"session_id": session_id})
        assert end.status_code == 403
        assert (await c.post("/api/device/session/end", headers=h(demo),
                             json={"session_id": session_id})).status_code == 200


@pytest.mark.anyio
async def test_removed_member_cannot_reach_old_circle_through_another(cw):
    app, db, elif_ = cw["app"], cw["db"], cw["elif_"]
    ids = (await _req(app, "POST", "/api/circles", body=_new_circle_body())).json()
    cid, creator = ids["circle_id"], ids["creator_id"]
    deniz = (await _req(app, "POST", "/api/admin/members", creator,
                        {"name": "Deniz", "birth_year": 2001, "relation_to_center": "grandson"})).json()["id"]
    story = _story(db, cid, ids["center_id"], "The House in Trabzon")
    q = _question(db, cid, deniz, ids["center_id"], "Where did you grow up?", QuestionStatus.waiting)
    # Deniz is also in the demo family.
    db.add(Membership(person_id=deniz, circle_id=cw["circle"].id, role=Role.member, relation_to_center="friend"))
    db.commit()
    assert (await _req(app, "GET", f"/api/stories/{story.id}", deniz)).status_code == 200

    assert (await _req(app, "DELETE", f"/api/admin/members/{deniz}", creator)).status_code == 200
    assert (await _req(app, "GET", "/api/circle", deniz, circle=cid)).status_code == 403
    assert (await _req(app, "GET", f"/api/stories/{story.id}", deniz)).status_code == 404
    assert (await _req(app, "GET", f"/api/lifeline/{ids['center_id']}", deniz)).status_code == 404
    feed = (await _req(app, "GET", "/api/feed", deniz)).text
    mine = (await _req(app, "GET", "/api/questions/mine", deniz)).text
    assert "Trabzon" not in feed and q.id not in mine
