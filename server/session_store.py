"""
In-process store for live chat sessions.

Each entry holds the ChatAgent (with its conversation history) and its DB
session so that successive /turn requests can reuse them, plus:
  - lock: one asyncio.Lock per session, so two requests for the same session
    (a double tap, a retry) never interleave their WAV appends and agent turns.
  - seen_questions: every item returned by get_pending_questions during the
    session, by question_id, so a question card can be built when the agent
    marks one as asked (possibly in a later turn).
  - last_question: the question sentence of the agent's latest reply, given to
    Whisper as context for the person's answer.

No MCP client is kept here: an MCP client must be closed in the same task that
opened it, so the device router opens one per request ("async with") and hands
it to the agent for that request only.

SessionStore is a plain dict wrapper managed by server/app.py's lifespan.
On startup any DB sessions left open (e.g. from a previous crash) are
marked as ended.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LiveSession:
    session_id: str
    owner_id: str        # the person who started the session (the center)
    agent: Any           # ChatAgent
    db: Any              # SQLAlchemy session used by the agent
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    seen_questions: dict[str, dict] = field(default_factory=dict)
    last_question: str | None = None   # the agent's latest question, a hint for Whisper
    circle_id: str = ""                # the session's circle (X-Circle-Id must match it)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, LiveSession] = {}

    def put(self, entry: LiveSession) -> None:
        self._sessions[entry.session_id] = entry

    def get(self, session_id: str) -> LiveSession | None:
        return self._sessions.get(session_id)

    def pop(self, session_id: str) -> LiveSession | None:
        return self._sessions.pop(session_id, None)

    def all(self) -> list[LiveSession]:
        return list(self._sessions.values())

    def __len__(self) -> int:
        return len(self._sessions)
