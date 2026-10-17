"""
Panel REST endpoints.

GET    /api/people                (demo only: the person picker, no header)
GET    /api/circle
GET    /api/feed
POST   /api/questions
GET    /api/lifeline/{person_id}
GET    /api/stories/{id}
GET    /api/stories/{id}/playlist
POST   /api/stories/{id}/reactions
PATCH  /api/stories/{id}/subjects/{person_id}
PATCH  /api/stories/{id}
DELETE /api/links/{id}

Story logic lives in core.services.stories; every story passes can_see() there.
A story the viewer cannot see gets the same 404 as a missing one.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.clock import now_utc
from core.db import SessionLocal
from core.enums import LifePeriod, QuestionSource, QuestionStatus, TopicSource
from core.models import Circle, Membership, Person, Question, SensitiveTopic
from core.services import stories as story_svc
from core.services.feed import build_feed
from core.services.questions import find_duplicate
from core.services.session_tools import _matches_sensitive_topic

log = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Identity helper (panel: any circle member, not just center)
# ---------------------------------------------------------------------------

def _resolve_panel_viewer(x_person_id: str, db) -> tuple[str, str]:
    """Return (person_id, circle_id) for a panel viewer.

    The panel caller can be any member.  We pick the first circle they belong
    to (hackathon: one circle exists).
    Raises HTTP 403 if not a member of any circle.
    """
    if not x_person_id:
        raise HTTPException(status_code=403, detail="X-Person-Id header required.")

    m = (
        db.query(Membership)
        .filter(Membership.person_id == x_person_id)
        .first()
    )
    if m is None:
        raise HTTPException(status_code=403, detail="Not a member of any circle.")
    return x_person_id, m.circle_id


# ---------------------------------------------------------------------------
# GET /api/people  (DEMO ONLY)
# ---------------------------------------------------------------------------

@router.get("/api/people")
async def get_people():
    """Everyone and their circles, for the panel's password-less person picker.

    DEMO ONLY: no header and no access check, by design (PROJECT.md
    "Bilinen sınırlar"). Returns names and roles only, never story data.
    """
    with SessionLocal() as db:
        people = db.query(Person).order_by(Person.name).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "circles": [
                    {"circle_id": m.circle_id, "role": m.role}
                    for m in db.query(Membership).filter(Membership.person_id == p.id).all()
                ],
            }
            for p in people
        ]


# ---------------------------------------------------------------------------
# GET /api/circle
# ---------------------------------------------------------------------------

@router.get("/api/circle")
async def get_circle(
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Return circle info and full member list, matching GET_circle.json."""
    with SessionLocal() as db:
        person_id, circle_id = _resolve_panel_viewer(x_person_id, db)

        circle = db.get(Circle, circle_id)
        if circle is None:
            raise HTTPException(status_code=404, detail="Circle not found.")

        viewer_membership = (
            db.query(Membership)
            .filter(Membership.person_id == person_id, Membership.circle_id == circle_id)
            .first()
        )
        viewer_person = db.get(Person, person_id)

        memberships = (
            db.query(Membership)
            .filter(Membership.circle_id == circle_id)
            .all()
        )
        members = []
        for m in memberships:
            p = db.get(Person, m.person_id)
            if p:
                members.append({
                    "id": p.id,
                    "name": p.name,
                    "birth_year": p.birth_year,
                    "role": m.role,
                    "relation_to_center": m.relation_to_center,
                })

        return {
            "circle": {
                "id": circle.id,
                "name": circle.name,
                "center_person_id": circle.center_person_id,
                "status": circle.status,
                "chat_time": circle.chat_time,
                "timezone": circle.timezone,
            },
            "me": {
                "id": person_id,
                "name": viewer_person.name if viewer_person else None,
                "role": viewer_membership.role if viewer_membership else None,
                "relation_to_center": viewer_membership.relation_to_center if viewer_membership else None,
            },
            "members": members,
        }


# ---------------------------------------------------------------------------
# GET /api/feed
# ---------------------------------------------------------------------------

