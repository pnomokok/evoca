"""
Admin endpoints (server/routers/admin.py, core/services/admin.py).

Uses the test_app fixture from tests/test_api.py (temp SQLite DB, Fatma as the
circle center, Elif as a plain member) and adds Ayse as the admin, one family
topic and one topic Fatma refused herself (source "speaker").

Coverage
--------
- The admin lists, adds and deletes family topics; the member and the center
  get the same 403 on every endpoint.
- A speaker topic is never listed, and its id gets the same 404 as a missing one.
- An added topic filters a new POST /api/questions.
- Empty text or text with no word the matcher can use: 400.
- The same text again (any case) returns the existing topic; a speaker topic's
  text is added as a new family topic (never its id).
- Deleting a topic leaves the questions it filtered filtered.
- PATCH chat_time, then a scheduler pass at the new time creates the
  invitation; a second change the same day creates nothing. Bad time or
  timezone: 400.
"""

from __future__ import annotations

import pytest

from core.clock import now_utc
from core.enums import QuestionStatus, Role, TopicSource
from core.models import Invitation, Question, SensitiveTopic
from core.services.invitations import run_invitations

from tests.test_api import _client, anyio_backend, test_app  # noqa: F401  (fixtures)
from tests.test_panel_stories import _person

URL = "/api/admin/sensitive-topics"
FAMILY_TOPIC = "1977 traffic accident"
SPEAKER_TOPIC = "Zuleyhanur"


@pytest.fixture
def adm(test_app, monkeypatch):
    app, db, fatma, elif_, circle, *_ = test_app
    import server.routers.admin as adm_r
    from core.db import SessionLocal

    monkeypatch.setattr(adm_r, "SessionLocal", SessionLocal)   # patched by test_app
    ayse = _person(db, circle, "Ayse", role=Role.admin, relation="daughter")
    family = SensitiveTopic(circle_id=circle.id, text=FAMILY_TOPIC, source=TopicSource.family,
                            added_by=ayse.id, created_at=now_utc().isoformat())
    speaker = SensitiveTopic(circle_id=circle.id, text=SPEAKER_TOPIC, source=TopicSource.speaker,
                             added_by=fatma.id, created_at=now_utc().isoformat())
    db.add_all([family, speaker]); db.commit()
    return dict(app=app, db=db, fatma=fatma, elif_=elif_, ayse=ayse, circle=circle,
                family=family, speaker=speaker)


async def _req(app, method, url, person, body=None):
    async with _client(app) as c:
        return await c.request(method, url, headers={"x-person-id": person.id}, json=body)


# ---------------------------------------------------------------------------
# Sensitive topics
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_admin_lists_only_family_topics(adm):
    r = await _req(adm["app"], "GET", URL, adm["ayse"])
    assert r.status_code == 200
    assert r.json() == [{"id": adm["family"].id, "text": FAMILY_TOPIC, "added_by": adm["ayse"].id,
                         "created_at": adm["family"].created_at}]
    assert SPEAKER_TOPIC not in r.text and adm["speaker"].id not in r.text


@pytest.mark.anyio
@pytest.mark.parametrize("who", ["elif_", "fatma"])
async def test_member_and_center_get_the_same_403(adm, who):
    viewer = adm[who]
    calls = [("GET", URL, None), ("POST", URL, {"text": "Selim's debt"}),
             ("DELETE", f"{URL}/{adm['family'].id}", None),
             ("DELETE", f"{URL}/{adm['speaker'].id}", None),
             ("PATCH", "/api/admin/circle", {"chat_time": "09:00"})]
    details = set()
    for method, url, body in calls:
        r = await _req(adm["app"], method, url, viewer, body)
        assert r.status_code == 403, (method, url, r.text)
        details.add(r.json()["detail"])
    assert len(details) == 1
    adm["db"].expire_all()
    assert adm["db"].query(SensitiveTopic).count() == 2


@pytest.mark.anyio
async def test_speaker_topic_id_gets_the_missing_404(adm):
    r_speaker = await _req(adm["app"], "DELETE", f"{URL}/{adm['speaker'].id}", adm["ayse"])
    r_missing = await _req(adm["app"], "DELETE", f"{URL}/no-such-id", adm["ayse"])
    assert r_speaker.status_code == r_missing.status_code == 404
    assert r_speaker.json() == r_missing.json()
    adm["db"].expire_all()
    assert adm["db"].get(SensitiveTopic, adm["speaker"].id) is not None


