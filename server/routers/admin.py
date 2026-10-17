"""
Admin REST endpoints.

GET    /api/admin/sensitive-topics
POST   /api/admin/sensitive-topics
DELETE /api/admin/sensitive-topics/{id}
PATCH  /api/admin/circle

The viewer comes from X-Person-Id; every endpoint needs role admin in the
viewer's circle, and anyone else gets the same 403. Logic lives in
core.services.admin: only family topics are ever listed, and a speaker topic's
id gets the same 404 as a missing one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from core.db import SessionLocal
from core.services import admin as admin_svc
from server.routers.panel import _resolve_panel_viewer

router = APIRouter()


def _admin_call(fn, x_person_id: str, *args):
    """Resolve the viewer, run an admin service function, map its errors to HTTP."""
    with SessionLocal() as db:
        person_id, circle_id = _resolve_panel_viewer(x_person_id, db)
        try:
            return fn(db, person_id, circle_id, *args)
        except admin_svc.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except admin_svc.Forbidden as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/admin/sensitive-topics")
async def get_sensitive_topics(
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """The family's sensitive topics. Matches GET_admin_sensitive_topics.json."""
    return _admin_call(admin_svc.list_family_topics, x_person_id)


class TopicRequest(BaseModel):
    text: str


@router.post("/api/admin/sensitive-topics")
async def post_sensitive_topic(
    body: TopicRequest,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Add a family topic; the same text again returns the existing topic."""
    return _admin_call(admin_svc.add_family_topic, x_person_id, body.text)


@router.delete("/api/admin/sensitive-topics/{topic_id}")
async def delete_sensitive_topic(
    topic_id: str,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Delete a family topic. Questions it already filtered stay filtered."""
    return _admin_call(admin_svc.delete_family_topic, x_person_id, topic_id)


class CirclePatchRequest(BaseModel):
    chat_time: str | None = None
    timezone: str | None = None


@router.patch("/api/admin/circle")
async def patch_circle(
    body: CirclePatchRequest,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Change chat_time and/or timezone; the scheduler uses them on its next pass."""
    return _admin_call(admin_svc.update_circle_settings, x_person_id, body.chat_time, body.timezone)
