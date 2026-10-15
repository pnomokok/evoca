"""
Chat agent for the Evoca voice companion.

ChatAgent.turn(user_text) is the main entry point.
It runs the Bedrock Converse tool loop and stores every exchange as Segments.

Architecture
------------
- The agent is async. BedrockLLM.converse (synchronous boto3) is run in a
  thread via anyio.to_thread.run_sync so it does not block the event loop.
- Identity (person_id, circle_id) is fixed at construction time and comes from
  the HTTP headers read by get_viewer in the MCP server — never from tool args.
- The MCPBridge is kept alive for the entire ChatAgent lifetime (opened on
  first turn, closed on close()).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio

from core.clock import now_utc
from core.db import SessionLocal
from core.enums import SessionStart
from core.services.sessions import add_segment, end_session, start_session
from server.llm import LLM, strip_thinking
from server.mcp_bridge import MCPBridge

_PROMPT_PATH = Path(__file__).parent / "prompts" / "chat_agent.md"
_MAX_TOOL_ROUNDS = 5


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclass
class ToolTrace:
    tool: str
    input: dict[str, Any]
    result_preview: str      # first 300 chars of the serialised result
    ms: int
    is_error: bool


@dataclass
class TurnResult:
    reply_text: str
    trace: list[ToolTrace]
    latency: dict[str, int]  # llm_ms, tools_ms, total_ms


# ---------------------------------------------------------------------------
# ChatAgent
# ---------------------------------------------------------------------------

class ChatAgent:
    """One agent instance per live session.

    Parameters
    ----------
    llm         : Any LLM-protocol object (BedrockLLM or a fake for tests).
    person_id   : UUID of the center person (viewer identity).
    circle_id   : UUID of the circle.
    db_session  : Open SQLAlchemy session (caller manages lifetime).
    bridge      : An already-entered MCPBridge (or a fake for tests).
    """

    def __init__(
        self,
        llm: LLM,
        person_id: str,
        circle_id: str,
        db_session: Any,
        bridge: Any,
    ) -> None:
        self._llm = llm
        self._person_id = person_id
        self._circle_id = circle_id
        self._db = db_session
        self._bridge = bridge

        self._system = [{"text": _PROMPT_PATH.read_text(encoding="utf-8")}]
        self._history: list[dict[str, Any]] = []
        self._tool_config: dict[str, Any] | None = None

        # Session row — created on first turn.
        self._orm_session_id: str | None = None
        self._session_wall_start: float | None = None

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _ensure_session(self) -> str:
        if self._orm_session_id is None:
            sess = start_session(
                self._db,
                self._circle_id,
                SessionStart.spontaneous,
                [self._person_id],
            )
            self._db.commit()
            self._orm_session_id = sess.id
            self._session_wall_start = time.monotonic()
        return self._orm_session_id

    def _elapsed_ms(self) -> int:
        if self._session_wall_start is None:
            return 0
        return int((time.monotonic() - self._session_wall_start) * 1000)

    def _store_segment(
        self,
        speaker_id: str | None,
        text: str,
        start_ms: int,
        end_ms: int,
    ) -> None:
        add_segment(
            self._db,
            self._ensure_session(),
            speaker_id,
            text,
            start_ms,
            end_ms,
        )
        self._db.commit()

    def end(self) -> None:
        """Mark the session finished."""
        if self._orm_session_id:
            end_session(self._db, self._orm_session_id)
            self._db.commit()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def turn(self, user_text: str) -> TurnResult:
        """Process one user utterance and return reply + diagnostics."""
        total_start = time.monotonic()

        # Lazy-fetch the tool config once per agent lifetime.
        if self._tool_config is None:
            self._tool_config = await self._bridge.bedrock_tool_config()

        # Store the user's segment before we do anything.
        seg_start = self._elapsed_ms()
        # Add user message to history.
        self._history.append(
            {"role": "user", "content": [{"text": user_text}]}
        )

        llm_ms_total = 0
        tools_ms_total = 0
        trace: list[ToolTrace] = []

        reply_text = ""

        for _round in range(_MAX_TOOL_ROUNDS):
            # Call the LLM in a thread so we don't block the event loop.
            llm_t0 = time.monotonic()
            response = await anyio.to_thread.run_sync(
                lambda: self._llm.converse(
                    self._system,
                    self._history,
                    self._tool_config,
                )
            )
            llm_ms_total += int((time.monotonic() - llm_t0) * 1000)

            assistant_msg = response["output"]["message"]
            self._history.append(assistant_msg)

            stop_reason = response.get("stopReason", "")

            # Collect any text from this response.
            for block in assistant_msg.get("content", []):
                if "text" in block:
                    reply_text = strip_thinking(block["text"])

            if stop_reason != "tool_use":
                # Model is done — exit the tool loop.
                break

            # --- tool use round -------------------------------------------
            tool_results_content = []
            for block in assistant_msg.get("content", []):
                if "toolUse" not in block:
                    continue
                tool_use = block["toolUse"]
                tool_name = tool_use["name"]
                tool_input = tool_use.get("input", {})
                tool_use_id = tool_use["toolUseId"]

                t0 = time.monotonic()
                is_error = False
                try:
                    result = await self._bridge.call_tool(tool_name, tool_input)
                    result_content = [{"json": result}]
                except Exception as exc:
                    result = {"error": str(exc)}
                    result_content = [{"text": str(exc)}]
                    is_error = True
                tool_ms = int((time.monotonic() - t0) * 1000)
                tools_ms_total += tool_ms

                preview = json.dumps(result)[:300] if result is not None else ""
                trace.append(
                    ToolTrace(
                        tool=tool_name,
                        input=tool_input,
                        result_preview=preview,
                        ms=tool_ms,
                        is_error=is_error,
                    )
                )

                tool_results_content.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": result_content,
                        }
                    }
                )

            # Feed all tool results back as a user message.
            self._history.append(
                {"role": "user", "content": tool_results_content}
            )

        else:
            # Exhausted max rounds without a text reply.
            reply_text = reply_text or "I'm sorry, I ran into a problem. Please try again."

        # Store segments.
        seg_end = self._elapsed_ms()
        self._store_segment(self._person_id, user_text, seg_start, seg_start + 100)
        self._store_segment(None, reply_text, seg_end, seg_end + 100)

        total_ms = int((time.monotonic() - total_start) * 1000)
        return TurnResult(
            reply_text=reply_text,
            trace=trace,
            latency={
                "llm_ms": llm_ms_total,
                "tools_ms": tools_ms_total,
                "total_ms": total_ms,
            },
        )