@pytest.mark.anyio
async def test_added_topic_filters_a_new_question(adm):
    r = await _req(adm["app"], "POST", URL, adm["ayse"], {"text": "  Selim's   debt "})
    assert r.status_code == 200
    topic = r.json()
    assert topic["text"] == "Selim's debt" and topic["added_by"] == adm["ayse"].id
    adm["db"].expire_all()
    assert adm["db"].get(SensitiveTopic, topic["id"]).source == TopicSource.family

    q = await _req(adm["app"], "POST", "/api/questions", adm["elif_"],
                   {"target_person_id": adm["fatma"].id, "text": "Who paid Selim's debt?"})
    assert q.json()["status"] == "filtered"

    listed = (await _req(adm["app"], "GET", URL, adm["ayse"])).json()
    assert [t["id"] for t in listed] == [adm["family"].id, topic["id"]]


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["", "   ", "the war", "tell me about it"])
async def test_text_without_a_usable_word_is_400(adm, text):
    r = await _req(adm["app"], "POST", URL, adm["ayse"], {"text": text})
    assert r.status_code == 400
    adm["db"].expire_all()
    assert adm["db"].query(SensitiveTopic).count() == 2


@pytest.mark.anyio
async def test_duplicate_text_returns_the_existing_topic(adm):
    r = await _req(adm["app"], "POST", URL, adm["ayse"], {"text": "1977 TRAFFIC  Accident"})
    assert r.status_code == 200
    assert r.json()["id"] == adm["family"].id
    adm["db"].expire_all()
    assert adm["db"].query(SensitiveTopic).count() == 2


@pytest.mark.anyio
async def test_speaker_topic_text_is_added_as_a_new_family_topic(adm):
    r = await _req(adm["app"], "POST", URL, adm["ayse"], {"text": SPEAKER_TOPIC.lower()})
    assert r.status_code == 200
    topic = r.json()
    assert topic["id"] != adm["speaker"].id and topic["added_by"] == adm["ayse"].id
    adm["db"].expire_all()
    assert adm["db"].get(SensitiveTopic, topic["id"]).source == TopicSource.family
    assert adm["db"].query(SensitiveTopic).count() == 3


@pytest.mark.anyio
async def test_delete_keeps_already_filtered_questions_filtered(adm):
    q = await _req(adm["app"], "POST", "/api/questions", adm["elif_"],
                   {"target_person_id": adm["fatma"].id, "text": "What happened in the accident?"})
    assert q.json()["status"] == "filtered"

    r = await _req(adm["app"], "DELETE", f"{URL}/{adm['family'].id}", adm["ayse"])
    assert r.status_code == 200
    assert (await _req(adm["app"], "GET", URL, adm["ayse"])).json() == []

    adm["db"].expire_all()
    saved = adm["db"].query(Question).filter(Question.text == "What happened in the accident?").one()
    assert saved.status == QuestionStatus.filtered


# ---------------------------------------------------------------------------
# PATCH /api/admin/circle
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_new_chat_time_is_used_by_the_next_scheduler_pass(adm, monkeypatch):
    db, circle = adm["db"], adm["circle"]
    day = "2026-12-01"                                       # no invitation seeded for this day
    monkeypatch.setenv("DEMO_NOW", f"{day}T06:30:00+00:00")  # 09:30 in Istanbul, before 10:00
    assert run_invitations(db) == []

    r = await _req(adm["app"], "PATCH", "/api/admin/circle", adm["ayse"], {"chat_time": "09:00"})
    assert r.status_code == 200
    assert r.json() == {"id": circle.id, "chat_time": "09:00", "timezone": "Europe/Istanbul"}

    db.expire_all()
    created = run_invitations(db)
    assert len(created) == 1
    assert db.get(Invitation, created[0]).date == day

    # Today's invitation exists: another change creates nothing more today.
    r = await _req(adm["app"], "PATCH", "/api/admin/circle", adm["ayse"],
                   {"chat_time": "09:15", "timezone": "Europe/Berlin"})
    assert r.json()["timezone"] == "Europe/Berlin"
    db.expire_all()
    assert run_invitations(db) == []


@pytest.mark.anyio
@pytest.mark.parametrize("body", [
    {"chat_time": "25:00"}, {"chat_time": "9:00"}, {"chat_time": "09:60"}, {"chat_time": ""},
    {"timezone": "Mars/Olympus"}, {"timezone": ""}, {"timezone": "../etc/passwd"},
    {"chat_time": "09:00", "timezone": "Nowhere"},
])
async def test_bad_time_or_timezone_is_400(adm, body):
    r = await _req(adm["app"], "PATCH", "/api/admin/circle", adm["ayse"], body)
    assert r.status_code == 400
    adm["db"].expire_all()
    circle = adm["db"].get(type(adm["circle"]), adm["circle"].id)
    assert (circle.chat_time, circle.timezone) == ("10:00", "Europe/Istanbul")
