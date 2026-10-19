"""
Personal invite links and sign-in sessions (core/services/auth.py,
server/auth.py, server/routers/invites.py, the admin invite endpoints).

Uses the test_app fixture from tests/test_api.py (Fatma center, Elif member),
with Ayse added as the admin.

Coverage
--------
- Tokens are never stored in clear: not in any row, not in the database file;
  only their SHA-256 hashes.
- Accepting a link gives a bearer token that works on panel and device
  endpoints, outside demo mode too; the link stays reusable.
- GET /api/invites/{token}: who it is for; one 404 for revoked, wrong, unknown.
- Revoking a link (DELETE, a new link, removing the member) stops the link and
  every session made from it; logout stops one session.
- Another circle's bearer is the same 403 as a non-member (X-Circle-Id that
  differs), and sees nothing of this circle.
- Outside demo mode: X-Person-Id, no auth and a bad token are one 401;
  /api/people and /api/circles/demo are 404.
- POST /api/circles signs the creator in and gives their own invite link.
- Only an admin makes or revokes links; the access log never shows a token.
"""

from __future__ import annotations

import hashlib
import logging

import pytest

from core.enums import Role
from core.models import AuthSession, InviteLink
from server.auth import SIGN_IN_REQUIRED, RedactTokens
from tests.test_api import _client, anyio_backend, test_app  # noqa: F401  (fixtures)
from tests.test_circles import _new_circle_body
from tests.test_panel_stories import _person


@pytest.fixture
def env(test_app, monkeypatch):
    app, db, fatma, elif_, circle, *_ = test_app
    import server.routers.admin as adm_r
    from core.db import SessionLocal
    monkeypatch.setattr(adm_r, "SessionLocal", SessionLocal)   # patched by test_app
    ayse = _person(db, circle, "Ayse", role=Role.admin, relation="daughter")
    return dict(app=app, db=db, fatma=fatma, elif_=elif_, ayse=ayse, circle=circle, test_app=test_app)


async def _call(app, method, url, person=None, bearer=None, circle=None, body=None):
    headers = {}
    if person is not None:
        headers["x-person-id"] = person.id
    if bearer is not None:
        headers["authorization"] = f"Bearer {bearer}"
    if circle is not None:
        headers["x-circle-id"] = circle
    async with _client(app) as c:
        return await c.request(method, url, headers=headers, json=body)


async def _invite(env, person) -> str:
    """The admin (demo headers) makes `person`'s link; returns its token."""
    r = await _call(env["app"], "POST", "/api/admin/invites", person=env["ayse"], body={"person_id": person.id})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["invite_url_path"] == f"/join/{out['token']}" and out["person_id"] == person.id
    return out["token"]


async def _accept(env, token) -> str:
    r = await _call(env["app"], "POST", f"/api/invites/{token}/accept")
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Tokens at rest
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tokens_are_stored_only_as_hashes(env, tmp_path):
    token = await _invite(env, env["elif_"])
    r = await _call(env["app"], "POST", f"/api/invites/{token}/accept")
    session_token = r.json()["session_token"]
    assert r.json()["person_id"] == env["elif_"].id and r.json()["circle_id"] == env["circle"].id

    db = env["db"]
    db.expire_all()
    link = db.query(InviteLink).one()
    sess = db.query(AuthSession).one()
    assert link.token_hash == _sha(token) and sess.token_hash == _sha(session_token)
    assert sess.invite_id == link.id and sess.person_id == env["elif_"].id

    raw = (tmp_path / "test.db").read_bytes()
    for t in (token, session_token):
        assert t.encode() not in raw


