"""
Device-screen REST endpoints.

POST /api/device/session/start
POST /api/device/turn
POST /api/device/session/end
GET  /api/device/invitation
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile

from core.clock import now_utc
from core.db import SessionLocal
from core.enums import InvitationStatus, SessionStart
from core.models import Circle, Invitation, Membership, Segment
from core.models import Session as OrmSession
from core.services.sessions import end_session, start_session
from server.agents.chat_agent import ChatAgent, chat_llm
from server.mcp_bridge import MCPBridge
from server.session_store import LiveSession, SessionStore
from server.speech import STT, TTS, build_initial_prompt, decode_audio
from server.wav_writer import append_pcm, session_wav_path
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
router = APIRouter()

TTS_DIR = Path("data") / "tts"
TTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Dependencies injected by app.py
# ---------------------------------------------------------------------------

def _get_store() -> SessionStore:
    raise NotImplementedError("store not injected")


def _get_stt() -> STT:
    raise NotImplementedError("stt not injected")


def _get_tts() -> TTS:
    raise NotImplementedError("tts not injected")


# ---------------------------------------------------------------------------
# Identity helper
# ---------------------------------------------------------------------------

def _resolve_viewer(
    x_person_id: str,
    db,
) -> tuple[str, str]:
    """Return (person_id, circle_id) for the device caller.

    The device is always operated by the center person.
    Raises HTTP 403 if the person is not the center of any circle.
    """
    if not x_person_id:
        raise HTTPException(status_code=403, detail="X-Person-Id header required")

    circle = (
        db.query(Circle)
        .filter(Circle.center_person_id == x_person_id)
        .first()
    )
    if circle is None:
        raise HTTPException(
            status_code=403,
            detail="No circle found where this person is the center.",
        )
    return x_person_id, circle.id


def _check_membership(person_id: str, circle_id: str, db) -> Membership:
    m = (
        db.query(Membership)
        .filter(Membership.person_id == person_id, Membership.circle_id == circle_id)
        .first()
    )
    if m is None:
        raise HTTPException(status_code=403, detail="Not a member of this circle.")
    return m


# ---------------------------------------------------------------------------
# Card builder — uses the full tool result from the agent trace
# ---------------------------------------------------------------------------

def _build_cards(trace) -> list[dict]:
    """Build the 'cards' array from the full tool results in the agent trace."""
    cards = []
    for t in trace:
        if t.is_error or t.result is None:
            continue

        if t.tool == "get_session_context":
            result = t.result
            reactions = result.get("undelivered_reactions", [])
            for r in reactions:
                cards.append({
                    "type": "reaction",
                    "story_title": r.get("story_title"),
                    "from": {
                        "name": r.get("person_name"),
                        "relation_to_center": r.get("relation_to_center"),
                    },
                    "emoji": r.get("emoji"),
                })

        elif t.tool == "get_pending_questions":
            result = t.result
            items = result if isinstance(result, list) else result.get("result", [])
            for q in items[:1]:   # agent asks exactly one question per turn
                cards.append({
                    "type": "question",
                    "question_id": q.get("question_id"),
                    "text": q.get("text"),
                    "asker": {
                        "name": q.get("asker_name"),
                        "relation_to_center": q.get("asker_relation_to_center"),
                    },
                })

    return cards


# ---------------------------------------------------------------------------
# Background archivist
# ---------------------------------------------------------------------------

async def _run_archivist(session_id: str, person_id: str, circle_id: str) -> None:
    """Run the archivist agent in the background after a session ends.

    Any exception is caught and logged so a failed archive run is visible
    in the server log instead of disappearing silently.
    """
    try:
        from server.agents.archivist_agent import ArchivistAgent, archivist_llm
        llm = archivist_llm()
        async with MCPBridge(person_id, circle_id) as bridge:
            agent = ArchivistAgent(
                llm=llm,
                person_id=person_id,
                circle_id=circle_id,
                bridge=bridge,
            )
            with SessionLocal() as db:
                result = await agent.run(session_id)
        log.info(
            "Archivist finished session %s: %d stories, %d answers",
            session_id, len(result.story_ids), len(result.answers_recorded),
        )
    except Exception:
        log.exception("Archivist failed for session %s", session_id)


# ---------------------------------------------------------------------------
# POST /api/device/session/start
# ---------------------------------------------------------------------------

@router.post("/api/device/session/start")
async def session_start(
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    store: SessionStore = Depends(_get_store),
    stt: STT = Depends(_get_stt),
    tts: TTS = Depends(_get_tts),
):
    with SessionLocal() as db:
        person_id, circle_id = _resolve_viewer(x_person_id, db)

        # Decide started_by.
        circle = db.get(Circle, circle_id)
        tz = ZoneInfo(circle.timezone)
        today_str = now_utc().astimezone(tz).strftime("%Y-%m-%d")
        invitation = (
            db.query(Invitation)
            .filter(
                Invitation.circle_id == circle_id,
                Invitation.date == today_str,
                Invitation.status == InvitationStatus.sent,
            )
            .first()
        )
        started_by = SessionStart.invitation if invitation else SessionStart.spontaneous

        # Create the Session row.
        sess = start_session(db, circle_id, started_by, [person_id])
        db.commit()
        session_id = sess.id

        # Set audio_path.
        wav_path = session_wav_path(session_id)
        sess_row = db.get(OrmSession, session_id)
        sess_row.audio_path = str(wav_path)
        db.commit()

        # Collect member names for Whisper prompt.
        from core.models import Person
        memberships = (
            db.query(Membership)
            .filter(Membership.circle_id == circle_id)
            .all()
        )
        members = []
        for m in memberships:
            p = db.get(Person, m.person_id)
            if p:
                members.append({"name": p.name, "relation_to_center": m.relation_to_center})

    initial_prompt = build_initial_prompt(members)

    # Open MCP bridge + agent (kept alive for the session).
    bridge = MCPBridge(person_id, circle_id)
    await bridge.__aenter__()

    db_session = SessionLocal()
    agent = ChatAgent(
        llm=chat_llm(),
        person_id=person_id,
        circle_id=circle_id,
        db_session=db_session,
        bridge=bridge,
    )
    # Inject the real session id so agent doesn't create a duplicate row.
    agent._orm_session_id = session_id
    agent._session_wall_start = time.monotonic()

    store.put(LiveSession(
        session_id=session_id,
        bridge=bridge,
        agent=agent,
        db=db_session,
    ))

    # Kickoff turn.
    t0 = time.monotonic()
    result = await agent.turn("(Session started.)", store_user=False)
    llm_ms = int((time.monotonic() - t0) * 1000)

    # TTS.
    tts_t0 = time.monotonic()
    tts_result = await tts.synthesize(result.reply_text)
    tts_ms = int((time.monotonic() - tts_t0) * 1000)

    # Save TTS mp3.
    mp3_name = f"{session_id}_start.mp3"
    mp3_path = TTS_DIR / mp3_name
    mp3_path.write_bytes(tts_result.mp3_bytes)

    cards = _build_cards(result.trace)

    return {
        "session_id": session_id,
        "session_open": True,
        "heard_text": None,
        "reply_text": result.reply_text,
        "reply_audio_url": f"/api/tts/{mp3_name}",
        "cards": cards,
        "trace": [
            {
                "tool": t.tool,
                "input": t.input,
                "result_preview": t.result_preview,
                "ms": t.ms,
                "is_error": t.is_error,
            }
            for t in result.trace
        ],
        "latency": {
            **result.latency,
            "stt_ms": 0,
            "tts_ms": tts_ms,
        },
    }


# ---------------------------------------------------------------------------
# POST /api/device/turn
# ---------------------------------------------------------------------------

@router.post("/api/device/turn")
async def device_turn(
    session_id: Annotated[str, Form()],
    audio: Annotated[UploadFile, File()],
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    store: SessionStore = Depends(_get_store),
    stt: STT = Depends(_get_stt),
    tts: TTS = Depends(_get_tts),
    background_tasks: BackgroundTasks = None,
):
    total_t0 = time.monotonic()

    live = store.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail="Session not found or already ended.")

    # Verify caller is the same person.
    if x_person_id and live.agent._person_id != x_person_id:
        raise HTTPException(status_code=403, detail="Session belongs to a different person.")

    person_id = live.agent._person_id
    circle_id = live.agent._circle_id

    # 1. Decode audio.
    raw_bytes = await audio.read()
    stt_t0 = time.monotonic()
    pcm = await decode_audio(raw_bytes)

    # 2. Append user audio to WAV; get real positions.
    user_start_ms, user_end_ms = await anyio.to_thread.run_sync(
        lambda: append_pcm(session_id, pcm)
    )

    # 3. STT.
    with SessionLocal() as db:
        memberships = (
            db.query(Membership)
            .filter(Membership.circle_id == circle_id)
            .all()
        )
        from core.models import Person
        members = []
        for m in memberships:
            p = db.get(Person, m.person_id)
            if p:
                members.append({"name": p.name, "relation_to_center": m.relation_to_center})

    initial_prompt = build_initial_prompt(members)
    stt_result = await stt.transcribe(pcm, initial_prompt)
    stt_ms = int((time.monotonic() - stt_t0) * 1000)

    # Shift Whisper word timestamps by the WAV start offset.
    shifted_words = [
        {
            "w": w["w"],
            "start_ms": w["start_ms"] + user_start_ms,
            "end_ms":   w["end_ms"]   + user_start_ms,
        }
        for w in stt_result.words
    ]

    # 4. Agent turn.
    result = await live.agent.turn(
        stt_result.text,
        store_user=True,
        user_start_ms=user_start_ms,
        user_end_ms=user_end_ms,
        user_words=shifted_words,
    )

    # 5. TTS.
    tts_t0 = time.monotonic()
    tts_result = await tts.synthesize(result.reply_text)
    tts_ms = int((time.monotonic() - tts_t0) * 1000)

    # 6. Decode TTS mp3 → PCM and append to WAV for agent segment.
    agent_pcm = await decode_audio(tts_result.mp3_bytes)
    agent_start_ms, agent_end_ms = await anyio.to_thread.run_sync(
        lambda: append_pcm(session_id, agent_pcm)
    )

    # Update agent segment timestamps in DB.
    with SessionLocal() as db:
        segs = (
            db.query(Segment)
            .filter(Segment.session_id == session_id, Segment.speaker_id.is_(None))
            .order_by(Segment.start_ms.desc())
            .first()
        )
        if segs:
            segs.start_ms = agent_start_ms
            segs.end_ms   = agent_end_ms
            db.commit()

    # 7. Save TTS mp3.
    turn_count = len([t for t in result.trace])
    mp3_name = f"{session_id}_{user_start_ms}.mp3"
    mp3_path = TTS_DIR / mp3_name
    mp3_path.write_bytes(tts_result.mp3_bytes)

    total_ms = int((time.monotonic() - total_t0) * 1000)

    # 8. If the agent ended the session, clean up.
    if result.session_should_end:
        store.pop(session_id)
        with SessionLocal() as db:
            end_session(db, session_id)
            db.commit()
        await live.bridge.__aexit__(None, None, None)
        live.db.close()
        if background_tasks:
            background_tasks.add_task(
                _run_archivist_bg, session_id, person_id, circle_id
            )

    cards = _build_cards(result.trace)

    return {
        "session_id": session_id,
        "session_open": not result.session_should_end,
        "heard_text": stt_result.text,
        "reply_text": result.reply_text,
        "reply_audio_url": f"/api/tts/{mp3_name}",
        "cards": cards,
        "trace": [
            {
                "tool": t.tool,
                "input": t.input,
                "result_preview": t.result_preview,
                "ms": t.ms,
                "is_error": t.is_error,
            }
            for t in result.trace
        ],
        "latency": {
            "stt_ms": stt_ms,
            "llm_ms": result.latency["llm_ms"],
            "tools_ms": result.latency["tools_ms"],
            "tts_ms": tts_ms,
            "total_ms": total_ms,
        },
    }


def _run_archivist_bg(session_id: str, person_id: str, circle_id: str) -> None:
    """Sync wrapper for BackgroundTasks (FastAPI calls it in a thread)."""
    import asyncio
    asyncio.run(_run_archivist(session_id, person_id, circle_id))


# ---------------------------------------------------------------------------
# POST /api/device/session/end
# ---------------------------------------------------------------------------

@router.post("/api/device/session/end")
async def session_end(
    body: dict,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    store: SessionStore = Depends(_get_store),
    background_tasks: BackgroundTasks = None,
):
    session_id = body.get("session_id", "")
    live = store.pop(session_id)

    if live is None:
        raise HTTPException(status_code=404, detail="Session not found or already ended.")

    person_id = live.agent._person_id
    circle_id = live.agent._circle_id

    with SessionLocal() as db:
        row = db.get(OrmSession, session_id)
        if row and row.ended_at is None:
            end_session(db, session_id)
            db.commit()
        ended_at = db.get(OrmSession, session_id).ended_at if row else now_utc().isoformat()

    await live.bridge.__aexit__(None, None, None)
    live.db.close()

    if background_tasks:
        background_tasks.add_task(
            _run_archivist_bg, session_id, person_id, circle_id
        )

    return {
        "session_id": session_id,
        "ended_at": ended_at,
        "processing": "started",
    }


# ---------------------------------------------------------------------------
# GET /api/device/invitation
# ---------------------------------------------------------------------------

@router.get("/api/device/invitation")
async def get_invitation(
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    with SessionLocal() as db:
        person_id, circle_id = _resolve_viewer(x_person_id, db)
        circle = db.get(Circle, circle_id)
        tz = ZoneInfo(circle.timezone)
        today_str = now_utc().astimezone(tz).strftime("%Y-%m-%d")

        inv = (
            db.query(Invitation)
            .filter(
                Invitation.circle_id == circle_id,
                Invitation.date == today_str,
                Invitation.status == InvitationStatus.sent,
            )
            .first()
        )
        if inv is None:
            return {"active": False, "invitation": None}

        return {
            "active": True,
            "invitation": {
                "id": inv.id,
                "person_id": inv.person_id,
                "date": inv.date,
                "reason": inv.reason,
                "status": inv.status,
            },
        }
