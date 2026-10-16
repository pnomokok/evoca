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
- The tool config is restricted to CHAT_TOOLS, so the model never sees
  archivist tools such as save_story. A call to any other tool gets an error
  result and never reaches the MCP server.
- end_conversation is a LOCAL tool, handled here and never sent to the MCP
  server. When the model calls it, the turn ends without another LLM call and
  TurnResult.session_should_end is True.
- Every reply passes through clean_reply(): quotation marks are removed, at
  most one question is kept, and a goodbye keeps no question at all. The
  cleaned text is what is returned, stored as a Segment and kept in history.
- Fallback for models that say goodbye without calling end_conversation: if
  the person clearly asked to stop (asks_to_stop) and the reply contains no
  question, the turn is treated as end_conversation.

Privacy ("don't let anyone hear that")
--------------------------------------
- keep_private(scope) is a LOCAL tool. The model only names the scope; the code
  turns it into the exact segments (no invented milliseconds):
    this_turn      the secret and the request are in the current turn
    previous_turn  the secret was in the previous turn; hides it and this turn
    next           the person is about to tell a secret; hides the next turn
  Each scope also hides the agent's replies to the hidden user turns.
- Hidden turns are scrubbed from the agent's own history at the end of the
  turn (replaced by PRIVATE_PLACEHOLDER), so nothing after the mark sends the
  text to the LLM again. Their segments become pending marks; the MCP tool
  mark_private (called by this code, never by the model) makes them is_private.
- Fail closed: a mark that fails stays pending (has_pending_private); the
  backend retries at session end and does not run the archivist if it still
  fails. If a reply promises privacy without any mark, the code applies
  "this_turn" itself so the promise is true.
- Reactions: after a reply that names every person who reacted to a story,
  the code calls mark_reactions_delivered for that story, so it is not
  announced again in the next session.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio

from core.clock import now_utc
from core.db import SessionLocal
from core.enums import SessionStart
from core.models import Segment
from core.services.sessions import add_segment, end_session, start_session
from server.llm import LLM, BedrockLLM, strip_thinking
from server.mcp_bridge import MCPBridge

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "chat_agent.md"
_MAX_TOOL_ROUNDS = 5

# MCP tools the model may call; get_linked_playlist is picked up
# automatically once the MCP server provides it.
CHAT_TOOLS = frozenset({
    "get_session_context",
    "get_pending_questions",
    "mark_question_asked",
    "set_story_access",
    "search_archive",
    "get_linked_playlist",
})

# MCP tools called by this agent's own code, never offered to the model.
CODE_TOOLS = frozenset({"mark_private", "mark_reactions_delivered"})

END_CONVERSATION = "end_conversation"
KEEP_PRIVATE = "keep_private"
# Tools handled inside ChatAgent itself, offered next to the MCP tools.
LOCAL_TOOLS = frozenset({END_CONVERSATION, KEEP_PRIVATE})
PRIVATE_SCOPES = ("this_turn", "previous_turn", "next")
_KEEP_PRIVATE_SPEC = {
    "toolSpec": {
        "name": KEEP_PRIVATE,
        "description": (
            "Keep part of the conversation private: nobody in the family will hear it and it "
            "stays out of the archive. Call it as soon as the person asks that something is not "
            "shared (for example 'don't tell anyone', 'keep this between us'), before you promise "
            "anything. scope: this_turn = the secret is in what the person just said, together "
            "with the request; previous_turn = the secret was in their previous answer and now "
            "they ask to keep it private (hides both); next = they are about to tell you "
            "something secret. When unsure, use previous_turn."
        ),
        "inputSchema": {"json": {
            "type": "object",
            "properties": {"scope": {"type": "string", "enum": list(PRIVATE_SCOPES)}},
            "required": ["scope"],
        }},
    }
}
PRIVATE_PLACEHOLDER = (
    "[The speaker asked to keep this part private. Do not mention or repeat it.]"
)
_END_CONVERSATION_SPEC = {
    "toolSpec": {
        "name": END_CONVERSATION,
        "description": (
            "End the conversation. Call this when the person wants to stop, "
            "in the same turn as your warm goodbye."
        ),
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }
}

