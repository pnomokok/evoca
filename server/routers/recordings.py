"""
Panel recordings (docs/ARCHITECTURE.md A4, "A family member's own memory").

POST /api/recordings
    Multipart: audio (webm/wav, like a device turn) + optional access
    ("circle" | "private", default "circle"). Any circle member may record,
    the center included; identity is the X-Person-Id header.

The request decodes the audio, checks its length, creates a single-person
panel_recording Session owned by the recorder, saves the audio to the session
WAV and ends the session, then answers 202 at once. Speech-to-text and the
archivist run in the background:

- one Segment for the whole recording (speaker_id = the recorder, word timings);
- the archivist in panel_recording mode: teller = the recorder, subjects and
  periods as usual, no answers, declines or questions;
- the stories get the requested access; for a private recording this is
  enforced again after the run, whatever happened in it, and if that fails
  the stories are hidden (fail closed). Access is never widened afterwards.

Failures are logged with the session id only, never transcript text.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile

from core.db import SessionLocal
from core.enums import SessionStart, StoryStatus
from core.models import Membership, Person, Story
from core.services import stories as story_svc
from core.services.sessions import add_segment, end_session, start_session
from server.agents.archivist_agent import ArchivistAgent, answer_check_llm, archivist_llm
from server.mcp_bridge import MCPBridge
from server.routers.device import _get_stt, _whisper_prompt
from server.routers.panel import _resolve_panel_viewer
from server.speech import STT, decode_audio
from server.wav_writer import append_pcm, pcm_duration_ms, session_wav_path

log = logging.getLogger(__name__)
router = APIRouter()

MAX_RECORDING_MS = 3 * 60 * 1000
MIN_RECORDING_MS = 500   # anything shorter holds no words
_ACCESS_TYPES = ("circle", "private")


# ---------------------------------------------------------------------------
# POST /api/recordings
# ---------------------------------------------------------------------------

@router.post("/api/recordings", status_code=202)
async def post_recording(
    background_tasks: BackgroundTasks,
    audio: Annotated[UploadFile, File()],
    access: Annotated[str, Form()] = "circle",
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    x_circle_id: Annotated[str, Header(alias="x-circle-id")] = "",
    stt: STT = Depends(_get_stt),
):
    with SessionLocal() as db:
        person_id, circle_id = _resolve_panel_viewer(x_person_id, db, x_circle_id)
    if access not in _ACCESS_TYPES:
        raise HTTPException(status_code=400, detail="access must be 'circle' or 'private'.")

    raw_bytes = await audio.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="The recording is empty.")
    try:
        pcm = await decode_audio(raw_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read the audio.")
    duration_ms = pcm_duration_ms(pcm)
    if duration_ms < MIN_RECORDING_MS:
        raise HTTPException(status_code=400, detail="The recording is empty.")
    if duration_ms > MAX_RECORDING_MS:
        raise HTTPException(status_code=400, detail="A recording can be at most 3 minutes long.")

    with SessionLocal() as db:
        sess = start_session(db, circle_id, SessionStart.panel_recording, [person_id])
        sess.audio_path = str(session_wav_path(sess.id))
        db.commit()
        session_id = sess.id
    try:
        await anyio.to_thread.run_sync(lambda: append_pcm(session_id, pcm))
    finally:
        with SessionLocal() as db:
            end_session(db, session_id)
            db.commit()

    background_tasks.add_task(_process_recording, session_id, person_id, circle_id,
                              pcm, access, stt)
    return {"session_id": session_id, "started_by": SessionStart.panel_recording.value,
            "processing": "started"}


# ---------------------------------------------------------------------------
# Background: speech-to-text, then the archivist
# ---------------------------------------------------------------------------

def _members(circle_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        out = []
        for m in db.query(Membership).filter(Membership.circle_id == circle_id).all():
            p = db.get(Person, m.person_id)
            if p:
                out.append({"person_id": p.id, "name": p.name,
                            "relation_to_center": m.relation_to_center,
                            "birth_year": p.birth_year})
        return out


def _session_stories(db, session_id: str, person_id: str) -> list[Story]:
    return [
        story for story in db.query(Story).filter(Story.teller_id == person_id).all()
        if any(s.get("session_id") == session_id for s in story.sources or [])
    ]


def _enforce_private(session_id: str, person_id: str) -> None:
    """Every story told from a private recording is private. Only ever
    narrows access: a story the teller made private stays private."""
    with SessionLocal() as db:
        for story in _session_stories(db, session_id, person_id):
            if (story.access or {}).get("type") != "private":
                story_svc.update_story(db, person_id, story.id, access="private")


def _hide_all(session_id: str, person_id: str) -> None:
    """Last resort when access could not be enforced: hide the stories (only
    the teller sees a hidden story)."""
    with SessionLocal() as db:
        for story in _session_stories(db, session_id, person_id):
            story.status = StoryStatus.hidden
        db.commit()


async def _process_recording(
    session_id: str, person_id: str, circle_id: str, pcm: bytes, access: str, stt: STT,
) -> None:
    """Transcribe the recording, store it as one Segment and archive it."""
    try:
        prompt = await anyio.to_thread.run_sync(lambda: _whisper_prompt(circle_id, None))
        stt_result = await stt.transcribe(pcm, prompt)
    except Exception as exc:
        log.error("Transcription failed for recording session %s: %s",
                  session_id, type(exc).__name__)
        return
    if not stt_result.text.strip():
        log.info("Recording session %s: no speech heard, nothing archived", session_id)
        return

    with SessionLocal() as db:
        add_segment(db, session_id, person_id, stt_result.text, 0, pcm_duration_ms(pcm),
                    words=stt_result.words)
        db.commit()

    log.info("Archivist started for recording session %s", session_id)
    try:
        members = await anyio.to_thread.run_sync(lambda: _members(circle_id))
        # The session header lets link_stories link only stories of this recording.
        async with MCPBridge(person_id, circle_id, session_id=session_id) as bridge:
            agent = ArchivistAgent(llm=archivist_llm(), person_id=person_id, circle_id=circle_id,
                                   bridge=bridge, panel_recording=True, members=members,
                                   story_access=access, story_guard_llm=answer_check_llm())
            result = await agent.run(session_id)
        log.info("Archivist finished recording session %s: %d stories (%d ms)",
                 session_id, len(result.story_ids), result.latency.get("total_ms", 0))
    except Exception as exc:
        log.error("Archivist failed for recording session %s: %s",
                  session_id, type(exc).__name__)
    finally:
        if access == "private":
            await _make_private(session_id, person_id)


async def _make_private(session_id: str, person_id: str) -> None:
    """Fail closed: if the stories cannot be made private, hide them."""
    try:
        await anyio.to_thread.run_sync(lambda: _enforce_private(session_id, person_id))
    except Exception as exc:
        log.error("Could not make the stories of recording session %s private (%s); "
                  "hiding them", session_id, type(exc).__name__)
        try:
            await anyio.to_thread.run_sync(lambda: _hide_all(session_id, person_id))
        except Exception as exc2:
            log.error("Could not hide the stories of recording session %s: %s",
                      session_id, type(exc2).__name__)
