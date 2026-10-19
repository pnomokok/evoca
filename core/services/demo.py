"""
Demo controls (EVOCA_DEMO_MODE=1 only), behind /api/demo/* (server/routers/demo.py).

Judges cannot restart the servers with a new DEMO_NOW, so the demo moves its
clock at runtime:

  advance  add hours to the demo offset (core/clock.py), then publish due
           stories and run the invitation scheduler, so the effect shows at once
  clock    the current demo time and offset
  reset    rebuild the demo database from the seed and delete the files of
           everything recorded since (session audio, TTS, photos)

Reset works only when EVOCA_DB_PATH is data/demo.db (scripts/run_demo.py);
any other database, data/evoca.db and data/browser.db included, is refused.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session as DbSession

import core.db as cdb
from core import clock
from core.models import DemoClock, StoryPhoto
from core.models import Session as OrmSession
from core.services.circles import demo_circle, people_in_circle
from core.services.invitations import run_invitations
from core.services.publisher import publish_due_stories

log = logging.getLogger(__name__)

MIN_HOURS, MAX_HOURS = 1, 72

REPO = Path(__file__).resolve().parent.parent.parent
DEMO_DB = REPO / "data" / "demo.db"

# Where session audio and TTS live (relative to the working directory, like
# server/wav_writer.py and server/routers/device.py); photos are in the demo
# database's own folder (core/services/photos.py photo_dir()).
FILE_DIRS = (Path("data") / "audio", Path("data") / "tts")


class ResetRefused(RuntimeError):
    """Reset would touch the real database."""


def clock_state(db: DbSession) -> dict[str, Any]:
    row = db.get(DemoClock, 1)
    seconds = row.offset_seconds if row else 0
    clock.set_cached_offset(seconds)
    return {"now": clock.now_utc().isoformat(), "offset_hours": seconds / 3600}


def advance(db: DbSession, hours: float) -> dict[str, Any]:
    """Move the demo clock forward and run the time-driven jobs once.

    Waits one offset cache period before returning, so the other process
    (the MCP server) also sees the new time by then.
    """
    if not MIN_HOURS <= hours <= MAX_HOURS:
        raise ValueError(f"hours must be between {MIN_HOURS} and {MAX_HOURS}.")
    row = db.get(DemoClock, 1)
    if row is None:
        row = DemoClock(id=1, offset_seconds=0)
        db.add(row)
    row.offset_seconds += round(hours * 3600)
    db.commit()
    clock.set_cached_offset(row.offset_seconds)

    published = publish_due_stories(db)
    invited = run_invitations(db)
    log.info("Demo clock +%s h: now %s, published %d, invitations %d",
             hours, clock.now_utc().isoformat(), len(published), len(invited))
    time.sleep(clock.OFFSET_CACHE_S)
    return clock_state(db)


def db_path() -> Path | None:
    """The database file reset would rebuild (None for an in-memory database)."""
    return None if cdb._in_memory else Path(cdb._abs_path).resolve()


def check_resettable() -> None:
    path = db_path()
    if path is None or path != DEMO_DB.resolve():
        raise ResetRefused(
            f"Reset only rebuilds data/demo.db, but the database is {path or ':memory:'}. "
            "Start the demo with: python scripts/run_demo.py"
        )


def _recorded_files(db: DbSession) -> list[Path]:
    """Audio and TTS files of non-seed sessions, and every photo (the seed adds its own again)."""
    from core.seed import SEED_SESSION_ID

    files: list[Path] = []
    for sess in db.query(OrmSession).filter(OrmSession.id != SEED_SESSION_ID).all():
        if sess.audio_path:
            files.append(Path(sess.audio_path))
        files.extend((Path("data") / "tts").glob(f"{sess.id}_*"))
    files.extend(Path(p.path) for p in db.query(StoryPhoto).all() if p.path)
    return files


def _inside_file_dirs(path: Path) -> bool:
    from core.services.photos import photo_dir

    resolved = path.resolve()
    return any(resolved.parent == d.resolve() for d in (*FILE_DIRS, photo_dir()))


def reset() -> list[dict[str, Any]]:
    """Rebuild the demo database from the seed; returns the demo circle's
    people (the shape of GET /api/people?circle_id=).

    The caller ends live device sessions (and closes their database sessions)
    first. Only files inside data/audio, data/tts and the demo database's
    photos folder (data/photos-demo) are deleted.
    """
    from core.seed import reset_and_seed

    check_resettable()
    with cdb.SessionLocal() as db:
        files = _recorded_files(db)

    clock.set_cached_offset(0)       # the seed must use the undelayed time
    reset_and_seed(force=True)       # drops every table, demo_clock included
    clock.set_cached_offset(0)

    for f in files:
        if f.exists() and _inside_file_dirs(f):
            try:
                f.unlink()
            except OSError as exc:
                log.warning("Demo reset could not delete %s: %s", f, exc)
    with cdb.SessionLocal() as db:
        return people_in_circle(db, demo_circle(db)["id"])
