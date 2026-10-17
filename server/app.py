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

import asyncio
import logging
from contextlib import asynccontextmanager

import anyio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.db import SessionLocal, init_db
from core.models import Session as OrmSession
from core.services.publisher import publish_due_stories
from server.session_store import SessionStore
from server.speech import PollyTTS, WhisperSTT

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan: startup + shutdown
# ---------------------------------------------------------------------------

# Module-level singletons (injected into routers via overrides).
_store = SessionStore()

PUBLISH_INTERVAL_S = 60


def _publish_once() -> int:
    with SessionLocal() as db:
        return len(publish_due_stories(db))


async def _publisher_loop() -> None:
    """Publish due stories once at startup, then every minute (PROJECT.md "Arka plan işleri")."""
    while True:
        try:
            count = await anyio.to_thread.run_sync(_publish_once)
            if count:
                log.info("Publisher: published %d stories", count)
        except Exception:
            log.exception("Publisher run failed")
        await asyncio.sleep(PUBLISH_INTERVAL_S)


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
    # Load and warm Whisper now, not on the first /turn (~3 s).
    await anyio.to_thread.run_sync(WhisperSTT.preload)
    app.state.tts   = PollyTTS()

    publisher = asyncio.create_task(_publisher_loop())

    yield

    publisher.cancel()

    # Shutdown: close the DB sessions of live sessions (MCP clients are per request).
    for live in _store.all():
        try:
            live.db.close()
        except Exception:
            log.exception("Closing live session %s on shutdown failed", live.session_id)


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="Evoca API", lifespan=lifespan)

# Show our INFO lines (e.g. "Archivist finished session ...") in the uvicorn log.
_server_log = logging.getLogger("server")
_server_log.setLevel(logging.INFO)
if not _server_log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    _server_log.addHandler(_handler)

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
from server.routers import recordings as recordings_router

app.include_router(device_router.router)
app.include_router(audio_router.router)
app.include_router(panel_router.router)
app.include_router(recordings_router.router)

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
