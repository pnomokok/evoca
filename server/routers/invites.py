"""
Invite links and sign-in sessions (docs/ARCHITECTURE.md "Access control",
Identity).

GET  /api/invites/{token}          (no auth) {circle_name, person_name, role}
POST /api/invites/{token}/accept   (no auth) a new sign-in session
POST /api/auth/logout              (bearer only) revokes the current session

A revoked, wrong or unknown invite token is the same 404. The link stays
usable until an admin revokes it. Logic lives in core.services.auth; tokens
are looked up by hash and never logged (server.auth.redact_token_paths).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

import core.db as cdb    # looked up per call, so tests that patch core.db.SessionLocal reach it
from core.services import admin as admin_svc
from core.services import auth as auth_svc
from server.auth import Viewer, panel_viewer, unauthorized

router = APIRouter()


@router.get("/api/invites/{token}")
async def get_invite(token: str):
    """Who the link is for. Matches GET_invite.json."""
    with cdb.SessionLocal() as db:
        try:
            return auth_svc.invite_info(db, token)
        except admin_svc.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/invites/{token}/accept")
async def accept_invite(token: str):
    """Sign in with the link: {session_token, person_id, circle_id}. Matches POST_invite_accept.json."""
    with cdb.SessionLocal() as db:
        try:
            return auth_svc.accept_invite(db, token)
        except admin_svc.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/auth/logout")
async def logout(viewer: Viewer = Depends(panel_viewer)):
    """Revoke the bearer session this request came with; demo headers have none (401)."""
    if viewer.auth_session_id is None:
        raise unauthorized()
    with cdb.SessionLocal() as db:
        return auth_svc.logout(db, viewer.auth_session_id)