# ---------------------------------------------------------------------------
# Bearer works on panel and device endpoints, outside demo mode too
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_accepted_link_bearer_works_on_panel_and_device(env, monkeypatch):
    elif_token = await _invite(env, env["elif_"])
    fatma_token = await _invite(env, env["fatma"])
    monkeypatch.delenv("EVOCA_DEMO_MODE")
    app = env["app"]

    elif_bearer = await _accept(env, elif_token)
    r = await _call(app, "GET", "/api/circle", bearer=elif_bearer)
    assert r.status_code == 200 and r.json()["me"]["id"] == env["elif_"].id
    assert (await _call(app, "GET", "/api/feed", bearer=elif_bearer)).status_code == 200
    r = await _call(app, "POST", "/api/questions", bearer=elif_bearer,
                    body={"target_person_id": env["fatma"].id, "text": "Where did you meet Grandpa?"})
    assert r.status_code == 200 and r.json()["question"]["asker_id"] == env["elif_"].id

    # The link is reusable: a second device gets its own session.
    second = await _accept(env, elif_token)
    assert second != elif_bearer
    assert (await _call(app, "GET", "/api/circle", bearer=second)).status_code == 200

    fatma_bearer = await _accept(env, fatma_token)
    r = await _call(app, "GET", "/api/device/invitation", bearer=fatma_bearer)
    assert r.status_code == 200 and r.json()["active"] is True
    r = await _call(app, "POST", "/api/device/session/start", bearer=fatma_bearer)
    assert r.status_code == 200, r.text
    r = await _call(app, "POST", "/api/device/session/end", bearer=fatma_bearer,
                    body={"session_id": r.json()["session_id"]})
    assert r.status_code == 200
    # Elif is no center: the device's own 403, as with headers.
    r = await _call(app, "GET", "/api/device/invitation", bearer=elif_bearer)
    assert r.status_code == 403


@pytest.mark.anyio
async def test_invite_info_and_one_404(env):
    token = await _invite(env, env["fatma"])
    r = await _call(env["app"], "GET", f"/api/invites/{token}")
    assert r.json() == {"circle_name": "Test Family", "person_name": "Fatma", "role": "center"}

    await _call(env["app"], "DELETE", f"/api/admin/invites/{env['fatma'].id}", person=env["ayse"])
    bodies = set()
    for t in (token, token[:-1] + ("A" if token[-1] != "A" else "B"), "unknown"):
        for method, url in (("GET", f"/api/invites/{t}"), ("POST", f"/api/invites/{t}/accept")):
            r = await _call(env["app"], method, url)
            assert r.status_code == 404
            bodies.add(r.text)
    assert len(bodies) == 1


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_revoked_link_and_its_sessions_stop_working(env):
    app = env["app"]
    token = await _invite(env, env["elif_"])
    a, b = await _accept(env, token), await _accept(env, token)
    r = await _call(app, "DELETE", f"/api/admin/invites/{env['elif_'].id}", person=env["ayse"])
    assert r.status_code == 200
    for bearer in (a, b):
        r = await _call(app, "GET", "/api/feed", bearer=bearer)
        assert r.status_code == 401 and r.json()["detail"] == SIGN_IN_REQUIRED
    assert (await _call(app, "POST", f"/api/invites/{token}/accept")).status_code == 404
    # Nothing left to revoke.
    r = await _call(app, "DELETE", f"/api/admin/invites/{env['elif_'].id}", person=env["ayse"])
    assert r.status_code == 404


@pytest.mark.anyio
async def test_new_link_revokes_the_old_one(env):
    app = env["app"]
    old = await _invite(env, env["elif_"])
    old_bearer = await _accept(env, old)
    new = await _invite(env, env["elif_"])
    assert (await _call(app, "GET", f"/api/invites/{old}")).status_code == 404
    assert (await _call(app, "GET", "/api/feed", bearer=old_bearer)).status_code == 401
    assert (await _call(app, "GET", "/api/feed", bearer=await _accept(env, new))).status_code == 200
    env["db"].expire_all()
    active = env["db"].query(InviteLink).filter(InviteLink.revoked_at.is_(None)).all()
    assert len(active) == 1


@pytest.mark.anyio
async def test_removing_a_member_revokes_their_link(env):
    app = env["app"]
    deniz = _person(env["db"], env["circle"], "Deniz")
    token = await _invite(env, deniz)
    bearer = await _accept(env, token)
    r = await _call(app, "DELETE", f"/api/admin/members/{deniz.id}", person=env["ayse"])
    assert r.status_code == 200
    assert (await _call(app, "GET", f"/api/invites/{token}")).status_code == 404
    assert (await _call(app, "GET", "/api/feed", bearer=bearer)).status_code == 401


@pytest.mark.anyio
async def test_logout_revokes_only_that_session(env):
    app = env["app"]
    token = await _invite(env, env["elif_"])
    a, b = await _accept(env, token), await _accept(env, token)
    r = await _call(app, "POST", "/api/auth/logout", bearer=a)
    assert r.status_code == 200
    assert (await _call(app, "GET", "/api/feed", bearer=a)).status_code == 401
    assert (await _call(app, "GET", "/api/feed", bearer=b)).status_code == 200
    # Demo headers have no session to end.
    assert (await _call(app, "POST", "/api/auth/logout", person=env["elif_"])).status_code == 401


