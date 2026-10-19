"""
Demo controls (docs/ARCHITECTURE.md "REST API"; "Known limits": open to anyone
on the page in demo mode).

GET  /api/demo/clock     {now, offset_hours}
GET  /api/demo/status    {archiving}: is an archive run of the demo circle in flight
POST /api/demo/advance   {hours} (1-72): wait for archive runs of the demo circle (up to
                         90 s), then move the clock, publish, run invitations
POST /api/demo/reset     rebuild the whole demo database from the seed; returns the demo circle's people

Only with EVOCA_DEMO_MODE=1; otherwise every endpoint is a 404 and nothing
changes. No X-Person-Id header (demo only). The logic is in core.services.demo.
"""

from __future__ import annotations

import logging

import anyio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import clock
from core.db import SessionLocal
from core.services import demo as demo_svc
from core.services.circles import NotFound, demo_circle
from server import archive_runs
from server.routers.device import _get_store
from server.session_store import SessionStore

log = logging.getLogger(__name__)
router = APIRouter()

# How long advance waits for the archivist: a story saved after the clock moved
# would start its 24-hour window from the new time.
ARCHIVE_WAIT_S = 90.0


def _demo_circle_id() -> str | None:
    with SessionLocal() as db:
        try:
            return demo_circle(db)["id"]
        except NotFound:
            return None


def _require_demo_mode() -> None:
    if not clock.demo_mode():
        raise HTTPException(status_code=404, detail="Not Found")


class AdvanceRequest(BaseModel):
    hours: float


@router.get("/api/demo/clock", dependencies=[Depends(_require_demo_mode)])
def get_clock():
    with SessionLocal() as db:
        return demo_svc.clock_state(db)


@router.get("/api/demo/status", dependencies=[Depends(_require_demo_mode)])
def get_status():
    """Only whether the demo circle's archivist is running: no ids, no content."""
    circle_id = _demo_circle_id()
    return {"archiving": bool(circle_id) and archive_runs.busy(circle_id)}


def _advance(hours: float) -> dict:
    with SessionLocal() as db:
        return demo_svc.advance(db, hours)


@router.post("/api/demo/advance", dependencies=[Depends(_require_demo_mode)])
async def post_advance(body: AdvanceRequest):
    if not demo_svc.MIN_HOURS <= body.hours <= demo_svc.MAX_HOURS:
        raise HTTPException(status_code=400,
                            detail=f"hours must be between {demo_svc.MIN_HOURS} and {demo_svc.MAX_HOURS}.")
    circle_id = await anyio.to_thread.run_sync(_demo_circle_id)
    waited = bool(circle_id) and archive_runs.busy(circle_id)
    finished = await archive_runs.wait_idle(circle_id, ARCHIVE_WAIT_S) if waited else True
    if not finished:
        log.warning("Demo advance: the archivist was still running after %.0f s; advancing anyway",
                    ARCHIVE_WAIT_S)
    try:
        state = await anyio.to_thread.run_sync(lambda: _advance(body.hours))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    # archive_wait: "none" (nothing was running), "done", or "timed_out" (advanced anyway).
    return {**state, "archive_wait": "none" if not waited else "done" if finished else "timed_out"}


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
