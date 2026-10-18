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
- A spoken promise is always true (one rule, at the very end of the reply
  pipeline, after the guard and any regeneration): an explicit keep_private
  always marks. If the FINAL reply promises privacy and no keep_private mark
  covers this turn, a temperature-0 checker sees the speaker's own words of
  this turn and the previous one. "yes" or "unsure" (also a checker error or
  an unparsable answer): mark previous_turn, which hides both. A clear "no":
  the promise is removed, and the replacement does not sound like agreement.
  A declined topic is not a secret.
- Privacy guard: the salient terms of hidden user turns (names, kinship
  words, content nouns, minus stopwords and words the speaker also used in
  turns that are not hidden) are kept in this object only, never in an LLM
  request. From the turn keep_private is requested on, a reply that contains
  one is regenerated once with a generic instruction; if it still does, a
  fixed safe reply that changes the subject is used. Blocks are logged with
  the session id, never with the terms.
- Spoken replies lose parenthetical asides ("(When you are ready, ...)").
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

# MCP tools the model may call.
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

# The opening's first two calls (steps 1 and 2 of the prompt), made by the code
# before the first LLM call when turn(prefetch_context=True). Same arguments as
# the model's own calls; they stay in CHAT_TOOLS for later turns.
PREFETCH_TOOLS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("get_session_context", {}),
    ("get_pending_questions", {}),
)

# How the prefetched opening shows a waiting question without an asker (follow_up, gap):
# a bare null asker next to a reaction was read as that person's question.
OWN_QUESTION = "you: this is your own question, no family member asked it"


def _with_own_questions_marked(tool_name: str, result: Any) -> Any:
    """get_pending_questions as the model sees it in the prefetched opening: every
    question without an asker says plainly that it is the companion's own."""
    if tool_name != "get_pending_questions":
        return result
    wrapped = isinstance(result, dict)
    items = result.get("result") if wrapped else result
    if not isinstance(items, list):
        return result
    shown = [{**q, "asked_by": OWN_QUESTION} if isinstance(q, dict) and not q.get("asker_id") else q
             for q in items]
    return {**result, "result": shown} if wrapped else shown

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

_PRIVACY_CHECK_PROMPT = """You check one thing in what an older person said to a voice companion (one or two turns): did they ask that something they said, or are about to say, is not shared with other people?
Reply with exactly one word: yes, no or unsure.
yes: they asked for it to stay private or secret (for example "don't tell anyone", "keep this between us", "nobody should hear that part", "I'll tell you something, but it's a secret").
no: they did not ask for that. Refusing to talk about a topic ("I don't want to talk about him", "that chapter is closed") is not a request to keep something private.
unsure: you cannot tell."""

_NO_PROMISE_INSTRUCTION = (
    "System note, not from the person: nothing was made private, so do not promise privacy or "
    "secrecy and do not agree to keep anything secret (no \"I understand\", no \"of course\"). "
    "Write a new reply that gently moves on to a different topic."
)
NEUTRAL_REPLY = "Let us talk about something else. What is a memory you would like to share today?"

# Words that would sound like agreeing to keep something secret.
_AGREEMENT = re.compile(
    r"\b(?:i understand|of course|i promise|certainly|absolutely|no problem)\b", re.IGNORECASE
)

DEFAULT_CHAT_MODEL = "us.amazon.nova-2-lite-v1:0"
DEFAULT_CHAT_TEMPERATURE = 0.3


def privacy_check_llm() -> BedrockLLM:
    """The privacy gate's checker: the chat model at temperature 0, a one-word answer."""
    return BedrockLLM(
        model_id=os.environ.get("EVOCA_CHAT_MODEL", DEFAULT_CHAT_MODEL),
        max_tokens=10,
        temperature=0.0,
    )


def checker_said_no(verdict: str) -> bool:
    """True only for a clear "no" (first word, ignoring Markdown). Anything
    else, including "unsure" and an empty reply, does not stop a mark."""
    match = re.search(r"[a-z]+", verdict.lower())
    return match is not None and match.group(0) == "no"


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


_PARENTHETICAL = re.compile(r"\s*\([^()]*\)")


