"""
Archivist agent for Evoca.

ArchivistAgent.run(session_id) processes one finished session in the
background, following the archivist steps in docs/PROJECT.md:

1. get_session_transcript   — read the non-private segments
2. save_story               — one story per distinct memory
3. record_answer            — for asked questions answered in this session
4. add_question             — at most two follow_up questions

link_stories and find_gaps are used only once the MCP server offers them.

Architecture
------------
- Same Bedrock Converse tool loop as ChatAgent, but one-shot: there is no live
  speaker and nothing is stored as Segments.
- The tool config is restricted to the archivist's tools, so the model cannot
  call chat-agent tools such as mark_question_asked.
- The question limit is enforced here as well as in the prompt: extra
  add_question calls get an error result and never reach the MCP server.
- So are duplicates: an add_question whose normalized text appears in one of
  the companion's segments of this session, or equals a waiting or asked
  question of the circle, is rejected the same way. The guard reads the
  transcript and the waiting questions itself (not shown in the trace) when
  the model has not fetched them.
- And so is answer matching: before record_answer reaches the MCP server, a
  checker LLM (temperature 0) gets the question and the speaker's own words in
  the answer range, and must say "yes" that they answer it. Anything else
  rejects the call and the question stays unanswered. A wrong answer would let
  a grandchild hear the wrong part (docs/PROJECT.md, risks); unanswered is fine.
  The words come from the non-private transcript the archivist already read.
- Declines work the same way: mark_question_declined goes through only when the
  checker confirms the speaker clearly declined that question in that range
  (when unsure, a question is not declined).
- At the end of the run, every question that is still "asked" (not answered,
  not declined) is returned to "waiting" via reopen_question, so it is asked
  again in a later session. These calls are made by this code, not the model.
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

from server.agents.chat_agent import ToolTrace
from server.llm import LLM, BedrockLLM, strip_thinking

log = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "archivist_agent.md"
_MAX_TOOL_ROUNDS = 15
_MAX_QUESTIONS = 2

DEFAULT_ARCHIVIST_MODEL = "us.amazon.nova-2-lite-v1:0"
DEFAULT_ARCHIVIST_TEMPERATURE = 0.2

# Tools the archivist may use; link_stories and find_gaps are picked up
# automatically once the server provides them.
_ARCHIVIST_TOOLS = {
    "get_session_transcript",
    "save_story",
    "record_answer",
    "add_question",
    "mark_question_declined",
    "link_stories",
    "find_gaps",
}


_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_question(text: str) -> str:
    """Lowercase, drop punctuation and collapse whitespace."""
    return " ".join(_PUNCTUATION.sub("", text.lower()).split())


def archivist_model_id() -> str:
    return os.environ.get("EVOCA_ARCHIVIST_MODEL", DEFAULT_ARCHIVIST_MODEL)


_ANSWER_CHECK_PROMPT = """You check one thing: does a passage from a recorded conversation directly answer a family member's question?
Reply with exactly one word: yes or no.
yes: the speaker talks about exactly what the question asks.
no: the passage is about something else, only brushes the topic, or you are unsure.
A warm or interesting story about something else is not an answer."""


_DECLINE_CHECK_PROMPT = """You check one thing: in a passage from a recorded conversation, does the speaker decline to talk about what a family member's question asks?
Reply with exactly one word: yes or no.
yes: the speaker clearly says they do not want to talk about it, for example "I'd rather not talk about that".
no: the speaker answers, tells something else without refusing, says they do not remember, or you are unsure."""


_FIRST_WORD = re.compile(r"[a-z]+")


def checker_said_yes(verdict: str) -> bool:
    """True only if the checker's first word is "yes".

    Models format freely ("**yes**", "Yes.", "yes - the passage ..."), so the
    first word is read ignoring Markdown and punctuation. Anything else,
    including an empty reply, counts as no.
    """
    match = _FIRST_WORD.search(verdict.lower())
    return match is not None and match.group(0) == "yes"


def answer_check_llm() -> BedrockLLM:
    """Bedrock LLM for the answer check: the archivist's model at temperature 0."""
    return BedrockLLM(model_id=archivist_model_id(), max_tokens=10, temperature=0.0)