@router.get("/api/feed")
async def get_feed(
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Answers to the viewer's own questions and published stories, newest first.

    Matches GET_feed.json; filtered by can_see() in core.services.feed.
    """
    with SessionLocal() as db:
        person_id, circle_id = _resolve_panel_viewer(x_person_id, db)
        return build_feed(db, person_id, circle_id)


# ---------------------------------------------------------------------------
# POST /api/questions
# ---------------------------------------------------------------------------

class QuestionRequest(BaseModel):
    target_person_id: str
    text: str
    period: str | None = None


@router.post("/api/questions")
async def post_question(
    body: QuestionRequest,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Add a family question. Returns 200 with status=waiting or status=filtered.

    Matches POST_questions_accepted.json and POST_questions_filtered.json.
    A filtered question returns HTTP 200 (not an error); the message never
    reveals which sensitive topic matched. Like every filtered question, it is
    kept with status "filtered" (docs/PROJECT.md "Hassas konular"). If only a
    topic the center refused herself (source "speaker") matches, the response
    is the normal accepted one with status "waiting": a filtered message would
    tell the asker that the center refused something (like a declined question,
    it looks unanswered). The asker's own open question with the same text
    (case, punctuation and a leading "Grandma,"/"Grandpa," aside; waiting,
    asked, declined or speaker-filtered, all shown as waiting) is returned
    instead of a new copy.
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Question text is required.")
    if body.period is not None and body.period not in {p.value for p in LifePeriod}:
        raise HTTPException(status_code=400, detail="Invalid period.")

    with SessionLocal() as db:
        person_id, circle_id = _resolve_panel_viewer(x_person_id, db)

        # Verify target is in the same circle.
        target_m = (
            db.query(Membership)
            .filter(
                Membership.person_id == body.target_person_id,
                Membership.circle_id == circle_id,
            )
            .first()
        )
        if target_m is None:
            raise HTTPException(
                status_code=400,
                detail="Target person is not in your circle.",
            )

        duplicate = find_duplicate(db, circle_id, person_id, body.target_person_id, body.text)
        if duplicate is not None:
            return _accepted(duplicate)

        # Sensitive-topic check — reuse the same matcher from session_tools.
        topics = (
            db.query(SensitiveTopic)
            .filter(SensitiveTopic.circle_id == circle_id)
            .all()
        )
        matched = [t for t in topics if _matches_sensitive_topic(body.text, t.text)]
        filtered = bool(matched)
        family_match = any(t.source != TopicSource.speaker for t in matched)

        # Save the question; a filtered one is kept but never asked.
        q = Question(
            circle_id=circle_id,
            target_person_id=body.target_person_id,
            asker_id=person_id,
            text=body.text.strip(),
            source=QuestionSource.family,
            period=body.period,
            status=QuestionStatus.filtered if filtered else QuestionStatus.waiting,
            answer=None,
            created_at=now_utc().isoformat(),
        )
        db.add(q)
        db.commit()

        if family_match:
            return {
                "status": "filtered",
                "question": None,
                "message": (
                    "This question touches a topic the family asked Evoca not "
                    "to bring up. It was not sent."
                ),
            }

        return _accepted(q)


def _accepted(q: Question) -> dict:
    return {
        "status": "waiting",
        "question": {
            "id": q.id,
            "circle_id": q.circle_id,
            "target_person_id": q.target_person_id,
            "asker_id": q.asker_id,
            "text": q.text,
            "source": q.source,
            "period": q.period,
            "status": QuestionStatus.waiting,   # even when filtered by a speaker topic
            "answer": q.answer,
            "created_at": q.created_at,
        },
    }


# ---------------------------------------------------------------------------
# Stories: lifeline, story page, playlist, reactions, corrections, links
# ---------------------------------------------------------------------------

def _story_call(fn, x_person_id: str, *args):
    """Resolve the viewer, run a story service function, map its errors to HTTP."""
    with SessionLocal() as db:
        person_id, _ = _resolve_panel_viewer(x_person_id, db)
        try:
            return fn(db, person_id, *args)
        except story_svc.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except story_svc.Forbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/lifeline/{person_id}")
async def get_lifeline(
    person_id: str,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Stories about person_id the viewer can see, by period. Matches GET_lifeline_person_fatma.json."""
    return _story_call(story_svc.build_lifeline, x_person_id, person_id)


@router.get("/api/stories/{story_id}")
async def get_story(
    story_id: str,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """The story page. Matches GET_story_mulberry.json."""
    return _story_call(story_svc.build_story, x_person_id, story_id)


@router.get("/api/stories/{story_id}/playlist")
async def get_story_playlist(
    story_id: str,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Listen from the start: the story and its visible direct links. Matches GET_story_mulberry_playlist.json."""
    return _story_call(story_svc.build_playlist, x_person_id, story_id)


class ReactionRequest(BaseModel):
    emoji: str
    action: str


@router.post("/api/stories/{story_id}/reactions")
async def post_story_reaction(
    story_id: str,
    body: ReactionRequest,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Add or remove the viewer's emoji. Matches POST_story_reactions.json (no counts)."""
    return _story_call(story_svc.set_reaction, x_person_id, story_id, body.emoji, body.action)


class PeriodRequest(BaseModel):
    period: str


@router.patch("/api/stories/{story_id}/subjects/{person_id}")
async def patch_story_subject(
    story_id: str,
    person_id: str,
    body: PeriodRequest,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Family period correction (period_source = family). Returns the updated subject."""
    return _story_call(story_svc.correct_period, x_person_id, story_id, person_id, body.period)


class StoryPatchRequest(BaseModel):
    access: str | None = None
    hidden: bool | None = None


@router.patch("/api/stories/{story_id}")
async def patch_story(
    story_id: str,
    body: StoryPatchRequest,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Change access (teller) or hide (teller, subject, center, admin). Hiding is final."""
    return _story_call(story_svc.update_story, x_person_id, story_id, body.access, body.hidden)


@router.delete("/api/links/{link_id}")
async def delete_link(
    link_id: str,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Mark a wrong link removed; the viewer must see both stories."""
    return _story_call(story_svc.remove_link, x_person_id, link_id)