def strip_parentheticals(text: str) -> str:
    """Remove "(...)" asides; they are not meant to be spoken."""
    stripped = _PARENTHETICAL.sub("", text)
    stripped = re.sub(r"[ \t]+", " ", stripped)
    stripped = re.sub(r"\s*\n\s*", "\n", stripped).strip()
    # A reply that was only an aside keeps its words, without the brackets.
    return stripped or text.replace("(", "").replace(")", "").strip()


def first_names_only(text: str, full_names: set[str]) -> str:
    """Say every known person by first name: "Elif Yilmaz" becomes "Elif"."""
    for name in sorted(full_names, key=len, reverse=True):
        parts = name.split()
        if len(parts) > 1:
            text = re.sub(rf"\b{re.escape(name)}\b", parts[0], text)
    return text


def clean_reply(text: str, ending: bool) -> str:
    """Apply the reply guards. A goodbye (ending=True) keeps no question at all."""
    text = keep_last_question(strip_parentheticals(strip_quotes(text).strip()))
    if ending:
        text = remove_questions(text) or GOODBYE_FALLBACK
    return text


# ---------------------------------------------------------------------------
# Privacy guard: salient terms of hidden turns (kept in memory, never sent)
# ---------------------------------------------------------------------------

_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)

# Function words, everyday verbs and the words of a privacy request itself
# ("please don't let anyone hear that part"). Kinship words are NOT here:
# "brother", "sister", ... are exactly what must not come back.
_GUARD_STOPWORDS = frozenset("""
a about above after again against all also always am an and any anyone anybody anything are around as
at away back be because been before being below between both but by can cannot could did do does doing
done down during each either else enough even ever every everyone everything few for from further get
gets getting go goes going gone got had has have having he her here hers herself him himself his how i
if in into is it its itself just keep kept know knew known last later least less let lets like little
long lot lots made make many may me might mine more most much must my myself never no nobody none nor
not nothing now of off often on once one only or other our ours ourselves out over own part please
private quite rather really said same say says secret see seen shall she should since so some someone
something still such tell telling than that the their theirs them themselves then there these they
thing things think this those though through to told too under until up upon us very want wanted was
we well were what when where whether which while who whom whose why will with without would yes yet
you your yours yourself yourselves hear hears heard heard listen anyone's day days year years time
times way ago old young many today yesterday tomorrow really maybe okay oh ah well
dont don't won't can't isn't wasn't didn't i'm i've i'll i'd it's that's there's let's
family between alone only also just
""".split())


def _norm(word: str) -> str:
    word = word.lower()
    if word.endswith("'s"):
        word = word[:-2]
    if len(word) > 4 and word.endswith("s"):
        word = word[:-1]
    return word


def _words(text: str) -> set[str]:
    return {_norm(w) for w in _WORD.findall(text)}


_KINSHIP = frozenset("""
brother sister mother father mom mum mama dad papa husband wife son daughter uncle aunt auntie
cousin grandmother grandfather grandma grandpa granny niece nephew granddaughter grandson
child children parent sibling stepmother stepfather stepson stepdaughter fiance fiancee
boyfriend girlfriend in-law
""".split())
# Capitalised words that start sentences without being names.
_NOT_NAMES = _GUARD_STOPWORDS | frozenset("""
now oh ah well yes no please sure thank thanks sorry let let's dear honey anyway actually
""".split())
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str) -> list[str]:
    return [p.strip() for p in _SENTENCE_END.split(text) if p.strip()]


def _kinship(word: str) -> str | None:
    if word in _KINSHIP:
        return word
    if word.endswith("s") and word[:-1] in _KINSHIP:
        return word[:-1]
    return None


def _known_names(text: str) -> set[str]:
    """Capitalised words that appear mid-sentence somewhere in the text: names.
    A capitalised first word ("Speaking", "Tending") is only a name if it is
    also capitalised elsewhere ("My brother Selim ... Selim lost it")."""
    names = set()
    for sentence in _sentences(text):
        for raw_word in _WORD.findall(sentence)[1:]:
            word = raw_word.lower().removesuffix("'s")
            if raw_word[0].isupper() and raw_word != "I" and len(word) >= 3 and word not in _NOT_NAMES:
                names.add(word)
    return names