def archivist_llm() -> BedrockLLM:
    """Bedrock LLM for the archivist (EVOCA_ARCHIVIST_MODEL, EVOCA_ARCHIVIST_TEMPERATURE)."""
    return BedrockLLM(
        model_id=archivist_model_id(),
        max_tokens=4096,
        temperature=float(
            os.environ.get("EVOCA_ARCHIVIST_TEMPERATURE", DEFAULT_ARCHIVIST_TEMPERATURE)
        ),
    )


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class ArchiveResult:
    session_id: str
    story_ids: list[str] = field(default_factory=list)
    answers_recorded: list[str] = field(default_factory=list)       # question ids
    questions_added: list[dict[str, str]] = field(default_factory=list)  # {question_id, status}
    questions_declined: list[str] = field(default_factory=list)  # question ids, confirmed declines
    questions_reopened: list[str] = field(default_factory=list)  # question ids, back to "waiting"
    final_text: str = ""
    trace: list[ToolTrace] = field(default_factory=list)
    latency: dict[str, int] = field(default_factory=dict)          # llm_ms, tools_ms, total_ms


# ---------------------------------------------------------------------------
# ArchivistAgent
# ---------------------------------------------------------------------------

class ArchivistAgent:
    """One agent instance per archiving run.

    Parameters
    ----------
    llm         : Any LLM-protocol object (BedrockLLM or a fake for tests).
    person_id   : UUID of the viewer identity (the circle's center person).
    circle_id   : UUID of the circle.
    bridge      : An already-entered MCPBridge (or a fake for tests).
    checker_llm : LLM for the answer check (answer_check_llm() in production);
                  defaults to llm.
    """

    def __init__(
        self,
        llm: LLM,
        person_id: str,
        circle_id: str,
        bridge: Any,
        checker_llm: LLM | None = None,
    ) -> None:
        self._llm = llm
        self._checker_llm = checker_llm or llm
        self._person_id = person_id
        self._circle_id = circle_id
        self._bridge = bridge
        self._system = [{"text": _PROMPT_PATH.read_text(encoding="utf-8")}]

        # Per-run state for the duplicate-question guard (filled lazily).
        self._session_id: str | None = None
        self._companion_texts: list[str] | None = None   # normalized
        self._asked_texts: set[str] | None = None        # normalized
        self._waiting_texts: set[str] | None = None      # normalized
        # Per-run state for the answer check (filled from the transcript).
        self._speaker_segments: list[tuple[int, int, str]] = []   # (start_ms, end_ms, text)
        self._asked_by_id: dict[str, str] = {}                     # question_id -> text
        self._check_ms = 0

    async def _tool_config(self) -> dict[str, Any]:
        full = await self._bridge.bedrock_tool_config()
        tools = [t for t in full["tools"] if t["toolSpec"]["name"] in _ARCHIVIST_TOOLS]
        return {"tools": tools}

    async def run(self, session_id: str) -> ArchiveResult:
        total_start = time.monotonic()
        result = ArchiveResult(session_id=session_id)
        self._session_id = session_id
        self._companion_texts = self._asked_texts = self._waiting_texts = None
        self._speaker_segments, self._asked_by_id, self._check_ms = [], {}, 0

        tool_config = await self._tool_config()
        allowed = {t["toolSpec"]["name"] for t in tool_config["tools"]}

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [{
                    "text": (
                        f"Archive the finished session with session_id {session_id}. "
                        f"Start by calling get_session_transcript with that session_id."
                    )
                }],
            }
        ]

        llm_ms_total = 0
        tools_ms_total = 0

        for _round in range(_MAX_TOOL_ROUNDS):
            llm_t0 = time.monotonic()
            response = await anyio.to_thread.run_sync(
                lambda: self._llm.converse(self._system, messages, tool_config)
            )
            llm_ms_total += int((time.monotonic() - llm_t0) * 1000)

            assistant_msg = response["output"]["message"]
            messages.append(assistant_msg)

            for block in assistant_msg.get("content", []):
                if "text" in block:
                    result.final_text = strip_thinking(block["text"])

            if response.get("stopReason", "") != "tool_use":
                break

            tool_results_content = []
            for block in assistant_msg.get("content", []):
                if "toolUse" not in block:
                    continue
                tool_use = block["toolUse"]
                tool_name = tool_use["name"]
                tool_input = tool_use.get("input", {})

                t0 = time.monotonic()
                is_error = False
                try:
                    tool_result = await self._call(tool_name, tool_input, allowed, result)
                    result_content = [{"json": tool_result}]
                except Exception as exc:
                    tool_result = {"error": str(exc)}
                    result_content = [{"text": str(exc)}]
                    is_error = True
                tool_ms = int((time.monotonic() - t0) * 1000)
                tools_ms_total += tool_ms

                result.trace.append(
                    ToolTrace(
                        tool=tool_name,
                        input=tool_input,
                        result=tool_result,
                        result_preview=json.dumps(tool_result)[:300] if tool_result is not None else "",
                        ms=tool_ms,
                        is_error=is_error,
                    )
                )
                tool_results_content.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_use["toolUseId"],
                            "content": result_content,
                        }
                    }
                )

            messages.append({"role": "user", "content": tool_results_content})

        await self._reopen_unanswered(result)

        result.latency = {
            "llm_ms": llm_ms_total + self._check_ms,
            "tools_ms": tools_ms_total,
            "total_ms": int((time.monotonic() - total_start) * 1000),
        }
        return result

    async def _call(
        self,
        name: str,
        arguments: dict[str, Any],
        allowed: set[str],
        result: ArchiveResult,
    ) -> Any:
        """Dispatch one tool call and record its outcome in result."""
        if name not in allowed:
            raise RuntimeError(f"Tool '{name}' is not available to the archivist.")
        if name == "add_question":
            if len(result.questions_added) >= _MAX_QUESTIONS:
                raise RuntimeError(
                    f"Question limit reached: at most {_MAX_QUESTIONS} questions per session."
                )
            reason = await self._duplicate_reason(arguments.get("text", ""))
            if reason:
                raise RuntimeError(f"Duplicate question rejected: {reason}.")
        if name == "record_answer":
            reason = await self._passage_rejection(
                arguments, _ANSWER_CHECK_PROMPT,
                "the speaker's words in that range do not answer the question",
            )
            if reason:
                raise RuntimeError(
                    f"Answer not recorded: {reason}. Leave this question unanswered."
                )
        if name == "mark_question_declined":
            if arguments.get("session_id") != self._session_id:
                reason = "a decline must be in the session being archived"
            else:
                reason = await self._passage_rejection(
                    arguments, _DECLINE_CHECK_PROMPT,
                    "the speaker does not clearly decline the question in that range",
                )
            if reason:
                raise RuntimeError(
                    f"Decline not recorded: {reason}. Treat the question as not declined."
                )

        out = await self._bridge.call_tool(name, arguments)

        if name == "get_session_transcript" and isinstance(out, dict):
            self._remember_transcript(out)

        if name == "save_story" and isinstance(out, dict) and out.get("story_id"):
            result.story_ids.append(out["story_id"])
        elif name == "record_answer":
            result.answers_recorded.append(arguments.get("question_id", ""))
        elif name == "mark_question_declined":
            result.questions_declined.append(arguments.get("question_id", ""))
        elif name == "add_question" and isinstance(out, dict):
            result.questions_added.append(
                {"question_id": out.get("question_id", ""), "status": out.get("status", "")}
            )
            if self._waiting_texts is not None:
                self._waiting_texts.add(normalize_question(arguments.get("text", "")))
        return out

    # ------------------------------------------------------------------
    # Duplicate-question guard
    # ------------------------------------------------------------------

    def _remember_transcript(self, transcript: dict[str, Any]) -> None:
        if transcript.get("session_id") != self._session_id:
            return
        self._companion_texts = [
            normalize_question(s.get("transcript", ""))
            for s in transcript.get("segments", [])
            if s.get("speaker_id") is None
        ]
        self._asked_texts = {
            normalize_question(q.get("text", "")) for q in transcript.get("asked_questions", [])
        }
        self._speaker_segments = [
            (s.get("start_ms", 0), s.get("end_ms", 0), s.get("transcript", ""))
            for s in transcript.get("segments", [])
            if s.get("speaker_id") is not None
        ]
        self._asked_by_id = {
            q.get("question_id", ""): q.get("text", "") for q in transcript.get("asked_questions", [])
        }

    async def _ensure_transcript(self) -> None:
        if self._companion_texts is None:
            self._remember_transcript(
                await self._bridge.call_tool(
                    "get_session_transcript", {"session_id": self._session_id}
                )
            )

    # ------------------------------------------------------------------
    # Answer check
    # ------------------------------------------------------------------

    async def _passage_rejection(
        self, arguments: dict[str, Any], prompt: str, failure: str
    ) -> str | None:
        """Ask the checker about the question and the speaker's words in the
        range; return why the call must not go through, or None if it may."""
        await self._ensure_transcript()
        question = self._asked_by_id.get(arguments.get("question_id", ""))
        if not question:
            return "that question was not asked in this circle"
        start, end = arguments.get("start_ms", 0), arguments.get("end_ms", 0)
        passage = " ".join(
            text for s_start, s_end, text in self._speaker_segments
            if s_start < end and s_end > start
        ).strip()
        if not passage:
            return "nobody speaks in that range"

        t0 = time.monotonic()
        response = await anyio.to_thread.run_sync(
            lambda: self._checker_llm.converse(
                [{"text": prompt}],
                [{"role": "user", "content": [{"text": f"QUESTION: {question}\n\nPASSAGE: {passage}"}]}],
                None,
            )
        )
        self._check_ms += int((time.monotonic() - t0) * 1000)
        verdict = " ".join(
            strip_thinking(b["text"]) for b in response["output"]["message"]["content"] if "text" in b
        )
        return None if checker_said_yes(verdict) else failure

    # ------------------------------------------------------------------
    # End of run: unanswered questions go back to "waiting"
    # ------------------------------------------------------------------

    async def _reopen_unanswered(self, result: ArchiveResult) -> None:
        """Return every asked question that was neither answered nor declined
        in this run to "waiting". Failures are logged, never raised."""
        try:
            await self._ensure_transcript()
        except Exception:
            log.exception("Could not read the transcript to reopen questions (session %s)",
                          self._session_id)
            return
        done = set(result.answers_recorded) | set(result.questions_declined)
        for question_id in self._asked_by_id:
            if not question_id or question_id in done:
                continue
            try:
                await self._bridge.call_tool("reopen_question", {"question_id": question_id})
                result.questions_reopened.append(question_id)
            except Exception:
                log.exception("Could not reopen question %s (session %s)",
                              question_id, self._session_id)

    async def _duplicate_reason(self, text: str) -> str | None:
        """Return why the question is a duplicate, or None if it is new."""
        norm = normalize_question(text)
        if not norm:
            return None  # the service rejects empty text with its own message

        await self._ensure_transcript()
        if self._waiting_texts is None:
            pending = await self._bridge.call_tool("get_pending_questions", {"limit": 1000})
            items = pending.get("result", []) if isinstance(pending, dict) else (pending or [])
            self._waiting_texts = {normalize_question(q.get("text", "")) for q in items}

        if any(norm in c for c in self._companion_texts or []):
            return "the companion already asked this in the session"
        if norm in (self._asked_texts or set()) | self._waiting_texts:
            return "the same question is already waiting or asked"
        return None
