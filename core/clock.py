"""
Central clock — always call now_utc() instead of datetime.now() directly.

Later, DEMO_NOW can be set (as a UTC ISO 8601 string) to freeze time for
demo recording and scheduler testing without touching any other code.

    DEMO_NOW=2026-10-18T09:55:00+00:00 python -m core.seed
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


def now_utc() -> datetime:
    """Return the current UTC datetime (timezone-aware).

    If the environment variable DEMO_NOW is set to a valid UTC ISO 8601 string
    it is returned instead, allowing time to be frozen for demos and tests.
    """
    raw = os.environ.get("DEMO_NOW", "").strip()
    if raw:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            # Treat a naive DEMO_NOW as UTC.
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    return datetime.now(timezone.utc)