def _person_words(sentence: str, known_names: set[str] | None = None) -> set[str]:
    """Names and kinship words in a sentence. Without known_names, any
    capitalised word that is not a common starter counts as a name."""
    found = set()
    for i, raw_word in enumerate(_WORD.findall(sentence)):
        word = raw_word.lower().removesuffix("'s")
        kin = _kinship(word)
        if kin:
            found.add(kin)
        elif raw_word[0].isupper() and raw_word != "I" and len(word) >= 3 and word not in _NOT_NAMES:
            if i > 0 or known_names is None or word in known_names:
                found.add(word)
    return found


def _names_a_person(sentence: str, known_names: set[str] | None = None) -> bool:
    """A kinship word, or a name."""
    return bool(_person_words(sentence, known_names))


_TOPIC_CHANGE = re.compile(
    r"^\W*(?:now|anyway|but enough|let me tell you|speaking of)\b", re.IGNORECASE
)


def _continues_subject(sentence: str, previous: str, known_names: set[str] | None = None) -> bool:
    """The sentence after a name/kinship sentence still belongs to it, unless it
    starts with a topic-change marker ("Now", "Anyway", "But enough",
    "Let me tell you", "Speaking of") or names a different person."""
    if _TOPIC_CHANGE.search(sentence):
        return False
    return not (_person_words(sentence, known_names) - _person_words(previous, known_names))


def _secret_sentences(text: str) -> list[str]:
    """Sentences that name a person or relative, plus the sentence right after
    each unless it changes topic ("Now, my wedding...") or names a different
    person. The whole turn if none qualifies."""
    sentences = _sentences(text)
    known = _known_names(text)
    keep: set[int] = set()
    for i, sentence in enumerate(sentences):
        if _names_a_person(sentence, known):
            keep.add(i)
            if i + 1 < len(sentences) and _continues_subject(sentences[i + 1], sentence, known):
                keep.add(i + 1)
    if not keep:
        return sentences
    return [sentences[i] for i in sorted(keep)]


def salient_terms(hidden_texts: list[str], other_texts: list[str]) -> set[str]:
    """Names, kinship words and content words of the hidden part, minus
    stopwords and anything the speaker also said in turns that are not hidden.

    Only the sentences about a person (and the sentence after each) count, so
    the rest of a long turn (her wedding, her garden) does not block replies.
    """
    used_elsewhere = set().union(*(_words(t) for t in other_texts)) if other_texts else set()
    terms: set[str] = set()
    for text in hidden_texts:
        for sentence in _secret_sentences(text):
            for word in _words(sentence):
                if len(word) >= 3 and word not in _GUARD_STOPWORDS and word not in used_elsewhere:
                    terms.add(word)
    return terms


def mentions_any(text: str, terms: set[str]) -> bool:
    return bool(terms and _words(text) & terms)


_GUARD_INSTRUCTION = (
    "System note, not from the person: your last reply touched the part the person asked to keep "
    "private. Write a new reply now. Do not mention or ask about the private part; change the subject "
    "to something else they told you, or invite a new memory."
)
_REMOVED_REPLY = "[A reply was removed.]"
GUARD_SAFE_REPLY = (
    "Thank you for sharing that with me. Let us talk about something else. "
    "What is a happy memory from your childhood that you would like to tell me about?"
)
# Used in turn, so the same safe reply is never spoken twice in a row.
GUARD_SAFE_REPLIES = (
    GUARD_SAFE_REPLY,
    "I am glad you told me. Shall we turn to something new? "
    "What is a place you loved to visit when you were young?",
    "Thank you. Let us talk about a different memory. "
    "What was a favourite meal at home when you were a child?",
)


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
    prefetched: bool = False  # called by the code before the opening's first LLM call


