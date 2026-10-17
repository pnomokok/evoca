"""
Archivist agent for Evoca.

ArchivistAgent.run(session_id) processes one finished session in the
background, following the archivist steps in docs/PROJECT.md:

1. get_session_transcript   — read the non-private segments
2. save_story               — one story per distinct memory
3. record_answer            — for asked questions answered in this session
4. add_refused_topic        — a topic the speaker refused on her own
5. search_archive + link_stories — links to related existing stories
6. find_gaps + add_question — at most two follow_up questions and one gap question

Architecture
------------
- Same Bedrock Converse tool loop as ChatAgent, but one-shot: there is no live
  speaker and nothing is stored as Segments.
- The tool config is restricted to the archivist's tools, so the model cannot
  call chat-agent tools such as mark_question_asked.
- The question limits are enforced here as well as in the prompt: at most
  two follow_up questions and one gap question per run; extra add_question
  calls get an error result and never reach the MCP server. A gap question
  must name a period that find_gaps returned for the center in this run (the
  code calls find_gaps itself if the model has not).
- search_archive runs as the bridge's identity, the session's teller (the
  center, or the recorder of a panel recording), so the model only sees
  stories that person can see when it looks for links. This code narrows it
  further to stories at least as widely shared as a new story (access
  "circle", and published or told by the teller) and drops their audio
  sources, teller, access and status: a new circle story must not repeat a
  private or pending story's words, nor point at its audio.
- In every mode, the session is the one being archived, never the model's
  choice: the session_id of get_session_transcript and mark_question_declined,
  and of every save_story source, is replaced with it before the call (a
  different value is logged, ids only). The server checks sources again
  against the session header. record_answer must name a story saved in this run.
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
- Refused topics too: add_refused_topic goes through only when the checker
  confirms, from the center's own words in the range, that she refuses to talk
  about that topic. A range that is not clear of private parts (it reaches
  outside the non-private segments this run read) or holds no words of the
  center (another person in a gathering does not count) is
  rejected before the checker is asked; a checker error counts as no. The
  server checks the range again. The session is the one being archived: the
  tool takes it from the X-Evoca-Session-Id header, so the bridge must be
  opened with it.
- At the end of the run, every question that is still "asked" (not answered,
  not declined) is returned to "waiting" via reopen_question, so it is asked
  again in a later session. These calls are made by this code, not the model.
- Split guard: the model sometimes saves one memory as two stories. When two
  stories saved in the same run have overlapping or adjacent sources (a gap
  under SPLIT_GAP_MS, not counting the companion's segments in between, so a
  companion question does not separate two parts of one memory) and share a
  place or a subject period, the pair is logged
  as a possible split (story ids only) and kept in possible_splits. Nothing is
  merged: telling a split from two short memories needs a person.

Panel recordings (A4)
---------------------
With panel_recording=True the session is one family member's own recording
from the panel. Questions belong only to the center's own sessions, so:
- only get_session_transcript, save_story, search_archive and link_stories
  are offered (and accepted; no add_refused_topic, find_gaps or questions); the circle's asked questions are dropped from the transcript the
  model sees, and nothing is reopened at the end of the run;
- teller_id is always the recorder (person_id), whatever the model passes,
  and only this session can be read or cited (the recorder's identity must
  not reach other sessions of the circle);
- subjects may be any circle member (the members list is in the first message,
  e.g. the center in "Grandma taught me...");
- every saved story gets the requested access right away, by this code
  (set_story_access as the teller); the caller enforces it again afterwards.
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
_PANEL_PROMPT_PATH = Path(__file__).parent / "prompts" / "archivist_panel_recording.md"
_MAX_TOOL_ROUNDS = 15
_MAX_QUESTIONS = 2        # follow_up questions per run
_MAX_GAP_QUESTIONS = 1    # gap questions per run
SPLIT_GAP_MS = 5_000      # sources closer than this may be one memory saved twice

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
    "add_refused_topic",
    "search_archive",
    "link_stories",
    "find_gaps",
}

# A panel recording only becomes stories (and their links); no answers,
# declines or questions.
_PANEL_RECORDING_TOOLS = {"get_session_transcript", "save_story", "search_archive", "link_stories"}

# Tools whose session_id argument is always the session being archived.
_SESSION_TOOLS = {"get_session_transcript", "mark_question_declined"}


_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)


def _gap_ms(a: dict[str, Any], b: dict[str, Any], companion: list[tuple[int, int]]) -> int:
    """Silence between two source ranges of one session, minus the companion's
    segments inside it (0 when they overlap or touch)."""
    first, second = (a, b) if a.get("start_ms", 0) <= b.get("start_ms", 0) else (b, a)
    gap_start, gap_end = first.get("end_ms", 0), second.get("start_ms", 0)
    if gap_end <= gap_start:
        return 0
    spoken = sum(max(0, min(e, gap_end) - max(s, gap_start)) for s, e in companion)
    return gap_end - gap_start - spoken


def possible_split(
    a: dict[str, Any],
    b: dict[str, Any],
    companion: dict[str, list[tuple[int, int]]] | None = None,
) -> bool:
    """True if two save_story argument sets look like one memory saved twice:
    sources in the same session that overlap or are less than SPLIT_GAP_MS
    apart (companion segments in between do not count; companion maps a
    session_id to its companion segment ranges), and the same place or a
    shared subject period."""
    companion = companion or {}
    close = any(
        sa.get("session_id") == sb.get("session_id")
        and _gap_ms(sa, sb, companion.get(sa.get("session_id"), [])) < SPLIT_GAP_MS
        for sa in a.get("sources") or [] for sb in b.get("sources") or []
    )
    if not close:
        return False
    place_a, place_b = (" ".join((x.get("place") or "").lower().split()) for x in (a, b))
    periods_a = {s.get("period") for s in a.get("subjects") or []}
    periods_b = {s.get("period") for s in b.get("subjects") or []}
    return bool(place_a and place_a == place_b) or bool((periods_a & periods_b) - {None})


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


_REFUSAL_CHECK_PROMPT = """You check one thing: in a passage from a recorded conversation, does the speaker refuse to talk about a topic?
Reply with exactly one word: yes or no.
yes: the speaker clearly says they do not want to talk about that topic, for example "I don't want to talk about her today".
no: the speaker talks about it, is only sad or quiet, changes the subject without refusing, refuses a different topic, or you are unsure."""


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
    links_added: list[str] = field(default_factory=list)         # link ids (source "ai")
    questions_declined: list[str] = field(default_factory=list)  # question ids, confirmed declines
    questions_reopened: list[str] = field(default_factory=list)  # question ids, back to "waiting"
    topics_refused: list[str] = field(default_factory=list)      # sensitive topic ids (source "speaker")
    possible_splits: list[tuple[str, str]] = field(default_factory=list)  # story id pairs, see possible_split
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
    panel_recording : True for a panel_recording session; person_id is then
                  the recorder (see "Panel recordings" above).
    members     : circle members offered as subjects of a panel recording:
                  [{person_id, name, relation_to_center, birth_year}].
    story_access : access for the stories of a panel recording ("circle" or
                  "private").
    """

    def __init__(
        self,
        llm: LLM,
        person_id: str,
        circle_id: str,
        bridge: Any,
        checker_llm: LLM | None = None,
        panel_recording: bool = False,
        members: list[dict[str, Any]] | None = None,
        story_access: str = "circle",
    ) -> None:
        self._llm = llm
        self._checker_llm = checker_llm or llm
        self._person_id = person_id
        self._circle_id = circle_id
        self._bridge = bridge
        self._panel_recording = panel_recording
        self._members = members or []
        self._story_access = story_access
        prompt = _PROMPT_PATH.read_text(encoding="utf-8")
        if panel_recording:
            prompt += "\n\n" + _PANEL_PROMPT_PATH.read_text(encoding="utf-8")
        self._system = [{"text": prompt}]

        # Per-run state for the duplicate-question guard (filled lazily).
        self._session_id: str | None = None
        self._companion_texts: list[str] | None = None   # normalized
        self._asked_texts: set[str] | None = None        # normalized
        self._waiting_texts: set[str] | None = None      # normalized
        # Per-run state for the answer check (filled from the transcript).
        self._speaker_segments: list[tuple[int, int, str]] = []   # (start_ms, end_ms, text)
        self._read_ranges: list[tuple[int, int]] = []              # every non-private segment
        self._center_segments: list[tuple[int, int, str]] = []    # the center's own words
        self._companion_ranges: list[tuple[int, int]] = []         # the companion's segments
        self._asked_by_id: dict[str, str] = {}                     # question_id -> text
        self._check_ms = 0
        # Per-run state for the question limits and the gap check.
        self._added_by_source: dict[str, int] = {}
        self._gaps: list[str] | None = None
        # Per-run state for the split guard: (story_id, save_story arguments).
        self._saved: list[tuple[str, dict[str, Any]]] = []

    async def _tool_config(self) -> dict[str, Any]:
        full = await self._bridge.bedrock_tool_config()
        names = _PANEL_RECORDING_TOOLS if self._panel_recording else _ARCHIVIST_TOOLS
        tools = [t for t in full["tools"] if t["toolSpec"]["name"] in names]
        return {"tools": tools}

    async def run(self, session_id: str) -> ArchiveResult:
        total_start = time.monotonic()
        result = ArchiveResult(session_id=session_id)
        self._session_id = session_id
        self._companion_texts = self._asked_texts = self._waiting_texts = None
        self._speaker_segments, self._asked_by_id, self._check_ms = [], {}, 0
        self._read_ranges, self._center_segments, self._companion_ranges = [], [], []
        self._added_by_source, self._gaps = {}, None
        self._saved = []

        tool_config = await self._tool_config()
        allowed = {t["toolSpec"]["name"] for t in tool_config["tools"]}

        first = (
            f"Archive the finished session with session_id {session_id}. "
            f"Start by calling get_session_transcript with that session_id."
        )
        if self._panel_recording:
            first += (
                f"\n\nThis is a panel recording by person_id {self._person_id}."
                f"\nCircle members you may use as subjects:\n{self._members_text()}"
            )
        else:
            first += f"\nThe center person, for find_gaps, is person_id {self._person_id}."
        messages: list[dict[str, Any]] = [{"role": "user", "content": [{"text": first}]}]

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

        if not self._panel_recording:
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
        self._pin_session(name, arguments)
        if self._panel_recording and name == "save_story":
            arguments["teller_id"] = self._person_id   # always the recorder
        if name == "record_answer" and arguments.get("story_id") not in result.story_ids:
            raise RuntimeError(
                "Answer not recorded: the answer must be in a story you saved from this session."
            )
        if name == "add_question":
            source = arguments.get("source")
            limit = _MAX_GAP_QUESTIONS if source == "gap" else _MAX_QUESTIONS
            if self._added_by_source.get(source, 0) >= limit:
                raise RuntimeError(
                    f"Question limit reached: at most {limit} {source} question(s) per session."
                )
            if source == "gap":
                gaps = await self._center_gaps()
                if arguments.get("period") not in gaps:
                    raise RuntimeError(
                        f"A gap question needs a period from find_gaps: {', '.join(gaps) or 'none'}."
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
            reason = await self._passage_rejection(
                arguments, _DECLINE_CHECK_PROMPT,
                "the speaker does not clearly decline the question in that range",
            )
            if reason:
                raise RuntimeError(
                    f"Decline not recorded: {reason}. Treat the question as not declined."
                )
        if name == "add_refused_topic":
            reason = await self._refusal_rejection(arguments)
            if reason:
                log.info("Refused topic rejected (session %s): %s", self._session_id, reason)
                raise RuntimeError(f"Topic not saved: {reason}. Do not try again.")

        out = await self._bridge.call_tool(name, arguments)

        if name == "search_archive":
            out = self._shareable_results(out)

        if name == "find_gaps" and isinstance(out, (dict, list)):
            self._gaps = out.get("result", []) if isinstance(out, dict) else list(out)

        if name == "get_session_transcript" and isinstance(out, dict):
            if self._panel_recording:
                out = {**out, "asked_questions": []}
            self._remember_transcript(out)

        if name == "save_story" and isinstance(out, dict) and out.get("story_id"):
            result.story_ids.append(out["story_id"])
            if self._panel_recording and self._story_access != "circle":
                await self._apply_story_access(out["story_id"])
            self._check_split(out["story_id"], arguments, result)
        elif name == "record_answer":
            result.answers_recorded.append(arguments.get("question_id", ""))
        elif name == "mark_question_declined":
            result.questions_declined.append(arguments.get("question_id", ""))
        elif name == "add_refused_topic" and isinstance(out, dict):
            if out.get("added"):
                result.topics_refused.append(out.get("topic_id", ""))
            log.info("Refused topic %s (session %s): topic %s",
                     "added" if out.get("added") else "already known",
                     self._session_id, out.get("topic_id", ""))
        elif name == "link_stories" and isinstance(out, dict) and out.get("added"):
            result.links_added.append(out.get("link_id", ""))
        elif name == "add_question" and isinstance(out, dict):
            source = arguments.get("source")
            self._added_by_source[source] = self._added_by_source.get(source, 0) + 1
            result.questions_added.append(
                {"question_id": out.get("question_id", ""), "status": out.get("status", "")}
            )
            if self._waiting_texts is not None:
                self._waiting_texts.add(normalize_question(arguments.get("text", "")))
        return out

    # ------------------------------------------------------------------
    # Panel recordings
    # ------------------------------------------------------------------

    def _check_split(self, story_id: str, arguments: dict[str, Any], result: ArchiveResult) -> None:
        """Log a possible split with an earlier story of this run (ids only, no text).

        A diagnostic only: it runs after the access step and never raises.
        """
        try:
            companion = {self._session_id: self._companion_ranges}
            for other_id, other_args in self._saved:
                if possible_split(other_args, arguments, companion):
                    result.possible_splits.append((other_id, story_id))
                    log.warning("Possible story split in session %s: %s and %s",
                                self._session_id, other_id, story_id)
        except Exception:
            log.exception("Split check failed (session %s, story %s)", self._session_id, story_id)
        self._saved.append((story_id, arguments))

    def _pin_session(self, name: str, arguments: dict[str, Any]) -> None:
        """Use the session being archived wherever a tool takes a session id;
        the model's value is ignored (a mistyped id would lose the whole run)."""
        targets = [arguments] if "session_id" in arguments or name in _SESSION_TOOLS else []
        if name == "save_story":
            targets += [src for src in arguments.get("sources") or [] if isinstance(src, dict)]
        for target in targets:
            if target.get("session_id") != self._session_id:
                log.info("Archivist %s: session id %s replaced with %s",
                         name, target.get("session_id"), self._session_id)
                target["session_id"] = self._session_id

    def _members_text(self) -> str:
        lines = []
        for m in self._members:
            relation = m.get("relation_to_center") or "the center of the circle"
            born = f", born {m['birth_year']}" if m.get("birth_year") else ""
            lines.append(f"- {m.get('name')} ({relation}{born}): person_id {m.get('person_id')}")
        return "\n".join(lines)

    async def _apply_story_access(self, story_id: str) -> None:
        """Give a just-saved story the requested access. A failure is logged,
        not shown to the model (it would save the story again); the caller
        enforces the access once more after the run."""
        try:
            await self._bridge.call_tool(
                "set_story_access", {"story_id": story_id, "type": self._story_access}
            )
        except Exception as exc:
            log.error("Could not set story access (session %s): %s",
                      self._session_id, type(exc).__name__)

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
        self._read_ranges = sorted(
            (s.get("start_ms", 0), s.get("end_ms", 0)) for s in transcript.get("segments", [])
        )
        self._companion_ranges = [
            (s.get("start_ms", 0), s.get("end_ms", 0))
            for s in transcript.get("segments", [])
            if s.get("speaker_id") is None
        ]
        # person_id is the center outside panel recordings, the only mode with add_refused_topic.
        self._center_segments = [
            (s.get("start_ms", 0), s.get("end_ms", 0), s.get("transcript", ""))
            for s in transcript.get("segments", [])
            if s.get("speaker_id") == self._person_id
        ]

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
    # Refused-topic check
    # ------------------------------------------------------------------

    def _covered_by_read_segments(self, start: int, end: int) -> bool:
        """True if every ms of [start, end) lies in a non-private segment this
        run read. Private segments are left out of the transcript, so a range
        reaching into a gap may overlap one and is never sent to the checker."""
        pos = start
        for s_start, s_end in self._read_ranges:
            if s_start > pos:
                break
            pos = max(pos, s_end)
            if pos >= end:
                return True
        return False

    async def _refusal_rejection(self, arguments: dict[str, Any]) -> str | None:
        """Return why add_refused_topic must not go through, or None if the
        checker confirmed the refusal. Range rules come before the checker."""
        raw = arguments.get("text")
        topic = " ".join(raw.split()) if isinstance(raw, str) else ""
        start, end = arguments.get("start_ms"), arguments.get("end_ms")
        if not topic:
            return "the topic is empty"
        if not isinstance(start, int) or not isinstance(end, int) or start >= end:
            return "the range is not valid"
        await self._ensure_transcript()
        if not self._covered_by_read_segments(start, end):
            return "the range is not inside the segments of the session being archived"
        passage = " ".join(
            text for s_start, s_end, text in self._center_segments
            if s_start < end and s_end > start
        ).strip()
        if not passage:
            return "the center person says nothing in that range"

        t0 = time.monotonic()
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self._checker_llm.converse(
                    [{"text": _REFUSAL_CHECK_PROMPT}],
                    [{"role": "user", "content": [{"text": f"TOPIC: {topic}\n\nPASSAGE: {passage}"}]}],
                    None,
                )
            )
            verdict = " ".join(
                strip_thinking(b["text"]) for b in response["output"]["message"]["content"]
                if "text" in b
            )
        except Exception as exc:
            log.warning("Refusal check failed (session %s): %s", self._session_id, type(exc).__name__)
            verdict = ""
        finally:
            self._check_ms += int((time.monotonic() - t0) * 1000)
        if checker_said_yes(verdict):
            return None
        return "the speaker does not clearly refuse that topic in that range"

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

    def _shareable_results(self, out: Any) -> dict[str, Any]:
        """Search results the model may use for links and retellings: only
        circle stories that are published or told by this run's teller, with
        no audio sources, teller, access or status."""
        items = out.get("result", []) if isinstance(out, dict) else list(out or [])
        keep = []
        for item in items:
            if item.get("access") != "circle":
                continue
            if item.get("status") != "published" and item.get("teller_id") != self._person_id:
                continue
            keep.append({k: v for k, v in item.items()
                         if k not in ("sources", "teller_id", "access", "status")})
        return {"result": keep}

    async def _center_gaps(self) -> list[str]:
        """The center's empty periods, from this run's find_gaps call or a new one."""
        if self._gaps is None:
            out = await self._bridge.call_tool("find_gaps", {"person_id": self._person_id})
            self._gaps = out.get("result", []) if isinstance(out, dict) else list(out or [])
        return self._gaps

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