GOODBYE_FALLBACK = "Thank you for sharing your memories today. Goodbye for now."

# A reply that promises privacy. If no mark was made in that turn, the code
# applies "this_turn" so the promise is true.
_PRIVACY_CLAIM = re.compile(
    r"\b(?:"
    r"(?:keep|kept|stay|stays|remain|remains)\s+(?:\w+\s+){0,3}"
    r"(?:private|secret|between us|between you and me)"
    r"|between (?:us|you and me)"
    r"|(?:no ?one|nobody)\s+(?:else\s+)?(?:will|is going to|can)\s+(?:hear|know|find out)"
    r"|won'?t tell (?:anyone|anybody|a soul)"
    r"|(?:is|are) safe with me"
    r")",
    re.IGNORECASE,
)


def claims_privacy(text: str) -> bool:
    """True if a reply promises that something stays private."""
    return bool(_PRIVACY_CLAIM.search(text.replace("\u2019", "'")))

DEFAULT_CHAT_MODEL = "us.amazon.nova-2-lite-v1:0"
DEFAULT_CHAT_TEMPERATURE = 0.3


def chat_llm() -> BedrockLLM:
    """Bedrock LLM for the chat agent (EVOCA_CHAT_MODEL, EVOCA_CHAT_TEMPERATURE)."""
    return BedrockLLM(
        model_id=os.environ.get("EVOCA_CHAT_MODEL", DEFAULT_CHAT_MODEL),
        temperature=float(os.environ.get("EVOCA_CHAT_TEMPERATURE", DEFAULT_CHAT_TEMPERATURE)),
    )


# ---------------------------------------------------------------------------
# Reply guards (pure functions)
# ---------------------------------------------------------------------------

_QUOTES = re.compile('["\u201c\u201d]')
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_ABBREVIATION = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|St)\.$")


def strip_quotes(text: str) -> str:
    """Remove the quotation marks " \u201c \u201d; they do not work in speech."""
    return _QUOTES.sub("", text)


def split_sentences(text: str) -> list[str]:
    """Split on whitespace after . ! or ?, keeping titles like "Mr." attached."""
    sentences: list[str] = []
    for piece in _SENTENCE_BREAK.split(text.strip()):
        if sentences and _ABBREVIATION.search(sentences[-1]):
            sentences[-1] += " " + piece
        elif piece:
            sentences.append(piece)
    return sentences


def _is_question(sentence: str) -> bool:
    return sentence.rstrip().endswith("?")


def keep_last_question(text: str) -> str:
    """With more than one question, drop all but the last question sentence."""
    sentences = split_sentences(text)
    questions = [i for i, s in enumerate(sentences) if _is_question(s)]
    if len(questions) <= 1:
        return text
    last = questions[-1]
    return " ".join(s for i, s in enumerate(sentences) if not _is_question(s) or i == last)


def remove_questions(text: str) -> str:
    """Drop every question sentence."""
    return " ".join(s for s in split_sentences(text) if not _is_question(s))


# Conservative stop detection: a few explicit phrases only, so a story does
# not end the session by accident:
# - "I'm tired" does not count when followed by "of" ("I'm tired of the rain");
# - "goodbye" counts only at the start of a sentence ("He said goodbye to ..." does not);
# - "that's enough" counts only at the end of a sentence or with "for today/now".
_STOP_PHRASES = re.compile(
    r"\b(?:let'?s stop|let us stop|stop for today|continue tomorrow|talk tomorrow)\b"
    r"|\bi(?:'?m| am) (?:so |very |a bit )?tired\b(?! of)"
    r"|\bthat(?:'?s| is) enough(?: for (?:today|now))?\s*(?:[.!]|$)"
    r"|(?:^|[.!?]\s+)(?:good-?bye|bye for now)\b"
)


def asks_to_stop(text: str) -> bool:
    """True if the person's message clearly asks to end the conversation."""
    return bool(_STOP_PHRASES.search(text.lower().replace("\u2019", "'")))