@dataclass
class TurnResult:
    reply_text: str
    trace: list[ToolTrace]
    latency: dict[str, int]  # llm_ms, tools_ms, total_ms
    session_should_end: bool = False  # the model called end_conversation
    marked_private: bool = False      # this turn was hidden (its text left the history)
    privacy_guard: str | None = None  # "regenerated" or "safe_reply" if a reply touched a hidden part
    privacy_check: str | None = None  # "confirmed" / "not_confirmed" when a mark was considered


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
    user_text: str | None = None              # original words, kept in memory only


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
        checker_llm: LLM | None = None,
    ) -> None:
        self._llm = llm
        # The privacy gate's checker (privacy_check_llm() in production).
        self._checker_llm = checker_llm or llm
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

        # Original words of hidden user turns, for the privacy guard. Memory only.
        self._hidden_user_texts: list[str] = []
        self._safe_reply_index = -1   # rotates through GUARD_SAFE_REPLIES

        # End of the last placeholder span (see turn()); keeps placeholders apart.
        self._placeholder_end = 0

        # Reactions told in this session: story_id -> first names of reactors.
        self._undelivered: dict[str, set[str]] = {}

        # Full names from the tools; the reply says only their first names.
        self._full_names: set[str] = set()

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
        if record.user_text:
            self._hidden_user_texts.append(record.user_text)
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

    async def _privacy_requested(self, speaker_texts: list[str]) -> tuple[bool, int]:
        """Ask the checker whether the speaker asked for privacy in these words.

        Only the speaker's own words are sent. Returns (confirmed, llm_ms);
        only a clear "no" is not confirmed.
        """
        passage = "\n".join(t for t in speaker_texts if t).strip()
        if not passage:
            return True, 0
        t0 = time.monotonic()
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self._checker_llm.converse(
                    [{"text": _PRIVACY_CHECK_PROMPT}],
                    [{"role": "user", "content": [{"text": f"WHAT THE PERSON SAID:\n{passage}"}]}],
                    None,
                )
            )
            verdict = " ".join(
                strip_thinking(b["text"])
                for b in response["output"]["message"].get("content", []) if "text" in b
            )
        except Exception:
            # Fail closed: an unanswered or unreadable check counts as a request.
            log.warning("Privacy check failed; marking (session %s)", self._ensure_session())
            return True, int((time.monotonic() - t0) * 1000)
        return not checker_said_no(verdict), int((time.monotonic() - t0) * 1000)

    async def _remove_promise(
        self, text_blocks: list[dict[str, Any]], ending: bool, terms: set[str]
    ) -> tuple[str, int]:
        """The final reply promised privacy that nobody asked for: ask once for a
        reply without the promise; accept it only if it neither promises, nor
        sounds like agreement, nor touches a hidden part. Else a neutral reply."""
        fallback = GOODBYE_FALLBACK if ending else NEUTRAL_REPLY
        for block in text_blocks:
            if claims_privacy(block.get("text", "")):
                block["text"] = _REMOVED_REPLY
        messages = list(self._history)
        note = {"text": _NO_PROMISE_INSTRUCTION}
        if messages and messages[-1]["role"] == "user":
            messages[-1] = {"role": "user", "content": list(messages[-1]["content"]) + [note]}
        else:
            messages.append({"role": "user", "content": [note]})
        t0 = time.monotonic()
        try:
            response = await anyio.to_thread.run_sync(
                lambda: self._llm.converse(self._system, messages, self._tool_config)
            )
            text = " ".join(
                strip_thinking(b["text"])
                for b in response["output"]["message"].get("content", []) if "text" in b
            ).strip()
        except Exception:
            log.warning("Promise-free regeneration failed; neutral reply (session %s)",
                        self._ensure_session())
            return fallback, int((time.monotonic() - t0) * 1000)
        llm_ms = int((time.monotonic() - t0) * 1000)
        text = clean_reply(text, ending) if text else ""
        if (text and not claims_privacy(text) and not _AGREEMENT.search(text)
                and not mentions_any(text, terms)):
            return text, llm_ms
        return fallback, llm_ms

    def _guard_terms(self, hiding_now: list[str], current_user_text: str | None) -> set[str]:
        """Salient terms of everything hidden so far plus what this turn will hide."""
        hidden = self._hidden_user_texts + hiding_now
        if not hidden:
            return set()
        others = [t.user_text for t in self._turns
                  if t.user_text and not t.hidden and t.user_text not in hiding_now]
        if current_user_text and current_user_text not in hiding_now:
            others.append(current_user_text)
        return salient_terms(hidden, others)

    async def _regenerate_without(
        self, terms: set[str], text_blocks: list[dict[str, Any]], ending: bool
    ) -> tuple[str, str, int]:
        """Ask once for a reply that leaves the private part alone; else the safe reply.

        The offending text is removed from the history first, and the
        instruction is generic, so no request carries the terms.
        Returns (reply, "regenerated" | "safe_reply", llm_ms).
        """
        for block in text_blocks:
            if mentions_any(block.get("text", ""), terms):
                block["text"] = _REMOVED_REPLY
        messages = list(self._history)
        note = {"text": _GUARD_INSTRUCTION}
        if messages and messages[-1]["role"] == "user":
            messages[-1] = {"role": "user", "content": list(messages[-1]["content"]) + [note]}
        else:
            messages.append({"role": "user", "content": [note]})

        t0 = time.monotonic()
        response = await anyio.to_thread.run_sync(
            lambda: self._llm.converse(self._system, messages, self._tool_config)
        )
        llm_ms = int((time.monotonic() - t0) * 1000)
        text = " ".join(
            strip_thinking(b["text"])
            for b in response["output"]["message"].get("content", []) if "text" in b
        ).strip()
        text = clean_reply(text, ending) if text else ""
        if text and not mentions_any(text, terms):
            log.warning("Reply touched a private part; regenerated it (session %s)", self._orm_session_id)
            return text, "regenerated", llm_ms
        log.warning("Reply touched a private part twice; used the safe reply (session %s)",
                    self._orm_session_id)
        if ending:
            return GOODBYE_FALLBACK, "safe_reply", llm_ms
        self._safe_reply_index = (self._safe_reply_index + 1) % len(GUARD_SAFE_REPLIES)
        return GUARD_SAFE_REPLIES[self._safe_reply_index], "safe_reply", llm_ms

    def _remember_names(self, tool_name: str, result: Any) -> None:
        if tool_name == "get_session_context" and isinstance(result, dict):
            names = [result.get("center_person_name")]
            names += [r.get("person_name") for r in result.get("undelivered_reactions", [])]
        elif tool_name == "get_pending_questions":
            items = result.get("result", []) if isinstance(result, dict) else result
            names = [q.get("asker_name") for q in items or [] if isinstance(q, dict)]
        else:
            return
        self._full_names.update(n for n in names if isinstance(n, str) and n.strip())

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

    async def _prefetch_opening(self, trace: list[ToolTrace]) -> int:
        """Call the opening's first two tools in code, before the first LLM call.

        The results go into the history as the model's own toolUse and the
        toolResult it would have received, so the model sees exactly what it
        saw before, one LLM round sooner. Same bridge, same identity headers,
        same filtering. If either call fails nothing is added and the model
        calls the tools itself, as before. Returns the tools' time in ms.
        """
        calls: list[tuple[str, dict[str, Any], Any, int]] = []
        t_start = time.monotonic()
        try:
            for name, args in PREFETCH_TOOLS:
                t0 = time.monotonic()
                result = await self._bridge.call_tool(name, dict(args))
                calls.append((name, dict(args), result, int((time.monotonic() - t0) * 1000)))
        except Exception as exc:
            log.warning("Opening prefetch failed; the model calls the tools (session %s): %s",
                        self._orm_session_id, exc)
            return int((time.monotonic() - t_start) * 1000)

        tool_uses, tool_results = [], []
        for name, args, result, ms in calls:
            tool_use_id = f"prefetch_{name}"
            tool_uses.append({"toolUse": {"toolUseId": tool_use_id, "name": name, "input": args}})
            shown = _with_own_questions_marked(name, result)
            tool_results.append({"toolResult": {"toolUseId": tool_use_id, "content": [{"json": shown}]}})
            if name == "get_session_context":
                self._remember_reactions(result)
            self._remember_names(name, result)
            trace.append(ToolTrace(
                tool=name, input=args, result=result,
                result_preview=json.dumps(result)[:300] if result is not None else "",
                ms=ms, is_error=False, prefetched=True,
            ))
        self._history.append({"role": "assistant", "content": tool_uses})
        self._history.append({"role": "user", "content": tool_results})
        return sum(ms for *_, ms in calls)

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
        prefetch_context: bool = False,
    ) -> TurnResult:
        """Process one user utterance and return reply + diagnostics.

        prefetch_context (the opening turn only): the code calls
        get_session_context and get_pending_questions before the first LLM
        call (_prefetch_opening), which saves the model one tool round.

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
        if prefetch_context:
            tools_ms_total += await self._prefetch_opening(trace)

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
                        self._remember_names(tool_name, result)
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

        reply_text = first_names_only(clean_reply(reply_text, ending), self._full_names)
        if not ending and asks_to_stop(user_text) and "?" not in reply_text:
            # The model said goodbye without calling end_conversation.
            ending = True

        # Privacy gate: a mark (the model's keep_private, or the auto-mark when
        # the reply promises privacy without one) needs the speaker to have
        # asked for privacy. Only a clear "no" from the checker stops it.
        # Privacy guard: from the turn keep_private is requested on, a reply
        # must not touch the hidden part.
        hiding_now: list[str] = []
        if store_user and (self._hide_next or requested_scope in ("this_turn", "previous_turn")):
            hiding_now.append(user_text)
        if requested_scope == "previous_turn":
            prev = next((t for t in reversed(self._turns) if t.user_text and not t.hidden), None)
            if prev is not None:
                hiding_now.append(prev.user_text)
        guard: str | None = None
        terms = self._guard_terms(hiding_now, user_text if store_user else None)
        if mentions_any(reply_text, terms):
            reply_text, guard, extra_ms = await self._regenerate_without(terms, text_blocks, ending)
            llm_ms_total += extra_ms

        # Final rule, after the guard and any regeneration: a spoken promise of
        # privacy must be true. Covered: an explicit keep_private this turn, or a
        # turn an earlier "next" hides. Otherwise check this turn and the previous
        # (not hidden) one; only a clear "no" stops the mark.
        privacy_check: str | None = None
        covered = requested_scope is not None or (self._hide_next and store_user)
        if claims_privacy(reply_text) and not covered:
            prev = next((t for t in reversed(self._turns) if t.user_text and not t.hidden), None)
            words = [w for w in (prev.user_text if prev else None,
                                 user_text if store_user else None) if w]
            if words:
                confirmed, check_ms = await self._privacy_requested(words)
                llm_ms_total += check_ms
            else:
                confirmed = False          # nobody said anything that could be kept
            if confirmed and store_user:
                privacy_check = "confirmed"
                requested_scope = "previous_turn"
                log.warning("Reply promised privacy without keep_private; marking this and the "
                            "previous turn (session %s)", self._ensure_session())
            else:
                privacy_check = "not_confirmed"
                log.warning("Privacy request not confirmed; promise removed (session %s)",
                            self._ensure_session())
                reply_text, extra_ms = await self._remove_promise(text_blocks, ending, terms)
                llm_ms_total += extra_ms

        if reply_block is not None:
            # Keep the history in line with what was actually spoken.
            reply_block["text"] = reply_text

        # Store segments.
        seg_end = self._elapsed_ms()
        # Without real audio (CLI, evals, tests) spans are placeholders. They must
        # never overlap, because mark_private works by range: an overlap would
        # hide a neighbouring turn. The backend passes real WAV positions for
        # the user and sets the agent's span after TTS (set_last_agent_span).
        segment_ids: list[str] = []
        if store_user:
            if user_start_ms is not None and user_end_ms is not None:
                u_start, u_end = user_start_ms, user_end_ms
            else:
                u_start = max(seg_start, self._placeholder_end)
                u_end = u_start + 100
                self._placeholder_end = u_end
            segment_ids.append(self._store_segment(
                self._person_id, user_text, u_start, u_end,
                words=user_words or [],
            ))
        a_start = max(seg_end, self._placeholder_end)
        self._placeholder_end = a_start + 100
        self._last_agent_segment_id = self._store_segment(
            None, reply_text, a_start, a_start + 100
        )
        segment_ids.append(self._last_agent_segment_id)

        # Privacy: turn the scope into turns to hide (code, not the model).
        record = _TurnRecord(user_block if store_user else None, text_blocks, segment_ids,
                             user_text=user_text if store_user else None)
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
            privacy_guard=guard,
            privacy_check=privacy_check,
        )