@pytest.mark.anyio
async def test_only_an_admin_manages_links(env):
    app = env["app"]
    r = await _call(app, "POST", "/api/admin/invites", person=env["elif_"], body={"person_id": env["elif_"].id})
    assert r.status_code == 403
    r = await _call(app, "POST", "/api/admin/invites", person=env["fatma"], body={"person_id": env["fatma"].id})
    assert r.status_code == 403
    await _invite(env, env["elif_"])
    r = await _call(app, "DELETE", f"/api/admin/invites/{env['elif_'].id}", person=env["elif_"])
    assert r.status_code == 403
    # Someone outside the circle gets no link.
    r = await _call(app, "POST", "/api/admin/invites", person=env["ayse"], body={"person_id": "nobody"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Another circle's bearer
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_other_circles_bearer_is_403_here(env, monkeypatch):
    app = env["app"]
    monkeypatch.delenv("EVOCA_DEMO_MODE")
    r = await _call(app, "POST", "/api/circles", body=_new_circle_body())
    assert r.status_code == 200
    other = r.json()
    here = env["circle"].id

    r = await _call(app, "GET", "/api/feed", bearer=other["session_token"], circle=here)
    assert r.status_code == 403
    # Same body as a member of another circle asking for this one with demo headers.
    monkeypatch.setenv("EVOCA_DEMO_MODE", "1")
    ref = await _call(app, "GET", "/api/feed", person=env["db"].get(type(env["fatma"]), other["creator_id"]),
                      circle=here)
    assert (ref.status_code, ref.text) == (403, r.text)
    monkeypatch.delenv("EVOCA_DEMO_MODE")

    for method, url in (("GET", "/api/circle"), ("GET", "/api/admin/sensitive-topics"),
                        ("GET", "/api/device/invitation"), ("GET", "/api/questions/mine")):
        assert (await _call(app, method, url, bearer=other["session_token"], circle=here)).status_code == 403
    # Without X-Circle-Id it works, but in its own circle only.
    r = await _call(app, "GET", "/api/circle", bearer=other["session_token"])
    assert r.status_code == 200 and r.json()["circle"]["id"] == other["circle_id"]
    r = await _call(app, "GET", f"/api/lifeline/{env['fatma'].id}", bearer=other["session_token"])
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Outside demo mode
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_outside_demo_mode_headers_are_401_and_picker_is_404(env, monkeypatch):
    app = env["app"]
    monkeypatch.delenv("EVOCA_DEMO_MODE")
    bodies = set()
    for kw in ({"person": env["elif_"]}, {"person": env["elif_"], "circle": env["circle"].id}, {},
               {"bearer": "not-a-token"}):
        for method, url in (("GET", "/api/feed"), ("GET", "/api/device/invitation"),
                            ("GET", "/api/admin/sensitive-topics"), ("GET", "/api/audio/x?start=0&end=10"),
                            ("GET", "/api/photos/x"), ("POST", "/api/auth/logout")):
            r = await _call(app, method, url, **kw)
            assert r.status_code == 401, (url, kw, r.text)
            bodies.add(r.text)
    assert len(bodies) == 1
    async with _client(app) as c:
        r = await c.get("/api/feed", headers={"authorization": "Basic abc"})
        assert r.status_code == 401
        assert (await c.get(f"/api/people?circle_id={env['circle'].id}")).status_code == 404
        assert (await c.get("/api/circles/demo")).status_code == 404


@pytest.mark.anyio
async def test_new_circle_signs_the_creator_in(env, monkeypatch):
    app = env["app"]
    monkeypatch.delenv("EVOCA_DEMO_MODE")
    r = await _call(app, "POST", "/api/circles", body=_new_circle_body())
    out = r.json()
    me = await _call(app, "GET", "/api/circle", bearer=out["session_token"])
    assert me.json()["me"] == {"id": out["creator_id"], "name": "Selin Demir", "role": "admin",
                               "relation_to_center": "daughter"}
    # Their own link, for another device.
    token = out["invite_url_path"].removeprefix("/join/")
    info = await _call(app, "GET", f"/api/invites/{token}")
    assert info.json() == {"circle_name": "The Demir Family", "person_name": "Selin Demir", "role": "admin"}
    r = await _call(app, "POST", f"/api/invites/{token}/accept")
    assert r.json()["person_id"] == out["creator_id"] and r.json()["circle_id"] == out["circle_id"]
    # The admin invites the center with the bearer.
    r = await _call(app, "POST", "/api/admin/invites", bearer=out["session_token"],
                    body={"person_id": out["center_id"]})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Access log
# ---------------------------------------------------------------------------

def test_access_log_redacts_invite_tokens():
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                               ("127.0.0.1:5000", "POST", "/api/invites/s3cr3tTok_-en/accept", "1.1", 200), None)
    RedactTokens().filter(record)
    line = record.getMessage()
    assert "s3cr3tTok_-en" not in line and "/api/invites/<redacted>/accept" in line


def test_app_installs_the_access_log_filter():
    import server.app  # noqa: F401
    assert any(isinstance(f, RedactTokens) for f in logging.getLogger("uvicorn.access").filters)


@pytest.mark.anyio
async def test_revoked_link_fails_closed_even_if_a_session_was_missed(env):
    """A session made while its link was being revoked (a race) still stops working."""
    token = await _invite(env, env["elif_"])
    bearer = await _accept(env, token)
    db = env["db"]
    db.expire_all()
    db.query(InviteLink).update({InviteLink.revoked_at: "2026-01-01T00:00:00+00:00"})   # sessions untouched
    db.commit()
    assert (await _call(env["app"], "GET", "/api/feed", bearer=bearer)).status_code == 401


@pytest.mark.anyio
async def test_audio_and_tts_of_another_circle_are_403_with_a_bearer(env):
    """Fatma took part in this circle's session; signed in to another circle, she cannot hear it."""
    app, db, fatma = env["app"], env["db"], env["fatma"]
    r = await _call(app, "POST", "/api/device/session/start", person=fatma)
    sid, tts_url = r.json()["session_id"], r.json()["reply_audio_url"]
    await _call(app, "POST", "/api/device/session/end", person=fatma, body={"session_id": sid})
    assert (await _call(app, "GET", f"/api/audio/{sid}?start=0&end=100", person=fatma)).status_code == 200

    other = (await _call(app, "POST", "/api/circles", body=_new_circle_body())).json()
    from core.models import Membership
    db.add(Membership(person_id=fatma.id, circle_id=other["circle_id"], role=Role.member,
                      relation_to_center="cousin"))
    db.commit()
    r = await _call(app, "POST", "/api/admin/invites", bearer=other["session_token"], body={"person_id": fatma.id})
    fatma_there = await _accept(env, r.json()["token"])

    for url in (f"/api/audio/{sid}?start=0&end=100", tts_url):
        r = await _call(app, "GET", url, bearer=fatma_there)
        assert r.status_code == 403, url
        ref = await _call(app, "GET", url, person=env["elif_"])   # any other refusal
        assert r.text == ref.text


@pytest.mark.anyio
async def test_cors_preflight_allows_the_bearer_header_from_the_web_origin():
    from server.app import app
    async with _client(app) as c:
        r = await c.options("/api/feed", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization, x-circle-id, content-type",
        })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    allowed = {h.strip().lower() for h in r.headers["access-control-allow-headers"].split(",")}
    assert {"authorization", "x-circle-id", "content-type"} <= allowed
    assert "GET" in r.headers["access-control-allow-methods"]


# ---------------------------------------------------------------------------
# has_invite on the members list (admins only)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_members_list_tells_admins_who_has_an_active_link(env):
    """has_invite is true while a member has an unrevoked link, on any device; members never see it."""
    app, ayse, elif_, fatma = env["app"], env["ayse"], env["elif_"], env["fatma"]

    def flags(body):
        return {m["id"]: m.get("has_invite") for m in body["members"]}

    before = (await _call(app, "GET", "/api/circle", person=ayse)).json()
    assert flags(before) == {fatma.id: False, elif_.id: False, ayse.id: False}

    await _invite(env, fatma)
    await _invite(env, elif_)
    after = (await _call(app, "GET", "/api/circle", person=ayse)).json()
    assert flags(after) == {fatma.id: True, elif_.id: True, ayse.id: False}

    r = await _call(app, "DELETE", f"/api/admin/invites/{elif_.id}", person=ayse)
    assert r.status_code == 200, r.text
    revoked = (await _call(app, "GET", "/api/circle", person=ayse)).json()
    assert flags(revoked)[elif_.id] is False

    as_member = (await _call(app, "GET", "/api/circle", person=elif_)).json()
    assert all("has_invite" not in m for m in as_member["members"])
