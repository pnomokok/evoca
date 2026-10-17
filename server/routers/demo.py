"""
Demo controls (docs/PROJECT.md "REST uçları"; Bilinen sınırlar: open to anyone
on the page in demo mode).

GET  /api/demo/clock     {now, offset_hours}
POST /api/demo/advance   {hours} (1-72): move the clock, publish, run invitations
POST /api/demo/reset     rebuild the demo database from the seed; returns the people list

Only with EVOCA_DEMO_MODE=1; otherwise every endpoint is a 404 and nothing
changes. No X-Person-Id header (demo only). The logic is in core.services.demo.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import clock
from core.db import SessionLocal
from core.services import demo as demo_svc
from server.routers.device import _get_store
from server.session_store import SessionStore

log = logging.getLogger(__name__)
router = APIRouter()


def _require_demo_mode() -> None:
    if not clock.demo_mode():
        raise HTTPException(status_code=404, detail="Not Found")


class AdvanceRequest(BaseModel):
    hours: float


@router.get("/api/demo/clock", dependencies=[Depends(_require_demo_mode)])
def get_clock():
    with SessionLocal() as db:
        return demo_svc.clock_state(db)


@router.post("/api/demo/advance", dependencies=[Depends(_require_demo_mode)])
def post_advance(body: AdvanceRequest):
    with SessionLocal() as db:
        try:
            return demo_svc.advance(db, body.hours)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/demo/reset", dependencies=[Depends(_require_demo_mode)])
def post_reset(store: SessionStore = Depends(_get_store)):
    try:
        demo_svc.check_resettable()
    except demo_svc.ResetRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # End live device sessions in memory: their database is about to be rebuilt.
    for live in store.all():
        store.pop(live.session_id)
        try:
            live.db.close()
        except Exception:
            log.exception("Closing live session %s on demo reset failed", live.session_id)
    return demo_svc.reset()