def clean_reply(text: str, ending: bool) -> str:
    """Apply the reply guards. A goodbye (ending=True) keeps no question at all."""
    text = keep_last_question(strip_quotes(text).strip())
    if ending:
        text = remove_questions(text) or GOODBYE_FALLBACK
    return text


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclass
class ToolTrace:
    tool: str
    input: dict[str, Any]
    result: Any              # full structured result (not sent to the client)
    result_preview: str      # first 300 chars of the serialised result (for API responses)
    ms: int
    is_error: bool


@dataclass
class TurnResult:
    reply_text: str
    trace: list[ToolTrace]
    latency: dict[str, int]  # llm_ms, tools_ms, total_ms
    session_should_end: bool = False  # the model called end_conversation
    marked_private: bool = False      # this turn was hidden (its text left the history)


# ---------------------------------------------------------------------------
# ChatAgent
# ---------------------------------------------------------------------------

@dataclass
class _TurnRecord:
    """What one turn left behind, so a privacy scope can find it later."""
    user_block: dict[str, Any] | None         # history block with the user's words
    assistant_blocks: list[dict[str, Any]]    # history blocks with the agent's words
    segment_ids: list[str]                    # the user's and the agent's segments
    hidden: bool = False


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
        session_id: str | None = None,
        flush_marks_in_turn: bool = True,
    ) -> None:
        self._llm = llm
        self._person_id = person_id
        self._circle_id = circle_id
        self._db = db_session
        self._bridge = bridge

        self._system = [{"text": _PROMPT_PATH.read_text(encoding="utf-8")}]
        self._history: list[dict[str, Any]] = []
        self._tool_config: dict[str, Any] | None = None

        # Session row — created on first turn unless the caller already made it
        # (the FastAPI backend passes session_id).
        self._orm_session_id: str | None = session_id
        self._session_wall_start: float | None = time.monotonic() if session_id else None
        # The agent's latest Segment, so its span can be set once TTS audio exists.
        self._last_agent_segment_id: str | None = None

        # Privacy: per-turn records, a pending "next" scope, and segment ids
        # still to be marked private through MCP. The backend sets
        # flush_marks_in_turn=False and flushes after the reply's audio span is
        # known; tests and the CLI flush at the end of each turn.
        self._turns: list[_TurnRecord] = []
        self._hide_next = False
        self.pending_private: list[str] = []
        self._flush_marks_in_turn = flush_marks_in_turn

        # Reactions told in this session: story_id -> first names of reactors.
        self._undelivered: dict[str, set[str]] = {}

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
        words: list[dict] | None = None,
    ) -> str:
        seg = add_segment(
            self._db,
            self._ensure_session(),
            speaker_id,
            text,
            start_ms,
            end_ms,
            words=words or [],
        )
        self._db.commit()
        return seg.id

    def set_last_agent_span(self, start_ms: int, end_ms: int) -> None:
        """Set the real audio span of the agent's latest reply (after TTS)."""
        if self._last_agent_segment_id is None:
            return
        seg = self._db.get(Segment, self._last_agent_segment_id)
        if seg is not None:
            seg.start_ms = start_ms
            seg.end_ms = end_ms
            self._db.commit()

    def set_bridge(self, bridge: Any) -> None:
        """Swap the MCP bridge. The FastAPI backend opens one per request (an MCP
        client must be closed in the task that opened it) and sets it here."""
        self._bridge = bridge

    @property
    def has_pending_private(self) -> bool:
        return bool(self.pending_private)

    def _hide(self, record: _TurnRecord) -> None:
        """Scrub a turn from the history and queue its segments to be marked private."""
        if record.user_block is not None:
            record.user_block["text"] = PRIVATE_PLACEHOLDER
        for block in record.assistant_blocks:
            block["text"] = PRIVATE_PLACEHOLDER
        for seg_id in record.segment_ids:
            if seg_id not in self.pending_private:
                self.pending_private.append(seg_id)
        record.hidden = True

    async def flush_private_marks(self) -> list[ToolTrace]:
        """Mark every pending segment private through MCP (exact segment
        boundaries). Failed marks stay pending. Returns trace entries."""
        traces: list[ToolTrace] = []
        for seg_id in list(self.pending_private):
            seg = self._db.get(Segment, seg_id)
            if seg is None:
                self.pending_private.remove(seg_id)
                continue
            args = {"start_ms": seg.start_ms, "end_ms": seg.end_ms}
            t0 = time.monotonic()
            try:
                result = await self._bridge.call_tool("mark_private", args)
                self.pending_private.remove(seg_id)
                is_error = False
            except Exception as exc:
                result = {"error": str(exc)}
                is_error = True
                log.warning("mark_private failed for segment %s (session %s): %s",
                            seg_id, self._orm_session_id, exc)
            traces.append(ToolTrace(
                tool="mark_private", input=args, result=result,
                result_preview=json.dumps(result)[:300],
                ms=int((time.monotonic() - t0) * 1000), is_error=is_error,
            ))
        return traces

    def _remember_reactions(self, context: Any) -> None:
        if not isinstance(context, dict):
            return
        self._undelivered = {}
        for r in context.get("undelivered_reactions", []):
            if r.get("story_id") and r.get("person_name"):
                self._undelivered.setdefault(r["story_id"], set()).add(r["person_name"].split()[0])

    async def _deliver_reactions(self, reply_text: str, trace: list[ToolTrace]) -> None:
        """Mark reactions delivered for stories whose every reactor was named."""
        told = sorted(
            story_id for story_id, names in self._undelivered.items()
            if all(re.search(rf"\b{re.escape(n)}\b", reply_text, re.IGNORECASE) for n in names)
        )
        if not told:
            return
        args = {"story_ids": told}
        t0 = time.monotonic()
        try:
            result = await self._bridge.call_tool("mark_reactions_delivered", args)
            for story_id in told:
                self._undelivered.pop(story_id, None)
            is_error = False
        except Exception as exc:
            result, is_error = {"error": str(exc)}, True
            log.warning("mark_reactions_delivered failed (session %s): %s", self._orm_session_id, exc)
        trace.append(ToolTrace(
            tool="mark_reactions_delivered", input=args, result=result,
            result_preview=json.dumps(result)[:300],
            ms=int((time.monotonic() - t0) * 1000), is_error=is_error,
        ))

    def end(self) -> None:
        """Mark the session finished."""
        if self._orm_session_id:
            end_session(self._db, self._orm_session_id)
            self._db.commit()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def turn(
        self,
        user_text: str,
        store_user: bool = True,
        user_start_ms: int | None = None,
        user_end_ms: int | None = None,
        user_words: list[dict] | None = None,
    ) -> TurnResult:
        """Process one user utterance and return reply + diagnostics.

        Optional real-span arguments (set by the FastAPI backend after STT):
          user_start_ms / user_end_ms   – the user's audio position in the
                                           session WAV.
          user_words                    – Whisper word timestamps shifted to WAV
                                           positions.
        The agent's reply gets a placeholder span; once its TTS audio is in the
        WAV the backend calls set_last_agent_span().
        """
        total_start = time.monotonic()

        # Lazy-fetch the tool config once per agent lifetime, limited to CHAT_TOOLS.
        if self._tool_config is None:
            full = await self._bridge.bedrock_tool_config()
            self._tool_config = {
                "tools": [t for t in full["tools"] if t["toolSpec"]["name"] in CHAT_TOOLS]
                + [_END_CONVERSATION_SPEC, _KEEP_PRIVATE_SPEC]
            }

        # Store the user's segment before we do anything.
        seg_start = self._elapsed_ms()
        # Add user message to history. After end_conversation the history may
        # already end with a user message (the tool results); roles must
        # alternate, so the text joins that message.
        user_block = {"text": user_text}
        if self._history and self._history[-1]["role"] == "user":
            self._history[-1]["content"].append(user_block)
        else:
            self._history.append({"role": "user", "content": [user_block]})

        llm_ms_total = 0
        tools_ms_total = 0
        trace: list[ToolTrace] = []

        reply_text = ""
        reply_block: dict[str, Any] | None = None   # history block holding the reply
        text_blocks: list[dict[str, Any]] = []      # every agent text block of this turn
        ending = False
        requested_scope: str | None = None

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
                    reply_block = block
                    text_blocks.append(block)

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
                if tool_name == END_CONVERSATION:
                    # Local tool: handled here, never sent to the MCP server.
                    ending = True
                    result = {"status": "ok"}
                    result_content = [{"json": result}]
                elif tool_name == KEEP_PRIVATE:
                    # Local tool: the code turns the scope into segments at the end of the turn.
                    scope = tool_input.get("scope")
                    if scope in PRIVATE_SCOPES:
                        requested_scope = scope
                        result = {"status": "ok", "kept_private": (
                            "what the person says next" if scope == "next" else "that part"
                        )}
                        result_content = [{"json": result}]
                    else:
                        result = {"error": f"scope must be one of {', '.join(PRIVATE_SCOPES)}"}
                        result_content = [{"text": result["error"]}]
                        is_error = True
                else:
                    try:
                        if tool_name not in CHAT_TOOLS:
                            raise RuntimeError(
                                f"Tool '{tool_name}' is not available to the chat agent."
                            )
                        result = await self._bridge.call_tool(tool_name, tool_input)
                        result_content = [{"json": result}]
                        if tool_name == "get_session_context":
                            self._remember_reactions(result)
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
                        result=result,
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

            if ending:
                # The goodbye was said in this message; no second LLM call.
                break

        else:
            # Exhausted max rounds without a text reply.
            reply_text = reply_text or "I'm sorry, I ran into a problem. Please try again."

        reply_text = clean_reply(reply_text, ending)
        if not ending and asks_to_stop(user_text) and "?" not in reply_text:
            # The model said goodbye without calling end_conversation.
            ending = True
        if reply_block is not None:
            # Keep the history in line with what was actually spoken.
            reply_block["text"] = reply_text

        # Store segments.
        seg_end = self._elapsed_ms()
        segment_ids: list[str] = []
        if store_user:
            u_start = user_start_ms if user_start_ms is not None else seg_start
            u_end   = user_end_ms   if user_end_ms   is not None else seg_start + 100
            segment_ids.append(self._store_segment(
                self._person_id, user_text, u_start, u_end,
                words=user_words or [],
            ))
        self._last_agent_segment_id = self._store_segment(
            None, reply_text, seg_end, seg_end + 100
        )
        segment_ids.append(self._last_agent_segment_id)

        # Privacy: turn the scope into turns to hide (code, not the model).
        record = _TurnRecord(user_block if store_user else None, text_blocks, segment_ids)
        previous = next((t for t in reversed(self._turns) if t.user_block is not None), None)
        self._turns.append(record)
        to_hide: list[_TurnRecord] = []
        if self._hide_next and store_user:
            to_hide.append(record)            # the secret announced last turn
            self._hide_next = False
        if requested_scope == "this_turn":
            to_hide.append(record)
        elif requested_scope == "previous_turn":
            to_hide.append(record)
            if previous is not None:
                to_hide.append(previous)
        elif requested_scope == "next":
            self._hide_next = True
        elif not to_hide and claims_privacy(reply_text):
            # The reply promised privacy without a mark: make the promise true.
            log.warning("Reply claimed privacy without keep_private; applying this_turn "
                        "(session %s)", self._orm_session_id)
            to_hide.append(record)
        for rec in to_hide:
            if not rec.hidden:
                self._hide(rec)

        await self._deliver_reactions(reply_text, trace)
        if self._flush_marks_in_turn and self.pending_private:
            trace.extend(await self.flush_private_marks())

        total_ms = int((time.monotonic() - total_start) * 1000)
        return TurnResult(
            reply_text=reply_text,
            trace=trace,
            latency={
                "llm_ms": llm_ms_total,
                "tools_ms": tools_ms_total,
                "total_ms": total_ms,
            },
            session_should_end=ending,
            marked_private=record.hidden,
        )
