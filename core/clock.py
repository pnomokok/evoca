"""
Central clock — always call now_utc() instead of datetime.now() directly.

now_utc() = (DEMO_NOW or the real now) + the demo offset.

DEMO_NOW can be set (as a UTC ISO 8601 string) to freeze time for demo
recording and scheduler testing without touching any other code:

    DEMO_NOW=2026-10-18T09:55:00+00:00 python -m core.seed

The demo offset exists only with EVOCA_DEMO_MODE=1. POST /api/demo/advance
moves it (core/services/demo.py). It is stored in the database (table
demo_clock), so the API and the MCP server, two processes, see the same time;
each process reads it at most every OFFSET_CACHE_S seconds.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

OFFSET_CACHE_S = 2.0

_cached_offset = 0          # seconds
_cached_at: float | None = None


def demo_mode() -> bool:
    """True when the demo controls are on (EVOCA_DEMO_MODE=1)."""
    return os.environ.get("EVOCA_DEMO_MODE", "").strip() == "1"


def clear_offset_cache() -> None:
    """Forget the cached offset, so the next now_utc() reads the database."""
    global _cached_at
    _cached_at = None


def set_cached_offset(seconds: int) -> None:
    """Use this offset in this process right away (after writing it)."""
    global _cached_offset, _cached_at
    _cached_offset, _cached_at = seconds, time.monotonic()


def demo_offset() -> timedelta:
    """The demo offset; zero outside demo mode, or if it cannot be read."""
    global _cached_offset, _cached_at
    if not demo_mode():
        return timedelta(0)
    t = time.monotonic()
    if _cached_at is None or t - _cached_at >= OFFSET_CACHE_S:
        try:
            # Imported here: core.models imports this module.
            import core.db as cdb
            from core.models import DemoClock
            with cdb.SessionLocal() as db:
                row = db.get(DemoClock, 1)
            _cached_offset = row.offset_seconds if row else 0
            _cached_at = t
        except Exception as exc:
            # A locked database, or no table yet (before init_db): use the last
            # value read, but do not cache it, so the next call reads again (a
            # stale 0 would let the other process publish a new story early).
            log.debug("Demo offset not read, using the last value (%d s): %s", _cached_offset, exc)
    return timedelta(seconds=_cached_offset)


def base_now() -> datetime:
    """DEMO_NOW if set, else the real UTC now (timezone-aware), without the offset."""
    raw = os.environ.get("DEMO_NOW", "").strip()
    if raw:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            # Treat a naive DEMO_NOW as UTC.
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return datetime.now(timezone.utc)


def now_utc() -> datetime:
    """Return the current UTC datetime (timezone-aware).

    If the environment variable DEMO_NOW is set to a valid UTC ISO 8601 string
    it is used instead of the real time, allowing time to be frozen for demos
    and tests. In demo mode the demo offset is added.
    """
    return base_now() + demo_offset()
