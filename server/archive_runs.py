"""
Archive runs in flight, per circle (in this process).

A run is registered when its session ends, before the response is sent
(server/routers/device.py _finish, server/routers/recordings.py), and released
when the archivist is done, failed or was skipped. The demo's "advance the
clock" waits for them (server/routers/demo.py): a story saved after the clock
moved would start its 24-hour window from the new time.

Only a count per circle is kept: no session ids, no content.
"""

from __future__ import annotations

import time

import anyio

_runs: dict[str, int] = {}


def begin(circle_id: str) -> None:
    _runs[circle_id] = _runs.get(circle_id, 0) + 1


def end(circle_id: str) -> None:
    left = _runs.get(circle_id, 0) - 1
    if left > 0:
        _runs[circle_id] = left
    else:
        _runs.pop(circle_id, None)


def busy(circle_id: str) -> bool:
    return _runs.get(circle_id, 0) > 0


async def wait_idle(circle_id: str, timeout_s: float, poll_s: float = 0.25) -> bool:
    """Wait until no archive run of the circle is in flight. True if it got
    there, False after timeout_s."""
    deadline = time.monotonic() + timeout_s
    while busy(circle_id):
        if time.monotonic() >= deadline:
            return False
        await anyio.sleep(poll_s)
    return True
