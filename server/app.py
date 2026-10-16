"""
Evoca FastAPI application.

Run:
    uvicorn server.app:app --port 8080

The MCP server runs separately on port 8000:
    uvicorn mcp_server.server:app --port 8000

Identity: X-Person-Id request header (panel and device endpoints).
CORS: http://localhost:5173 (web client dev server).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.db import SessionLocal, init_db
from core.models import Session as OrmSession
from server.session_store import SessionStore
from server.speech import FakeSTT, FakeTTS, PollyTTS, WhisperSTT

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan: startup + shutdown
# ---------------------------------------------------------------------------

# Module-level singletons (injected into routers via overrides).
_store = SessionStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup.
    init_db()

    # Mark any sessions that were left open by a previous crash as ended.
    with SessionLocal() as db:
        orphans = (
            db.query(OrmSession)
            .filter(OrmSession.ended_at.is_(None))
            .all()
        )
        if orphans:
            from core.clock import now_utc
            for sess in orphans:
                sess.ended_at = now_utc().isoformat()
            db.commit()
            log.warning("Marked %d orphaned open session(s) as ended on startup.", len(orphans))

    # Attach live services to the app state (used by dependency overrides).
    app.state.store = _store
    app.state.stt   = WhisperSTT()
    app.state.tts   = PollyTTS()

    yield

    # Shutdown: close any remaining live bridges.
    for live in list(_store._sessions.values()):
        try:
            await live.bridge.__aexit__(None, None, None)
            live.db.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="Evoca API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers + dependency injection
# ---------------------------------------------------------------------------

from server.routers import device as device_router
from server.routers import audio as audio_router
from server.routers import panel as panel_router

app.include_router(device_router.router)
app.include_router(audio_router.router)
app.include_router(panel_router.router)

# Override the placeholder dependency functions in the device router with
# functions that read from app.state.
def _get_store():
    return _store

def _get_stt():
    return app.state.stt

def _get_tts():
    return app.state.tts

app.dependency_overrides[device_router._get_store] = _get_store
app.dependency_overrides[device_router._get_stt]   = _get_stt
app.dependency_overrides[device_router._get_tts]   = _get_tts
