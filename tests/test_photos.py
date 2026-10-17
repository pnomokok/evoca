"""
Story photos (core/services/photos.py, server/routers/photos.py) and lifeline years.

Uses the world fixture from tests/test_panel_stories.py: Fatma (center) told
"The Mulberry Tree"; Elif, Ali, Bora are members, Ayse is the admin.

Coverage: the teller, a subject and an admin can upload, a plain member who is
not a subject cannot; an invisible story gives the same 404 as a missing one;
wrong type, too big, broken image and a long caption are 400; EXIF and GPS are
gone from the stored file, which is a re-encoded JPEG of at most 1600 px under
a server-chosen name; a replacement deletes the old file; delete permissions;
GET /api/photos is 404 for a viewer who cannot see the story (private, pending
for a member, hidden even for the teller) and Cache-Control: private, no-store otherwise;
photo fields appear in story, feed and lifeline only when the story is visible;
lifeline years from birth_year, null without it.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

import core.services.photos as photo_svc
from core.enums import AccessType, StoryStatus
from core.models import Membership, Person, StoryPhoto
from core.services.stories import PERIOD_AGES, period_years
from tests.test_api import _client, anyio_backend, test_app  # noqa: F401  (fixtures)
from tests.test_panel_stories import _story, world  # noqa: F401

CAMERA = "SecretCam 3000"


def _image(fmt="JPEG", size=(2400, 1200), exif=True, mode="RGB") -> bytes:
    img = Image.new(mode, size, (200, 120, 40) if mode == "RGB" else (200, 120, 40, 128))
    buf = io.BytesIO()
    kw = {}
    if exif and fmt in ("JPEG", "WEBP", "PNG"):
        e = Image.Exif()
        e[0x010F] = CAMERA                                 # Make
        e[0x0112] = 1                                      # Orientation
        e[0x8825] = {1: "N", 2: (41.0, 0.0, 51.0), 3: "E", 4: (29.0, 1.0, 2.0)}   # GPS
        kw["exif"] = e.tobytes()
    img.save(buf, format=fmt, **kw)
    return buf.getvalue()


@pytest.fixture
def photos(world, tmp_path, monkeypatch):
    monkeypatch.setattr(photo_svc, "PHOTO_DIR", tmp_path / "photos")
    return world


async def _upload(app, story_id, person, data=None, caption=None, name="x.jpg", ctype="image/jpeg"):
    form = {"caption": caption} if caption is not None else {}
    async with _client(app) as c:
        return await c.post(f"/api/stories/{story_id}/photo", headers={"x-person-id": person.id},
                            data=form, files={"image": (name, data or _image(), ctype)})


async def _get(app, url, person):
    async with _client(app) as c:
        return await c.get(url, headers={"x-person-id": person.id})


def _stored(db, story_id) -> StoryPhoto:
    db.expire_all()
    return db.query(StoryPhoto).filter(StoryPhoto.story_id == story_id).one()


# ---------------------------------------------------------------------------
# Upload permissions
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_teller_subject_and_admin_can_upload_plain_member_cannot(photos):
    w = photos
    ali_story = _story(w["db"], w["circle"], w["ali"], [(w["bora"], "youth")], title="Bora's Bike")
    for story, who in [(w["mulberry"], w["fatma"]), (ali_story, w["bora"]), (ali_story, w["ayse"])]:
        r = await _upload(w["app"], story.id, who, caption="Summer 1956")
        assert r.status_code == 200, (who.name, r.text)
        body = r.json()
        assert body["photo_url"] == f"/api/photos/{_stored(w['db'], story.id).id}"
        assert body["photo_caption"] == "Summer 1956"
    # Elif can see the mulberry story but is neither teller, subject nor admin.
    r = await _upload(w["app"], w["mulberry"].id, w["elif_"])
    assert r.status_code == 403
    # One photo per story: Ayse's upload replaced Bora's.
    w["db"].expire_all()
    assert w["db"].query(StoryPhoto).filter(StoryPhoto.story_id == ali_story.id).count() == 1


@pytest.mark.anyio
async def test_invisible_story_is_the_same_404_as_missing(photos):
    w = photos
    secret = _story(w["db"], w["circle"], w["ali"], [(w["elif_"], "youth")], access=AccessType.private,
                    title="Secret")
    hidden = _story(w["db"], w["circle"], w["ali"], [(w["ali"], "youth")], status=StoryStatus.hidden,
                    title="Hidden")
    missing = await _upload(w["app"], "no-such-story", w["elif_"])
    private = await _upload(w["app"], secret.id, w["elif_"])          # a subject, but cannot see it
    hidden_r = await _upload(w["app"], hidden.id, w["ali"])          # even the teller
    assert missing.status_code == private.status_code == hidden_r.status_code == 404
    assert missing.json() == private.json() == hidden_r.json()


@pytest.mark.parametrize("data,name,ctype", [
    (_image("GIF", exif=False), "x.gif", "image/gif"),
    (_image("JPEG")[:400], "x.jpg", "image/jpeg"),                # broken
    (b"not an image at all", "x.jpg", "image/jpeg"),
    (b"", "x.jpg", "image/jpeg"),
])
@pytest.mark.anyio
async def test_bad_images_are_400(photos, data, name, ctype):
    w = photos
    async with _client(w["app"]) as c:
        r = await c.post(f"/api/stories/{w['mulberry'].id}/photo", headers={"x-person-id": w["fatma"].id},
                         files={"image": (name, data, ctype)})
    assert r.status_code == 400
    assert not (photo_svc.PHOTO_DIR.exists() and any(photo_svc.PHOTO_DIR.iterdir()))


@pytest.mark.anyio
async def test_too_many_pixels_is_400_before_decoding(photos, monkeypatch):
    w = photos
    bomb = _image("PNG", size=(6000, 5000), exif=False)        # 30 MP, a few KB when compressed
    assert len(bomb) < photo_svc.MAX_BYTES
    monkeypatch.setattr(Image.Image, "load", lambda self: pytest.fail("decoded a too-large image"))
    r = await _upload(w["app"], w["mulberry"].id, w["fatma"], data=bomb, name="x.png", ctype="image/png")
    assert r.status_code == 400
    assert not (photo_svc.PHOTO_DIR.exists() and any(photo_svc.PHOTO_DIR.iterdir()))


@pytest.mark.anyio
async def test_oversized_body_refused_before_parsing(photos):
    w = photos
    async with _client(w["app"]) as c:   # no header either: refused before anything else
        r = await c.post(f"/api/stories/{w['mulberry'].id}/photo",
                         files={"image": ("x.jpg", b"\x00" * (photo_svc.MAX_BYTES + 128 * 1024), "image/jpeg")})
    assert r.status_code == 400 and "5 MB" in r.json()["detail"]


@pytest.mark.anyio
async def test_too_big_and_long_caption_are_400(photos):
    w = photos
    too_big = _image() + b"\x00" * (photo_svc.MAX_BYTES + 1)
    assert (await _upload(w["app"], w["mulberry"].id, w["fatma"], data=too_big)).status_code == 400
    r = await _upload(w["app"], w["mulberry"].id, w["fatma"], caption="x" * 121)
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Stored file
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt,mode", [("JPEG", "RGB"), ("PNG", "RGBA"), ("WEBP", "RGB")])
@pytest.mark.anyio
async def test_stored_file_is_a_clean_resized_jpeg(photos, fmt, mode):
    w = photos
    raw = _image(fmt, mode=mode)
    assert CAMERA.encode() in raw
    r = await _upload(w["app"], w["mulberry"].id, w["fatma"], data=raw, name="../../evil name.png")
    assert r.status_code == 200
    photo = _stored(w["db"], w["mulberry"].id)
    path = Path(photo.path)
    assert path.parent == photo_svc.PHOTO_DIR and path.name == f"{photo.id}.jpg"
    stored = path.read_bytes()
    assert CAMERA.encode() not in stored and b"Exif" not in stored
    with Image.open(io.BytesIO(stored)) as img:
        assert img.format == "JPEG"
        assert max(img.size) == 1600 and img.size == (1600, 800)
        assert len(img.getexif()) == 0
        assert not img.getexif().get_ifd(0x8825)
        assert "exif" not in img.info and "icc_profile" not in img.info


@pytest.mark.anyio
async def test_replacing_deletes_the_old_file(photos):
    w = photos
    await _upload(w["app"], w["mulberry"].id, w["fatma"])
    first = Path(_stored(w["db"], w["mulberry"].id).path)
    assert first.exists()
    await _upload(w["app"], w["mulberry"].id, w["ayse"])
    second = Path(_stored(w["db"], w["mulberry"].id).path)
    assert second.exists() and second != first and not first.exists()
    assert sorted(p.name for p in photo_svc.PHOTO_DIR.iterdir()) == [second.name]


@pytest.mark.anyio
async def test_delete_by_uploader_teller_or_admin_only(photos):
    w = photos
    app, db = w["app"], w["db"]
    story = _story(db, w["circle"], w["ali"], [(w["bora"], "youth"), (w["elif_"], "youth")], title="Trip")

    async def delete(who):
        async with _client(app) as c:
            return await c.delete(f"/api/stories/{story.id}/photo", headers={"x-person-id": who.id})

    for uploader, deleter in [(w["bora"], w["bora"]), (w["bora"], w["ali"]), (w["bora"], w["ayse"])]:
        assert (await _upload(app, story.id, uploader)).status_code == 200
        path = Path(_stored(db, story.id).path)
        assert (await delete(deleter)).status_code == 200
        assert not path.exists()
    # Elif is a subject but did not upload it.
    await _upload(app, story.id, w["bora"])
    assert (await delete(w["elif_"])).status_code == 403
    assert (await delete(w["bora"])).status_code == 200
    assert (await delete(w["bora"])).status_code == 404      # nothing left


# ---------------------------------------------------------------------------
# GET /api/photos/{id}
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_photo_served_only_to_viewers_who_see_the_story(photos):
    w = photos
    app, db = w["app"], w["db"]
    await _upload(app, w["mulberry"].id, w["fatma"])
    url = f"/api/photos/{_stored(db, w['mulberry'].id).id}"
    r = await _get(app, url, w["elif_"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "private, no-store"
    assert r.headers["x-content-type-options"] == "nosniff"

    missing = await _get(app, "/api/photos/no-such-photo", w["elif_"])
    assert missing.status_code == 404

    # Private: only the teller.
    private = _story(db, w["circle"], w["ali"], [(w["ali"], "youth")], title="Private")
    await _upload(app, private.id, w["ali"])
    private_url = f"/api/photos/{_stored(db, private.id).id}"
    assert (await _get(app, private_url, w["ali"])).status_code == 200
    private.access = {"type": AccessType.private, "person_ids": []}
    db.commit()
    for who in (w["elif_"], w["fatma"], w["ayse"]):
        r = await _get(app, private_url, who)
        assert r.status_code == 404 and r.json() == missing.json()
    assert (await _get(app, private_url, w["ali"])).status_code == 200

    # Pending: not for a plain member.
    pending = _story(db, w["circle"], w["ali"], [(w["ali"], "youth")], status=StoryStatus.pending,
                     title="Pending")
    await _upload(app, pending.id, w["ali"])
    pending_url = f"/api/photos/{_stored(db, pending.id).id}"
    assert (await _get(app, pending_url, w["elif_"])).status_code == 404
    assert (await _get(app, pending_url, w["fatma"])).status_code == 200    # the center sees pending

    # Hidden: nobody, not even the teller.
    w["mulberry"].status = StoryStatus.hidden
    db.commit()
    for who in (w["elif_"], w["fatma"], w["ayse"]):
        assert (await _get(app, url, who)).status_code == 404


# ---------------------------------------------------------------------------
# Photo fields in story, feed and lifeline
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_photo_fields_only_when_visible(photos):
    w = photos
    app, db, m = w["app"], w["db"], w["mulberry"]
    await _upload(app, m.id, w["fatma"], caption="The tree in 1955")
    photo_url = f"/api/photos/{_stored(db, m.id).id}"

    story = (await _get(app, f"/api/stories/{m.id}", w["elif_"])).json()
    assert story["photo_url"] == photo_url and story["photo_caption"] == "The tree in 1955"
    feed = (await _get(app, "/api/feed", w["elif_"])).json()
    cards = [i["story"] for i in feed["items"] if i["type"] == "story_published" and i["story"]["id"] == m.id]
    assert cards and cards[0]["photo_url"] == photo_url and cards[0]["photo_caption"] == "The tree in 1955"
    life = (await _get(app, f"/api/lifeline/{w['fatma'].id}", w["elif_"])).json()
    items = [s for p in life["periods"] for s in p["stories"] if s["id"] == m.id]
    assert items and items[0]["photo_url"] == photo_url

    # A story without a photo carries nulls.
    plain = _story(db, w["circle"], w["fatma"], [(w["fatma"], "youth")], title="No Photo")
    body = (await _get(app, f"/api/stories/{plain.id}", w["elif_"])).json()
    assert body["photo_url"] is None and body["photo_caption"] is None

    # Private for Ali: Elif sees no trace of its photo anywhere.
    secret = _story(db, w["circle"], w["fatma"], [(w["fatma"], "youth")], title="Secret Photo")
    await _upload(app, secret.id, w["fatma"], caption="hush")
    secret.access = {"type": AccessType.private, "person_ids": []}
    db.commit()
    secret_url = f"/api/photos/{_stored(db, secret.id).id}"
    for url in ("/api/feed", f"/api/lifeline/{w['fatma'].id}"):
        text = json.dumps((await _get(app, url, w["elif_"])).json())
        assert secret_url not in text and "hush" not in text

    # Hidden: the teller still opens the story, without its photo.
    m.status = StoryStatus.hidden
    db.commit()
    body = (await _get(app, f"/api/stories/{m.id}", w["fatma"])).json()
    assert body["photo_url"] is None and body["photo_caption"] is None
    for who in (w["fatma"], w["elif_"]):
        for url in ("/api/feed", f"/api/lifeline/{w['fatma'].id}"):
            assert photo_url not in json.dumps((await _get(app, url, who)).json())


# ---------------------------------------------------------------------------
# Lifeline years
# ---------------------------------------------------------------------------

def test_period_years_from_birth_year():
    assert period_years(1948, "childhood") == {"from": 1948, "to": 1960}
    assert period_years(1948, "youth") == {"from": 1961, "to": 1970}
    assert period_years(1948, "midlife") == {"from": 1994, "to": 2008}
    assert period_years(1948, "retirement") == {"from": 2009, "to": None}   # open end
    assert period_years(2003, "midlife")["to"] is None                       # beyond this year
    assert period_years(None, "childhood") is None
    assert list(PERIOD_AGES) == ["childhood", "youth", "marriage_early_years", "raising_children",
                                 "midlife", "retirement"]


@pytest.mark.anyio
async def test_lifeline_periods_carry_years(photos):
    w = photos
    life = (await _get(w["app"], f"/api/lifeline/{w['fatma'].id}", w["elif_"])).json()
    years = {p["period"]: p["years"] for p in life["periods"]}
    assert years["childhood"] == {"from": 1948, "to": 1960}
    assert years["retirement"] == {"from": 2009, "to": None}
    unknown = Person(name="Nobody Knows", birth_year=None, language="en")
    w["db"].add(unknown); w["db"].flush()
    w["db"].add(Membership(person_id=unknown.id, circle_id=w["circle"].id, role="member",
                           relation_to_center="cousin"))
    w["db"].commit()
    life = (await _get(w["app"], f"/api/lifeline/{unknown.id}", w["elif_"])).json()
    assert all(p["years"] is None for p in life["periods"])
