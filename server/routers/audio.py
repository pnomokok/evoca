"""
Audio endpoints.

GET /api/audio/{session_id}?start=<ms>&end=<ms>
    Serves a WAV slice with access-control checks.

GET /api/tts/{file}
    Serves generated TTS mp3 files.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response

from core.access import can_see
from core.clock import now_utc
from core.db import SessionLocal
from core.models import Membership, Question, Segment, Story
from core.models import Session as OrmSession
from server.wav_writer import read_slice

log = logging.getLogger(__name__)
router = APIRouter()

TTS_DIR = Path("data") / "tts"


@router.get("/api/audio/{session_id}")
async def get_audio_slice(
    session_id: str,
    start: int = Query(..., ge=0),
    end: int = Query(..., gt=0),
    x_person_id: Annotated[str, Header(alias="x-person-id")] = "",
):
    """Return a WAV slice of the session audio with access control.

    Access rules (privacy):
      1. The range must not overlap any private segment of the session → 403.
      2. The viewer must be allowed to hear it:
         a. The viewer is the session's center person (participant_ids[0]), OR
         b. The range lies within the sources of a story the viewer can_see, OR
         c. The range lies within the answer range of a question the viewer asked.
      Otherwise → 403.
    """
    if not x_person_id:
        raise HTTPException(status_code=403, detail="X-Person-Id header required.")
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be greater than start.")

    with SessionLocal() as db:
        sess: OrmSession | None = db.get(OrmSession, session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail="Session not found.")

        # Membership check.
        member = (
            db.query(Membership)
            .filter(
                Membership.person_id == x_person_id,
                Membership.circle_id == sess.circle_id,
            )
            .first()
        )
        if member is None:
            raise HTTPException(status_code=403, detail="Not a member of this circle.")

        # Rule 1: no overlap with any private segment.
        private_segs = (
            db.query(Segment)
            .filter(
                Segment.session_id == session_id,
                Segment.is_private == True,  # noqa: E712
            )
            .all()
        )
        for seg in private_segs:
            # Ranges overlap if start < seg.end_ms and end > seg.start_ms.
            if start < seg.end_ms and end > seg.start_ms:
                raise HTTPException(
                    status_code=403,
                    detail="The requested range overlaps a private segment.",
                )

        # Rule 2: check viewer entitlement.
        center_id = sess.participant_ids[0] if sess.participant_ids else None
        if x_person_id == center_id:
            # Center person may always hear their own session.
            pass
        else:
            # Check story sources.
            allowed_by_story = False
            stories = (
                db.query(Story)
                .filter(Story.circle_id == sess.circle_id)
                .all()
            )
            for story in stories:
                if not can_see(db, x_person_id, story):
                    continue
                for src in (story.sources or []):
                    if src.get("session_id") != session_id:
                        continue
                    s_start = src.get("start_ms", 0)
                    s_end   = src.get("end_ms", 0)
                    # The requested range must be fully within the source range.
                    if start >= s_start and end <= s_end:
                        allowed_by_story = True
                        break
                if allowed_by_story:
                    break

            # Check question answers.
            allowed_by_question = False
            if not allowed_by_story:
                questions = (
                    db.query(Question)
                    .filter(
                        Question.circle_id == sess.circle_id,
                        Question.asker_id == x_person_id,
                    )
                    .all()
                )
                for q in questions:
                    ans = q.answer
                    if not ans:
                        continue
                    if ans.get("session_id") != session_id:
                        continue
                    a_start = ans.get("start_ms", 0)
                    a_end   = ans.get("end_ms", 0)
                    if start >= a_start and end <= a_end:
                        allowed_by_question = True
                        break

            if not allowed_by_story and not allowed_by_question:
                raise HTTPException(
                    status_code=403,
                    detail="You do not have access to this audio range.",
                )

    # All checks passed; stream the slice.
    try:
        wav_bytes = read_slice(session_id, start, end)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Audio file not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return Response(content=wav_bytes, media_type="audio/wav")


@router.get("/api/tts/{file}")
async def get_tts_file(file: str):
    """Serve a generated TTS mp3 file."""
    # Sanitise: no path traversal.
    if "/" in file or "\\" in file or ".." in file:
        raise HTTPException(status_code=400, detail="Invalid file name.")
    path = TTS_DIR / file
    if not path.exists():
        raise HTTPException(status_code=404, detail="TTS file not found.")
    return Response(content=path.read_bytes(), media_type="audio/mpeg")
