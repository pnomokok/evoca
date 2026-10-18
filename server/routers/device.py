"""
Device-screen REST endpoints.

POST /api/device/session/start
POST /api/device/turn
POST /api/device/session/end
GET  /api/device/invitation

Identity: the X-Person-Id header. Only a circle's center person can start a
device session, and only the person who started a session can send turns to
it or end it. An optional X-Circle-Id header picks the circle when the person
is the center of several; it must be a circle they are the center of (else
the same 403), and on /turn and /session/end it must be the session's circle.

The session audio is one WAV per session (server/wav_writer.py). Every user
turn and every spoken agent reply is appended to it, and each Segment gets its
real position in that WAV, so story sources, answers and private ranges all
point at the right audio.

Privacy marks ("don't let anyone hear that") are flushed after the reply's
audio span is in the WAV. A mark that fails stays pending; /session/end (or a
goodbye) retries it, and if it still fails the archivist is NOT run for that
session: the story may be lost, the secret must not leak.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from core.clock import now_utc
from core.db import SessionLocal
from core.enums import InvitationStatus, SessionStart
from core.models import Circle, Invitation, Membership, Person, Question
from core.models import Session as OrmSession
from core.services.chat_tools import playlist_ranges
from core.services.sessions import end_session, start_session
from server.agents.archivist_agent import ArchivistAgent, answer_check_llm, archivist_llm
from server.agents.chat_agent import ChatAgent, chat_llm, privacy_check_llm, split_sentences
from server.mcp_bridge import MCPBridge
from server.session_store import LiveSession, SessionStore
from server.speech import STT, TTS, build_initial_prompt, decode_audio
from server.wav_writer import append_pcm, session_wav_path

log = logging.getLogger(__name__)
router = APIRouter()

TTS_DIR = Path("data") / "tts"
TTS_DIR.mkdir(parents=True, exist_ok=True)

# Said when speech-to-text heard nothing; no LLM call, nothing stored.
DIDNT_CATCH = "I'm sorry, I didn't catch that. Could you say it again?"


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
# Identity helpers
# ---------------------------------------------------------------------------

def _resolve_center(x_person_id: str, db, x_circle_id: str = "") -> tuple[str, str]:
    """Return (person_id, circle_id) for the device caller, who must be a center
    (of the X-Circle-Id circle when given)."""
    if not x_person_id:
        raise HTTPException(status_code=403, detail="X-Person-Id header required.")
    q = db.query(Circle).filter(Circle.center_person_id == x_person_id)
    if x_circle_id:
        q = q.filter(Circle.id == x_circle_id)
    circle = q.order_by(Circle.id).first()
    if circle is None:
        raise HTTPException(status_code=403, detail="No circle found where this person is the center.")
    return x_person_id, circle.id


def _require_owner(live: LiveSession, x_person_id: str, x_circle_id: str = "") -> None:
    """Only the person who started the session may use it (in its own circle)."""
    if not x_person_id or x_person_id != live.owner_id or (x_circle_id and x_circle_id != live.circle_id):
        raise HTTPException(status_code=403, detail="Only the person who started this session can use it.")


def _whisper_prompt(circle_id: str, last_question: str | None) -> str:
    """Member names and relations (names fail without them), plus the question
    the agent just asked, as a Whisper hint."""
    with SessionLocal() as db:
        members = []
        for m in db.query(Membership).filter(Membership.circle_id == circle_id).all():
            p = db.get(Person, m.person_id)
            if p:
                members.append({"name": p.name, "relation_to_center": m.relation_to_center})
    return build_initial_prompt(members, last_question)


def _question_in(reply: str) -> str | None:
    """The last question sentence of a reply, or None."""
    questions = [s for s in split_sentences(reply) if s.rstrip().endswith("?")]
    return questions[-1] if questions else None


# ---------------------------------------------------------------------------
# Cards — built from the full tool results kept in ToolTrace.result
# ---------------------------------------------------------------------------

def _remember_questions(live: LiveSession, trace) -> None:
    """Keep every pending question the agent has seen in this session."""
    for t in trace:
        if t.tool == "get_pending_questions" and not t.is_error and t.result is not None:
            items = t.result if isinstance(t.result, list) else t.result.get("result", [])
            for q in items:
                if q.get("question_id"):
                    live.seen_questions[q["question_id"]] = q


def _playlist_card(viewer_id: str, session_id: str, story_id: str) -> dict | None:
    """A playlist card for the story get_linked_playlist played in this turn.

    The model never sees audio ranges, so they are rebuilt here with the same
    service, the same viewer (the center) and the same order: can_see()
    filtered and cut around private parts. The device plays the reply audio
    first, then these items in order."""
    with SessionLocal() as db:
        sess = db.get(OrmSession, session_id)
        if sess is None:
            return None
        try:
            ranges = playlist_ranges(db, viewer_id, sess.circle_id, story_id)
        except ValueError:
            return None
    items = [
        {"story_id": r["story_id"], "title": r["title"], "teller": r["teller"]["name"], "url": r["url"]}
        for r in ranges
    ]
    return {"type": "playlist", "items": items} if items else None


def _build_cards(trace, live: LiveSession) -> list[dict]:
    """Reaction cards from get_session_context; a question card only for a
    question the agent actually marked as asked in this turn; a playlist card
    only when get_linked_playlist ran in this turn (its last successful call).
    A reaction appears once even if the model calls get_session_context again
    after the prefetch."""
    seen_questions = live.seen_questions
    cards: list[dict] = []
    seen_reactions: set[tuple] = set()
    playlist_story: str | None = None
    for t in trace:
        if t.is_error or t.result is None:
            continue
        if t.tool == "get_session_context":
            for r in t.result.get("undelivered_reactions", []):
                key = (r.get("story_id"), r.get("person_id"), r.get("emoji"))
                if key in seen_reactions:
                    continue
                seen_reactions.add(key)
                cards.append({
                    "type": "reaction",
                    "story_id": r.get("story_id"),
                    "story_title": r.get("story_title"),
                    "from": {
                        "id": r.get("person_id"),
                        "name": r.get("person_name"),
                        "relation_to_center": r.get("relation_to_center"),
                    },
                    "emoji": r.get("emoji"),
                })
        elif t.tool == "mark_question_asked":
            q = seen_questions.get(t.input.get("question_id", ""))
            if q:
                cards.append({
                    "type": "question",
                    "question_id": q.get("question_id"),
                    "text": q.get("text"),
                    "asker": {
                        "id": q.get("asker_id"),
                        "name": q.get("asker_name"),
                        "relation_to_center": q.get("asker_relation_to_center"),
                    },
                })
        elif t.tool == "get_linked_playlist" and t.result.get("items"):
            playlist_story = t.input.get("story_id")
    if playlist_story:
        card = _playlist_card(live.owner_id, live.session_id, playlist_story)
        if card:
            cards.append(card)
    return cards


def _trace_json(trace) -> list[dict[str, Any]]:
    return [
        {"tool": t.tool, "input": t.input, "result_preview": t.result_preview,
         "ms": t.ms, "is_error": t.is_error, "prefetched": t.prefetched}
        for t in trace
    ]


# ---------------------------------------------------------------------------
# Speaking, closing, archiving
# ---------------------------------------------------------------------------

async def _speak(live: LiveSession, tts: TTS, text: str, record: bool) -> tuple[str, int]:
    """Synthesize text, save it for the client, and (if record) append it to the
    session WAV and give the agent's latest Segment that real span.

    Returns (reply_audio_url, tts_ms).
    """
    t0 = time.monotonic()
    tts_result = await tts.synthesize(text)
    tts_ms = int((time.monotonic() - t0) * 1000)

    # Random part keeps file names unguessable; /api/tts also checks access.
    name = f"{live.session_id}_{uuid.uuid4().hex[:12]}.{tts_result.audio_format}"
    await anyio.to_thread.run_sync(lambda: (TTS_DIR / name).write_bytes(tts_result.mp3_bytes))

    if record:
        pcm = await decode_audio(tts_result.mp3_bytes)
        start_ms, end_ms = await anyio.to_thread.run_sync(lambda: append_pcm(live.session_id, pcm))
        live.agent.set_last_agent_span(start_ms, end_ms)
    return f"/api/tts/{name}", tts_ms


@asynccontextmanager
async def _connected(live: LiveSession):
    """Open an MCP client for this request only and hand it to the agent.

    An MCP client (its anyio task group) must be closed in the task that opened
    it, so it cannot outlive the request. Yields the connect time in ms; the
    agent's tool list is cached after the first turn, so this is the only
    per-turn MCP overhead.
    """
    t0 = time.monotonic()
    async with MCPBridge(live.owner_id, live.agent._circle_id, session_id=live.session_id) as bridge:
        connect_ms = int((time.monotonic() - t0) * 1000)
        live.agent.set_bridge(bridge)
        try:
            yield connect_ms
        finally:
            live.agent.set_bridge(None)


async def _flush_marks(live: LiveSession) -> list:
    """Apply pending privacy marks through MCP; failures stay pending."""
    if not live.agent.has_pending_private:
        return []
    try:
        async with _connected(live):
            return await live.agent.flush_private_marks()
    except Exception:
        log.exception("Could not connect to mark private segments (session %s); "
                      "the marks stay pending", live.session_id)
        return []


async def _close_live(live: LiveSession) -> None:
    live.db.close()


def _end_session_row(session_id: str) -> str:
    """Set ended_at if not set yet; return ended_at."""
    with SessionLocal() as db:
        row = db.get(OrmSession, session_id)
        if row is None:
            return now_utc().isoformat()
        if row.ended_at is None:
            end_session(db, session_id)
            db.commit()
        return row.ended_at


async def _finish(live: LiveSession, store: SessionStore, background_tasks: BackgroundTasks) -> str:
    """End a live session and start the archivist in the background.

    Pending privacy marks are retried first. If any still fail, the archivist
    is not run for this session (fail closed).
    """
    store.pop(live.session_id)
    if live.agent.has_pending_private:
        await _flush_marks(live)
    ended_at = _end_session_row(live.session_id)
    unmarked = list(live.agent.pending_private)
    await _close_live(live)
    if unmarked:
        log.error(
            "Session %s: %d segment(s) could not be marked private; the archivist is NOT "
            "run for this session so the private part cannot leak (segments: %s)",
            live.session_id, len(unmarked), ", ".join(unmarked),
        )
    else:
        background_tasks.add_task(_run_archivist, live.session_id, live.owner_id, live.agent._circle_id)
    return ended_at


async def _run_archivist(session_id: str, person_id: str, circle_id: str) -> None:
    """Run the archivist after a session ends (FastAPI background task).

    Any exception is logged with the session id, so a failed archive run is
    visible in the server log instead of disappearing silently.
    """
    log.info("Archivist started for session %s", session_id)
    try:
        # The session header lets add_refused_topic act only on this session.
        async with MCPBridge(person_id, circle_id, session_id=session_id) as bridge:
            agent = ArchivistAgent(llm=archivist_llm(), person_id=person_id, circle_id=circle_id,
                                   bridge=bridge, checker_llm=answer_check_llm())
            result = await agent.run(session_id)
        log.info(
            "Archivist finished session %s: %d stories, %d answers, %d questions, "
            "%d refused topics (%d ms)",
            session_id, len(result.story_ids), len(result.answers_recorded),
            len(result.questions_added), len(result.topics_refused),
            result.latency.get("total_ms", 0),
        )
        with SessionLocal() as db:
            for qid in result.answers_recorded:
                q = db.get(Question, qid)
                log.info("Archivist marked answered: %r (question %s)", q.text if q else "?", qid)
            for qid in result.questions_declined:
                q = db.get(Question, qid)
                log.info("Archivist marked declined: %r (question %s)", q.text if q else "?", qid)
            for qid in result.questions_reopened:
                q = db.get(Question, qid)
                log.info("Archivist returned to waiting: %r (question %s)", q.text if q else "?", qid)
        for t in result.trace:
            if t.tool in ("record_answer", "mark_question_declined") and t.is_error:
                log.info("Archivist %s rejected: %s", t.tool, t.result_preview)
            elif t.tool == "add_refused_topic" and t.is_error:
                # The preview may echo the topic; the agent logs its own reason.
                log.info("Archivist add_refused_topic rejected (session %s)", session_id)
    except Exception:
        log.exception("Archivist failed for session %s", session_id)


# ---------------------------------------------------------------------------
# POST /api/device/session/start
# ---------------------------------------------------------------------------

@router.post("/api/device/session/start")
async def session_start(
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    x_circle_id: Annotated[str, Header(alias="x-circle-id")] = "",
    store: SessionStore = Depends(_get_store),
    tts: TTS = Depends(_get_tts),
):
    total_t0 = time.monotonic()
    with SessionLocal() as db:
        person_id, circle_id = _resolve_center(x_person_id, db, x_circle_id)

        circle = db.get(Circle, circle_id)
        today_str = now_utc().astimezone(ZoneInfo(circle.timezone)).strftime("%Y-%m-%d")
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
        if invitation:
            invitation.status = InvitationStatus.accepted

        sess = start_session(db, circle_id, started_by, [person_id])
        sess.audio_path = str(session_wav_path(sess.id))
        db.commit()
        session_id = sess.id

    db_session = SessionLocal()
    agent = ChatAgent(llm=chat_llm(), person_id=person_id, circle_id=circle_id,
                      db_session=db_session, bridge=None, session_id=session_id,
                      flush_marks_in_turn=False, checker_llm=privacy_check_llm())
    live = LiveSession(session_id=session_id, owner_id=person_id, agent=agent, db=db_session,
                       circle_id=circle_id)
    store.put(live)

    async with live.lock:
        try:
            async with _connected(live) as connect_ms:
                result = await agent.turn("(Session started.)", store_user=False, prefetch_context=True)
            _remember_questions(live, result.trace)
            live.last_question = _question_in(result.reply_text)
            audio_url, tts_ms = await _speak(live, tts, result.reply_text, record=True)
            result.trace.extend(await _flush_marks(live))
        except Exception:
            # MCP server down, LLM or TTS failure: do not leave an open session behind.
            log.exception("Opening turn failed for session %s", session_id)
            store.pop(session_id)
            _end_session_row(session_id)
            await _close_live(live)
            raise HTTPException(status_code=502, detail="The conversation could not start.")

    return {
        "session_id": session_id,
        "session_open": True,
        "heard_text": None,
        "reply_text": result.reply_text,
        "reply_audio_url": audio_url,
        "cards": _build_cards(result.trace, live),
        "trace": _trace_json(result.trace),
        "latency": {
            "stt_ms": 0,
            "mcp_connect_ms": connect_ms,
            "llm_ms": result.latency["llm_ms"],
            "tools_ms": result.latency["tools_ms"],
            "tts_ms": tts_ms,
            "total_ms": int((time.monotonic() - total_t0) * 1000),
        },
    }


# ---------------------------------------------------------------------------
# POST /api/device/turn
# ---------------------------------------------------------------------------

@router.post("/api/device/turn")
async def device_turn(
    background_tasks: BackgroundTasks,
    session_id: Annotated[str, Form()],
    audio: Annotated[UploadFile, File()],
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    x_circle_id: Annotated[str, Header(alias="x-circle-id")] = "",
    store: SessionStore = Depends(_get_store),
    stt: STT = Depends(_get_stt),
    tts: TTS = Depends(_get_tts),
):
    total_t0 = time.monotonic()

    live = store.get(session_id)
    if live is None:
        raise HTTPException(status_code=404, detail="Session not found or already ended.")
    _require_owner(live, x_person_id, x_circle_id)

    async with live.lock:
        if store.get(session_id) is None:   # ended while this request waited
            raise HTTPException(status_code=404, detail="Session not found or already ended.")

        # 1. Decode and transcribe.
        raw_bytes = await audio.read()
        stt_t0 = time.monotonic()
        try:
            pcm = await decode_audio(raw_bytes)
        except Exception:
            raise HTTPException(status_code=400, detail="Could not read the audio.")
        prompt = await anyio.to_thread.run_sync(
            lambda: _whisper_prompt(live.agent._circle_id, live.last_question)
        )
        stt_result = await stt.transcribe(pcm, prompt)
        stt_ms = int((time.monotonic() - stt_t0) * 1000)

        # 2. Nothing heard: ask again, without an LLM call and without storing anything.
        if not stt_result.text.strip():
            audio_url, tts_ms = await _speak(live, tts, DIDNT_CATCH, record=False)
            return {
                "session_id": session_id,
                "session_open": True,
                "heard_text": "",
                "reply_text": DIDNT_CATCH,
                "reply_audio_url": audio_url,
                "cards": [],
                "trace": [],
                "latency": {"stt_ms": stt_ms, "llm_ms": 0, "tools_ms": 0, "tts_ms": tts_ms,
                            "total_ms": int((time.monotonic() - total_t0) * 1000)},
            }

        # 3. Connect to MCP first, so nothing is stored if the MCP server is down.
        try:
            async with _connected(live) as connect_ms:
                # 4. Append the user's audio and shift word timestamps to WAV positions.
                user_start_ms, user_end_ms = await anyio.to_thread.run_sync(
                    lambda: append_pcm(session_id, pcm)
                )
                shifted_words = [
                    {"w": w["w"], "start_ms": w["start_ms"] + user_start_ms,
                     "end_ms": w["end_ms"] + user_start_ms}
                    for w in stt_result.words
                ]
                # 5. Agent turn.
                result = await live.agent.turn(
                    stt_result.text,
                    store_user=True,
                    user_start_ms=user_start_ms,
                    user_end_ms=user_end_ms,
                    user_words=shifted_words,
                )
        except Exception:
            log.exception("Turn failed for session %s", session_id)
            raise HTTPException(status_code=502, detail="The conversation service is not available.")

        # 6. Speak and record the reply, then apply privacy marks (the reply's
        #    real audio span is known only now).
        _remember_questions(live, result.trace)
        # A hidden reply must not reach Whisper's hint either.
        live.last_question = None if result.marked_private else _question_in(result.reply_text)
        audio_url, tts_ms = await _speak(live, tts, result.reply_text, record=True)
        result.trace.extend(await _flush_marks(live))

        # 7. The agent said goodbye: end the session and archive it.
        if result.session_should_end:
            await _finish(live, store, background_tasks)

    return {
        "session_id": session_id,
        "session_open": not result.session_should_end,
        "heard_text": stt_result.text,
        "reply_text": result.reply_text,
        "reply_audio_url": audio_url,
        "cards": _build_cards(result.trace, live),
        "trace": _trace_json(result.trace),
        "latency": {
            "stt_ms": stt_ms,
            "mcp_connect_ms": connect_ms,
            "llm_ms": result.latency["llm_ms"],
            "tools_ms": result.latency["tools_ms"],
            "tts_ms": tts_ms,
            "total_ms": int((time.monotonic() - total_t0) * 1000),
        },
    }


# ---------------------------------------------------------------------------
# POST /api/device/session/end
# ---------------------------------------------------------------------------

class SessionEndRequest(BaseModel):
    session_id: str


@router.post("/api/device/session/end")
async def session_end(
    body: SessionEndRequest,
    background_tasks: BackgroundTasks,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    x_circle_id: Annotated[str, Header(alias="x-circle-id")] = "",
    store: SessionStore = Depends(_get_store),
):
    live = store.get(body.session_id)
    if live is None:
        raise HTTPException(status_code=404, detail="Session not found or already ended.")
    _require_owner(live, x_person_id, x_circle_id)

    async with live.lock:
        if store.get(body.session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found or already ended.")
        ended_at = await _finish(live, store, background_tasks)

    return {"session_id": body.session_id, "ended_at": ended_at, "processing": "started"}


# ---------------------------------------------------------------------------
# GET /api/device/invitation
# ---------------------------------------------------------------------------

@router.get("/api/device/invitation")
async def get_invitation(
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    x_circle_id: Annotated[str, Header(alias="x-circle-id")] = "",
):
    """Is the light on? "now" is the demo-aware current time (now_utc(), so
    DEMO_NOW moves it), for the device clock."""
    now = now_utc()
    with SessionLocal() as db:
        _, circle_id = _resolve_center(x_person_id, db, x_circle_id)
        circle = db.get(Circle, circle_id)
        today_str = now.astimezone(ZoneInfo(circle.timezone)).strftime("%Y-%m-%d")
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
            return {"active": False, "invitation": None, "now": now.isoformat()}
        return {
            "active": True,
            "now": now.isoformat(),
            "invitation": {
                "id": inv.id,
                "person_id": inv.person_id,
                "date": inv.date,
                "reason": inv.reason,
                "status": inv.status,
            },
        }
