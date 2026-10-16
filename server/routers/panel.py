"""
Panel REST endpoints.

GET  /api/circle
POST /api/questions
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.clock import now_utc
from core.db import SessionLocal
from core.enums import QuestionSource, QuestionStatus
from core.models import Circle, Membership, Person, Question
from core.services.session_tools import _matches_sensitive_topic
from core.models import SensitiveTopic

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
    reveals which sensitive topic matched.
    """
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Question text is required.")

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

        # Sensitive-topic check — reuse the same matcher from session_tools.
        topics = (
            db.query(SensitiveTopic)
            .filter(SensitiveTopic.circle_id == circle_id)
            .all()
        )
        for topic in topics:
            if _matches_sensitive_topic(body.text, topic.text):
                return {
                    "status": "filtered",
                    "question": None,
                    "message": (
                        "This question touches a topic the family asked Evoca not "
                        "to bring up. It was not sent."
                    ),
                }

        # Save the question.
        q = Question(
            circle_id=circle_id,
            target_person_id=body.target_person_id,
            asker_id=person_id,
            text=body.text.strip(),
            source=QuestionSource.family,
            period=body.period,
            status=QuestionStatus.waiting,
            answer=None,
            created_at=now_utc().isoformat(),
        )
        db.add(q)
        db.commit()

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
                "status": q.status,
                "answer": q.answer,
                "created_at": q.created_at,
            },
        }
