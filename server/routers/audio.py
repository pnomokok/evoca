"""
Audio endpoints.

GET /api/audio/{session_id}?start=<ms>&end=<ms>
    A WAV slice of a session, with access control.
GET /api/tts/{file}
    A generated reply audio file, for the participants of its session.

Privacy rules for /api/audio (docs/PROJECT.md "Erişim kuralları"):
  1. The viewer must be entitled to the range, checked FIRST:
     a. the recorder of a panel_recording session, or the circle's center
        person for a session the center took part in, may hear any range of
        that session (the center has no whole-session right to another
        member's panel recording); or
     b. the range lies inside a source of a story the viewer can_see(); or
     c. the range lies inside the answer to a question the viewer asked, and
        the viewer can_see() the answer's story (so a pending, hidden or
        private story keeps its answer from the asker too).
  2. A range overlapping private segments is allowed only if the viewer is
     the speaker of EVERY private segment it overlaps (private means "only the
     teller"). Nobody else hears a private part: not the circle center, not a
     story source, not an answer. An agent segment marked private has no
     speaker, so it is refused for everyone.
  Every refusal returns the same 403 message, so a viewer cannot tell a
  private part from audio they simply may not hear (they must not learn that
  a private part exists).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response

from core.access import can_see
from core.db import SessionLocal
from core.enums import SessionStart
from core.models import Circle, Question, Segment, Story
from core.models import Session as OrmSession
from server.wav_writer import read_slice

log = logging.getLogger(__name__)
router = APIRouter()

TTS_DIR = Path("data") / "tts"

_DENIED = "You do not have access to this audio."
_TTS_NAME = re.compile(r"^(?P<session_id>[0-9a-fA-F-]{36})_[0-9a-zA-Z]+\.(?:mp3|wav)$")
_MEDIA_TYPES = {"mp3": "audio/mpeg", "wav": "audio/wav"}


def _deny() -> HTTPException:
    return HTTPException(status_code=403, detail=_DENIED)


def _within(start: int, end: int, rng: dict) -> bool:
    return rng.get("start_ms", 0) <= start and end <= rng.get("end_ms", 0)


def _may_hear_whole_session(db, viewer_id: str, sess: OrmSession) -> bool:
    if viewer_id not in (sess.participant_ids or []):
        return False
    if sess.started_by == SessionStart.panel_recording:
        return True
    circle = db.get(Circle, sess.circle_id)
    return circle is not None and viewer_id == circle.center_person_id


def _allowed_by_story(db, viewer_id: str, sess: OrmSession, start: int, end: int) -> bool:
    for story in db.query(Story).filter(Story.circle_id == sess.circle_id).all():
        if not can_see(db, viewer_id, story):
            continue
        for src in story.sources or []:
            if src.get("session_id") == sess.id and _within(start, end, src):
                return True
    return False


def _allowed_by_answer(db, viewer_id: str, sess: OrmSession, start: int, end: int) -> bool:
    questions = (
        db.query(Question)
        .filter(Question.circle_id == sess.circle_id, Question.asker_id == viewer_id)
        .all()
    )
    for q in questions:
        ans = q.answer
        if not ans or ans.get("session_id") != sess.id or not _within(start, end, ans):
            continue
        story = db.get(Story, ans.get("story_id"))
        if story is not None and can_see(db, viewer_id, story):
            return True
    return False


def _private_parts_allowed(db, viewer_id: str, session_id: str, start: int, end: int) -> bool:
    """True if every private segment overlapping the range was spoken by the viewer."""
    speakers = (
        db.query(Segment.speaker_id)
        .filter(
            Segment.session_id == session_id,
            Segment.is_private == True,  # noqa: E712
            Segment.start_ms < end,
            Segment.end_ms > start,
        )
        .all()
    )
    return all(speaker_id == viewer_id for (speaker_id,) in speakers)


@router.get("/api/audio/{session_id}")
async def get_audio_slice(
    session_id: str,
    start: int = Query(..., ge=0),
    end: int = Query(..., gt=0),
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    x_circle_id: Annotated[str, Header(alias="x-circle-id")] = "",
):
    """Return a WAV slice of the session audio, if the viewer may hear it."""
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be greater than start.")
    if not x_person_id:
        raise _deny()

    with SessionLocal() as db:
        sess: OrmSession | None = db.get(OrmSession, session_id)
        if sess is None or (x_circle_id and x_circle_id != sess.circle_id):
            raise _deny()

        entitled = (
            _may_hear_whole_session(db, x_person_id, sess)
            or _allowed_by_story(db, x_person_id, sess, start, end)
            or _allowed_by_answer(db, x_person_id, sess, start, end)
        )
        if not entitled or not _private_parts_allowed(db, x_person_id, session_id, start, end):
            raise _deny()

    try:
        wav_bytes = read_slice(session_id, start, end)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio file not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return Response(content=wav_bytes, media_type="audio/wav")


@router.get("/api/tts/{file}")
async def get_tts_file(
    file: str,
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
    x_circle_id: Annotated[str, Header(alias="x-circle-id")] = "",
):
    """Serve a generated reply audio file to a participant of its session."""
    match = _TTS_NAME.match(file)
    if not match:
        raise HTTPException(status_code=400, detail="Invalid file name.")
    if not x_person_id:
        raise _deny()

    with SessionLocal() as db:
        sess = db.get(OrmSession, match["session_id"])
        if (sess is None or x_person_id not in (sess.participant_ids or [])
                or (x_circle_id and x_circle_id != sess.circle_id)):
            raise _deny()

    path = TTS_DIR / file
    if not path.exists():
        raise HTTPException(status_code=404, detail="TTS file not found.")
    return Response(content=path.read_bytes(), media_type=_MEDIA_TYPES[file.rsplit(".", 1)[1]])
