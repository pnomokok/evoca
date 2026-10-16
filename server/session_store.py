"""
In-process store for live chat sessions.

Each entry holds the MCPBridge, the ChatAgent, and the DB session
so that successive /turn requests can reuse them.

SessionStore is a plain dict wrapper managed by server/app.py's lifespan.
On startup any DB sessions left open (e.g. from a previous crash) are
marked as ended.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LiveSession:
    session_id: str
    bridge: Any          # MCPBridge (async context)
    agent: Any           # ChatAgent
    db: Any              # SQLAlchemy session


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, LiveSession] = {}

    def put(self, entry: LiveSession) -> None:
        self._sessions[entry.session_id] = entry

    def get(self, session_id: str) -> LiveSession | None:
        return self._sessions.get(session_id)

    def pop(self, session_id: str) -> LiveSession | None:
        return self._sessions.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._sessions)
