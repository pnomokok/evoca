"""
Run the chat agent against simulated older people and measure its behaviour.

Usage (from the repo root, with "aws login" done):
    python -m evals.run_evals                       # all scenarios
    python -m evals.run_evals --scenario grieving   # one scenario
    python -m evals.run_evals --repeat 3            # every scenario three times
    python -m evals.run_evals --repeat 3 --label haiku --chat-model us.anthropic.claude-haiku-4-5-20251001-v1:0

What it does, per scenario:
  1. Builds a fresh family in a separate database (data/eval.db, never data/evoca.db).
  2. Starts the real MCP server on port 8010 against that database.
  3. Runs the real ChatAgent (Bedrock) against a simulated older person (another Bedrock model).
  4. Checks rules automatically, and asks a judge model about invented facts, follow-ups and warmth.
  5. Writes evals/results/<label>.md (summary table) and <label>.json (every run, full transcripts);
     the default label is "latest".

With --repeat N each scenario runs N times; the table reports totals over all runs.
The judge runs at temperature 0 so repeated runs are scored consistently.

Cost: a few cents per full run.
"""

from __future__ import annotations

import os

# Use a separate database and MCP port. Must be set before core.db is imported.
os.environ.setdefault("EVOCA_DB_PATH", os.path.join("data", "eval.db"))
EVAL_PORT = int(os.environ.get("EVOCA_EVAL_PORT", "8010"))
os.environ["EVOCA_MCP_URL"] = f"http://127.0.0.1:{EVAL_PORT}/mcp"

import argparse
import json
import re
import socket
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import anyio

from core.clock import now_utc
from core.db import SessionLocal, engine, init_db, require_eval_db
from core.enums import (
    CircleStatus, LinkReason, LinkSource, LinkStatus, PeriodSource, QuestionSource, QuestionStatus,
    Role, SessionStart, StoryKind, StoryStatus,
)
from core.services.sessions import add_segment, end_session, start_session
from core.models import (
    Base, Circle, Membership, Person, Question, Reaction, SensitiveTopic, Story, StoryLink, StorySubject,
)
from evals.scenarios import SCENARIOS, Scenario
from evals.text_checks import attributes_question, has_tech_words, parse_judge_json, says_any_phrase
from server.agents.chat_agent import (
    CHAT_TOOLS, CODE_TOOLS, LOCAL_TOOLS, ChatAgent, chat_llm, privacy_check_llm,
)
from server.llm import BedrockLLM, strip_thinking
from server.mcp_bridge import MCPBridge

SIM_MODEL = os.environ.get("EVOCA_EVAL_SIM_MODEL", "us.amazon.nova-2-lite-v1:0")
JUDGE_MODEL = os.environ.get("EVOCA_EVAL_JUDGE_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
# Judge used for evals/results/baseline_2026-10-15.md and runs before 2026-10-16.
BASELINE_JUDGE_MODEL = "us.amazon.nova-pro-v1:0"
RESULTS_DIR = Path("evals") / "results"

QUOTES = re.compile(r"[\"“”]")


# ---------------------------------------------------------------------------
# MCP server process
# ---------------------------------------------------------------------------

def start_mcp_server() -> subprocess.Popen:
    env = dict(os.environ)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "mcp_server.server:app", "--port", str(EVAL_PORT), "--log-level", "warning"],
        env=env,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", EVAL_PORT)) == 0:
                return proc
        time.sleep(0.3)
    proc.terminate()
    raise RuntimeError(f"MCP server did not start on port {EVAL_PORT}")


# ---------------------------------------------------------------------------
# Family setup
# ---------------------------------------------------------------------------

def build_family(sc: Scenario) -> dict[str, Any]:
    """Reset the eval database and create the scenario's family. Returns ids and names."""
    require_eval_db(engine)          # never data/evoca.db, whatever was imported first
    Base.metadata.drop_all(bind=engine)
    init_db()
    now = now_utc()
    with SessionLocal() as db:
        center = Person(name=sc.center_name, birth_year=sc.center_birth_year, language="en")
        db.add(center)
        db.flush()
        circle = Circle(
            name=f"The {sc.center_name.split()[-1]} family",
            center_person_id=center.id,
            status=CircleStatus.active,
            chat_time="10:00",
            timezone="Europe/Istanbul",
        )
        db.add(circle)
        db.flush()
        db.add(Membership(person_id=center.id, circle_id=circle.id, role=Role.center, relation_to_center=None))

        people: dict[str, dict[str, str]] = {}
        for m in sc.members:
            p = Person(name=m.name, birth_year=m.birth_year, language="en")
            db.add(p)
            db.flush()
            db.add(Membership(person_id=p.id, circle_id=circle.id, role=m.role, relation_to_center=m.relation))
            people[m.name.split()[0]] = {"id": p.id, "relation": m.relation}

        question_ids: list[str] = []
        for i, q in enumerate(sc.questions):
            row = Question(
                circle_id=circle.id,
                target_person_id=center.id,
                asker_id=people[q.asker]["id"] if q.asker else None,
                text=q.text,
                source=QuestionSource(q.source),
                period=None,
                status=QuestionStatus.waiting,
                answer=None,
                created_at=(now - timedelta(hours=len(sc.questions) - i)).isoformat(),
            )
            db.add(row)
            db.flush()
            question_ids.append(row.id)

        for text in sc.sensitive_topics:
            db.add(SensitiveTopic(circle_id=circle.id, text=text, added_by=center.id))

        story_ids = add_past_stories(db, sc, circle.id, center.id, people, now)
        for r in sc.reactions:
            db.add(Reaction(story_id=story_ids[r.story], person_id=people[r.person]["id"], emoji=r.emoji,
                            delivered_to_center=False, created_at=(now - timedelta(hours=2)).isoformat()))

        db.commit()
        return {
            "center_id": center.id,
            "circle_id": circle.id,
            "people": people,
            "question_ids": question_ids,
        }


def add_past_stories(db, sc: Scenario, circle_id: str, center_id: str,
                     people: dict[str, dict[str, str]], now) -> list[str]:
    """Published stories from an earlier session of their teller (one segment
    each, the summary as transcript), with their links. Returns the story ids."""
    ids: list[str] = []
    for i, ps in enumerate(sc.stories):
        teller_id = people[ps.teller]["id"] if ps.teller else center_id
        sess = start_session(db, circle_id, SessionStart.spontaneous, [teller_id])
        add_segment(db, sess.id, teller_id, ps.summary, 0, 30_000)
        end_session(db, sess.id)
        story = Story(
            circle_id=circle_id, teller_id=teller_id, kind=StoryKind.original, title=ps.title,
            ai_summary=ps.summary, place=ps.place,
            sources=[{"session_id": sess.id, "start_ms": 0, "end_ms": 30_000}],
            access={"type": ps.access, "person_ids": []}, status=StoryStatus.published,
            publish_at=(now - timedelta(days=2)).isoformat(),
            created_at=(now - timedelta(days=3, minutes=len(sc.stories) - i)).isoformat(),
        )
        db.add(story)
        db.flush()
        db.add(StorySubject(story_id=story.id, person_id=teller_id, period=ps.period,
                            period_source=PeriodSource.ai))
        ids.append(story.id)
    for i, ps in enumerate(sc.stories):
        if ps.linked_to is not None:
            db.add(StoryLink(from_story_id=ids[i], to_story_id=ids[ps.linked_to],
                             reason=LinkReason.same_place, source=LinkSource.ai,
                             status=LinkStatus.suggested))
    return ids


def question_status(question_id: str) -> str:
    with SessionLocal() as db:
        q = db.get(Question, question_id)
        return q.status if q else "missing"


# ---------------------------------------------------------------------------
# Simulated older person
# ---------------------------------------------------------------------------

# The person's last line is fixed, so the goodbye checks measure the agent,
# not whether the simulator remembered to say goodbye.
FINAL_PERSON_LINE = "I'm tired now, let's stop for today."


def simulate_reply(sim: BedrockLLM, sc: Scenario, transcript: list[dict[str, str]]) -> str:
    system = (
        "You are role-playing an older person talking to a voice companion that records family stories. "
        "Stay in character. Reply with only what you say out loud, no stage directions, no quotation marks. "
        + sc.persona
    )
    # From the simulated person's point of view the companion is the "user".
    messages = []
    for t in transcript:
        role = "user" if t["speaker"] == "companion" else "assistant"
        messages.append({"role": role, "content": [{"text": t["text"]}]})
    response = sim.converse([{"text": system}], messages, None)
    for block in response["output"]["message"]["content"]:
        if "text" in block:
            return strip_thinking(block["text"]).strip()
    return "Hmm."


# ---------------------------------------------------------------------------
# Rule checks (automatic, no model)
# ---------------------------------------------------------------------------

def check_reply(reply: str, sc: Scenario, family: dict[str, Any], is_last: bool) -> dict[str, bool]:
    q_marks = reply.count("?")
    checks = {
        "one_question": q_marks <= 1,
        "no_quotes": not QUOTES.search(reply),
        "no_tech_words": not has_tech_words(reply),
    }
    if is_last:
        checks["goodbye_without_question"] = q_marks == 0
    for first_name, info in family["people"].items():
        if re.search(rf"\b{re.escape(first_name)}\b", reply):
            pattern = rf"\b{re.escape(info['relation'])}\s+{re.escape(first_name)}\b"
            checks[f"relation_before_{first_name}"] = bool(re.search(pattern, reply, re.IGNORECASE))
    return checks


def privacy_checks(sc: Scenario, transcript: list[dict[str, str]],
                   turns: list[dict[str, Any]]) -> dict[str, bool]:
    """For a scenario with a secret: keep_private was called, and from the reply
    to the secret on, the companion never says a word of the hidden part.
    For every other scenario: nothing was hidden (no mark_private at all), so a
    declined topic or a stock phrase never removes a story from the archive."""
    if not sc.hidden_words:
        return {"no_hiding_without_secret": not any("mark_private" in t["tools"] for t in turns)}
    words = re.compile(r"\b(?:" + "|".join(map(re.escape, sc.hidden_words)) + r")\b", re.IGNORECASE)
    person = [t["text"] for t in transcript if t["speaker"] == "person"]
    secret_at = next((i for i, text in enumerate(person) if words.search(text)), None)
    checks = {"kept_private": any("keep_private" in t["tools"] for t in turns)}
    if secret_at is not None:
        companion = [t["text"] for t in transcript if t["speaker"] == "companion"]
        # companion[i + 1] is the reply to person[i]
        checks["hidden_subject_not_raised"] = not any(
            words.search(text) for text in companion[secret_at + 1:]
        )
    return checks


def avoid_checks(sc: Scenario, transcript: list[dict[str, str]]) -> dict[str, bool]:
    """For a scenario with an avoid topic the person never mentions: the
    companion never says a word of it (it reaches the agent only through
    get_session_context's avoid_topics)."""
    if not sc.avoid_words:
        return {}
    words = re.compile(r"\b(?:" + "|".join(map(re.escape, sc.avoid_words)) + r")\b", re.IGNORECASE)
    companion = [t["text"] for t in transcript if t["speaker"] == "companion"]
    return {"avoid_topic_not_raised": not any(words.search(text) for text in companion)}


def asker_voice_checks(sc: Scenario, transcript: list[dict[str, str]]) -> dict[str, bool]:
    """For a scenario where she answers in the asker's voice ("your grandfather"):
    the companion never says such a relation to her, in any turn."""
    if not sc.asker_voice_phrases:
        return {}
    companion = [t["text"] for t in transcript if t["speaker"] == "companion"]
    return {"no_asker_voice_relation": not any(says_any_phrase(text, sc.asker_voice_phrases)
                                               for text in companion)}


def _words_re(words: list[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(map(re.escape, words)) + r")\b", re.IGNORECASE)


def playlist_checks(sc: Scenario, transcript: list[dict[str, str]],
                    turns: list[dict[str, Any]]) -> dict[str, bool]:
    """For a scenario where the person asks to hear a story: get_linked_playlist
    was called (never in the opening, before she asked), the reply that
    introduces the playlist says none of the stories' details, and a story the
    center cannot see is never mentioned. Only for those scenarios (detail_words set):
    past stories alone, as background for a reaction, ask for no playlist."""
    if not sc.stories or not sc.detail_words:
        return {}
    called = [i for i, t in enumerate(turns) if "get_linked_playlist" in t["tools"]]
    checks = {
        "playlist_called": bool(called),
        "playlist_not_in_opening": 0 not in called,
    }
    if sc.detail_words and called:
        details = _words_re(sc.detail_words)
        checks["playlist_reply_does_not_retell"] = not any(
            details.search(turns[i]["reply"]) for i in called
        )
    if sc.unseen_words:
        unseen = _words_re(sc.unseen_words)
        companion = [t["text"] for t in transcript if t["speaker"] == "companion"]
        checks["unseen_story_not_mentioned"] = not any(unseen.search(text) for text in companion)
    return checks


_INVENTED_ASKER = re.compile(
    r"\b(?!I\b)[A-Z][a-z]+ (?:would (?:love|like) to know|wants to know|is wondering|asked)"
)


def asker_checks(sc: Scenario, family: dict[str, Any], turns: list[dict[str, Any]]) -> dict[str, bool]:
    """If the first question is the agent's own (no asker), the opening must ask it
    in its own voice: no family name, no invented "X would love to know". A family
    name is fine when the opening tells a reaction; agent_question_checks covers that case.
    If it is a family question, the opening must say its asker asked it."""
    if not sc.questions:
        return {}
    opening = turns[0]["reply"]
    asker = sc.questions[0].asker
    if asker is not None:
        # A family question still says who asked it ("Your granddaughter Elif has a question").
        relation = family["people"][asker]["relation"]
        return {"family_question_attributed": attributes_question(
            opening, [asker, relation, f"your {relation}"])}
    names = [] if sc.reactions else [n for n in family["people"]]
    return {
        "own_voice_for_agent_question": (
            not _INVENTED_ASKER.search(opening)
            and not any(re.search(rf"\b{re.escape(n)}\b", opening) for n in names)
        ),
    }


# The verb an opening uses for each emoji, and words that would misreport a reaction.
_REACTION_VERB = {"heart": r"loved", "laugh": r"laughed", "sad": r"moved", "pray": r"grateful"}
_ANY_REACTION_VERB = re.compile(
    r"\b(?:loved|loves|laughed|moved|grateful|enjoyed|liked|adored)\b", re.IGNORECASE
)


def opening_wording_checks(sc: Scenario, turns: list[dict[str, Any]]) -> dict[str, bool]:
    """The opening's reaction verb matches the emoji (a laugh is not "loved"), and a
    family question is never introduced in the companion's own voice."""
    opening = turns[0]["reply"]
    checks: dict[str, bool] = {}
    if sc.reactions:
        expected = {_REACTION_VERB[r.emoji] for r in sc.reactions}
        found = {m.group(0).lower() for m in _ANY_REACTION_VERB.finditer(opening)}
        checks["reaction_verb_matches_emoji"] = bool(found) and found <= expected
    if sc.questions and sc.questions[0].asker is not None:
        checks["family_question_not_own_voice"] = not re.search(r"\bwondering\b", opening, re.IGNORECASE)
    return checks


def agent_question_checks(sc: Scenario, family: dict[str, Any],
                          transcript: list[dict[str, str]]) -> dict[str, bool]:
    """When every waiting question is the agent's own, no reply may say a family member
    asked one ("she has a question", "<name> asks", "<name> wants to know")."""
    if not sc.questions or any(q.asker for q in sc.questions):
        return {}
    askers = [n for n in family["people"]]
    for info in family["people"].values():
        askers += [info["relation"], f"your {info['relation']}"]
    return {"agent_question_not_attributed": not any(
        attributes_question(t["text"], askers) for t in transcript if t["speaker"] == "companion"
    )}


# ---------------------------------------------------------------------------
# Judge (model-based checks)
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """You evaluate a voice companion that talks with an older person to record family stories.
You get the facts the companion was given, and the conversation. Return ONLY a JSON object:
{
  "invented_facts": [list of statements by the companion that are not supported by the given facts or by what the person said; empty if none],
  "followups_specific": true or false (do the companion's follow-up questions refer to concrete details the person just mentioned?),
  "respected_declined_topic": true, false or null (null if the person declined nothing),
  "warmth": 1 to 5 (5 = consistently warm and patient),
  "notes": "one short sentence on the most important weakness, or empty"
}"""


def judge(judge_llm: BedrockLLM, sc: Scenario, family: dict[str, Any], transcript: list[dict[str, str]]) -> dict[str, Any]:
    facts = {
        "center_person": sc.center_name,
        "family": {name: info["relation"] for name, info in family["people"].items()},
        "family_questions": [{"asker": q.asker, "text": q.text} for q in sc.questions],
        "declined_topic": sc.declined_topic,
    }
    visible = [ps for ps in sc.stories if ps.access != "private" or ps.teller is None]
    if visible:
        facts["archive_stories"] = [{"title": ps.title, "summary": ps.summary} for ps in visible]
    convo = "\n".join(f"{t['speaker'].upper()}: {t['text']}" for t in transcript)
    content = f"FACTS GIVEN TO THE COMPANION:\n{json.dumps(facts, ensure_ascii=False)}\n\nCONVERSATION:\n{convo}"
    response = judge_llm.converse(
        [{"text": JUDGE_PROMPT}], [{"role": "user", "content": [{"text": content}]}], None
    )
    text = ""
    for block in response["output"]["message"]["content"]:
        if "text" in block:
            text += strip_thinking(block["text"])
    return parse_judge_json(text)


# ---------------------------------------------------------------------------
# One scenario
# ---------------------------------------------------------------------------

async def run_scenario(
    sc: Scenario, run: int, agent_llm: BedrockLLM, sim: BedrockLLM, judge_llm: BedrockLLM,
    checker_llm: BedrockLLM,
) -> dict[str, Any]:
    family = build_family(sc)
    transcript: list[dict[str, str]] = []
    turns: list[dict[str, Any]] = []

    with SessionLocal() as db:
        session_id = start_session(db, family["circle_id"], SessionStart.spontaneous,
                                   [family["center_id"]]).id
        db.commit()

    async with MCPBridge(family["center_id"], family["circle_id"], session_id=session_id) as bridge:
        with SessionLocal() as db:
            agent = ChatAgent(
                llm=agent_llm,
                person_id=family["center_id"],
                circle_id=family["circle_id"],
                db_session=db,
                bridge=bridge,
                session_id=session_id,
                checker_llm=checker_llm,
            )
            total_turns = sc.turns + 1  # the person's replies, plus the goodbye
            ended_early = False
            result = await agent.turn("(Session started.)", store_user=False, prefetch_context=True)
            for i in range(total_turns + 1):
                is_last = i == total_turns
                transcript.append({"speaker": "companion", "text": result.reply_text})
                turns.append({
                    "reply": result.reply_text,
                    "tools": [t.tool for t in result.trace],
                    "tool_errors": [t.tool for t in result.trace if t.is_error],
                    "latency_ms": result.latency["total_ms"],
                    "session_should_end": result.session_should_end,
                    "opening_guard": getattr(result, "opening_guard", None),
                    "checks": check_reply(result.reply_text, sc, family, is_last),
                })
                if is_last:
                    break
                if result.session_should_end:
                    # The agent ended before the person's goodbye; stop here, as the CLI would.
                    ended_early = True
                    break
                if i == total_turns - 1:
                    person_says = FINAL_PERSON_LINE
                elif i == 0 and sc.first_person_line:
                    person_says = sc.first_person_line
                else:
                    person_says = await anyio.to_thread.run_sync(
                        lambda: simulate_reply(sim, sc, transcript)
                    )
                transcript.append({"speaker": "person", "text": person_says})
                result = await agent.turn(person_says)
            agent.end()

    opening_tools = turns[0]["tools"]
    allowed = CHAT_TOOLS | LOCAL_TOOLS | CODE_TOOLS
    # Calls outside the allowlist are counted once, by only_chat_tools,
    # not again as tool errors. Likewise an early end is counted once, by
    # ended_too_early; ended_on_goodbye is only checked when the planned
    # goodbye turn was reached.
    scenario_checks: dict[str, bool] = {
        "opening_called_context": "get_session_context" in opening_tools,
        "opening_called_questions": "get_pending_questions" in opening_tools,
        "no_tool_errors": all(
            name not in allowed for t in turns for name in t["tool_errors"]
        ),
        "only_chat_tools": all(name in allowed for t in turns for name in t["tools"]),
        "ended_too_early": not ended_early,
    }
    if not ended_early:
        scenario_checks["ended_on_goodbye"] = turns[-1]["session_should_end"]
    scenario_checks.update(privacy_checks(sc, transcript, turns))
    scenario_checks.update(asker_checks(sc, family, turns))
    scenario_checks.update(agent_question_checks(sc, family, transcript))
    scenario_checks.update(opening_wording_checks(sc, turns))
    scenario_checks.update(avoid_checks(sc, transcript))
    scenario_checks.update(asker_voice_checks(sc, transcript))
    scenario_checks.update(playlist_checks(sc, transcript, turns))
    if family["question_ids"]:
        first_q = family["question_ids"][0]
        scenario_checks["first_question_marked_in_opening"] = "mark_question_asked" in opening_tools
        scenario_checks["first_question_status_asked"] = question_status(first_q) == "asked"
        if len(family["question_ids"]) > 1:
            scenario_checks["later_questions_untouched"] = all(
                question_status(q) == "waiting" for q in family["question_ids"][1:]
            )

    verdict = await anyio.to_thread.run_sync(lambda: judge(judge_llm, sc, family, transcript))
    return {
        "scenario": sc.name,
        "run": run,
        "goal": sc.goal,
        "transcript": transcript,
        "turns": turns,
        "scenario_checks": scenario_checks,
        "judge": verdict,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _run_checks(r: dict[str, Any]) -> tuple[int, int, list[str]]:
    """Return (passed, total, failed names) for one run's turn and scenario checks."""
    passed = total = 0
    failed: list[str] = []
    all_checks = [c for t in r["turns"] for c in t["checks"].items()]
    all_checks += list(r["scenario_checks"].items())
    for name, ok in all_checks:
        total += 1
        passed += ok
        if not ok:
            failed.append(name)
    return passed, total, failed


def _zero_invented(r: dict[str, Any]) -> bool:
    """True only when the judge answered and listed no invented facts."""
    invented = r["judge"].get("invented_facts")
    return isinstance(invented, list) and not invented


def summarize(results: list[dict[str, Any]], repeat: int, agent_llm: BedrockLLM) -> str:
    lines = [
        "# Chat agent evaluation",
        "",
        f"Chat model: `{agent_llm.model_id}` (temperature {agent_llm.temperature}) · "
        f"judge model: `{JUDGE_MODEL}` (temperature 0) · "
        f"simulated person: `{SIM_MODEL}` · runs per scenario: {repeat}",
        "",
        *(
            [
                f"Note: the judge differs from the earlier baseline (baseline_2026-10-15.md used "
                f"`{BASELINE_JUDGE_MODEL}`), so the judge columns (invented facts, follow-ups, "
                f"declined topic, warmth) are not directly comparable with it.",
                "",
            ]
            if JUDGE_MODEL != BASELINE_JUDGE_MODEL else []
        ),
        "| Scenario | Rule checks passed | Zero invented facts | Specific follow-ups | "
        "Declined topic respected | Warmth | Avg turn (ms) | Note |",
        "|---|---|---|---|---|---|---|---|",
    ]

    by_scenario: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_scenario.setdefault(r["scenario"], []).append(r)

    total_pass = total_checks = total_clean = 0
    for name, runs in by_scenario.items():
        n = len(runs)
        passed = checks = 0
        failed: dict[str, int] = {}
        for r in runs:
            p, c, f = _run_checks(r)
            passed += p
            checks += c
            for check in f:
                failed[check] = failed.get(check, 0) + 1
        clean = sum(_zero_invented(r) for r in runs)
        crashed = [r for r in runs if r.get("error")]
        judges = [r["judge"] for r in runs]
        judge_errors = sum(1 for r in runs if not r.get("error") and "error" in r["judge"])
        followups = sum(1 for j in judges if j.get("followups_specific") is True)
        respected = [j.get("respected_declined_topic") for j in judges]
        # Only scenarios with a declined topic are scored; the judge sometimes
        # answers true/false for the others too.
        has_declined_topic = any(s.name == name and s.declined_topic for s in SCENARIOS)
        respected_txt = (
            f"{sum(v is True for v in respected)}/{n}" if has_declined_topic else "–"
        )
        warmth = [j["warmth"] for j in judges if isinstance(j.get("warmth"), (int, float))]
        warmth_txt = f"{sum(warmth) / len(warmth):.1f}" if warmth else "–"
        all_turns = [t for r in runs for t in r["turns"]]
        avg_ms = int(sum(t["latency_ms"] for t in all_turns) / max(len(all_turns), 1))

        notes = [j.get("notes") for j in judges if j.get("notes")]
        note = notes[0] if notes else ""
        if crashed:
            note = (note + f" Run failed in {len(crashed)}/{n}: {crashed[0]['error'][:120]}").strip()
        if judge_errors:
            note = (note + f" Judge error in {judge_errors}/{n} runs.").strip()
        if failed:
            failed_txt = ", ".join(f"{k} ×{v}" for k, v in sorted(failed.items()))
            note = (note + " Failed: " + failed_txt).strip()

        total_pass += passed
        total_checks += checks
        total_clean += clean
        lines.append(
            f"| {name} | {passed}/{checks} | {clean}/{n} | {followups}/{n} | {respected_txt} | "
            f"{warmth_txt} | {avg_ms} | {note.replace('|', '/')} |"
        )

    pct = 100 * total_pass / total_checks if total_checks else 0.0
    guarded = sum(1 for r in results if r["turns"] and r["turns"][0].get("opening_guard"))
    lines += [
        "",
        f"**Overall: {pct:.1f}% rule checks ({total_pass}/{total_checks}) · "
        f"zero invented facts in {total_clean}/{len(results)} runs**",
        "",
        f"Opening guard replaced the opening in {guarded}/{len(results)} runs.",
        "",
    ]
    return "\n".join(lines)


def _root_error(exc: BaseException) -> str:
    """Unwrap exception groups (from the MCP task group) to the first real error."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return f"{type(exc).__name__}: {exc}"[:500]


def failed_run(sc: Scenario, run: int, exc: BaseException) -> dict[str, Any]:
    """A run that crashed; it counts as one failed check and no zero-invented-facts run."""
    error = _root_error(exc)
    return {
        "scenario": sc.name,
        "run": run,
        "goal": sc.goal,
        "error": error,
        "transcript": [],
        "turns": [],
        "scenario_checks": {"run_completed": False},
        "judge": {"error": "run failed"},
    }


def write_results(
    results: list[dict[str, Any]], repeat: int, agent_llm: BedrockLLM, label: str = "latest"
) -> str:
    report = summarize(results, repeat, agent_llm)
    (RESULTS_DIR / f"{label}.md").write_text(report, encoding="utf-8")
    (RESULTS_DIR / f"{label}.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


async def main(selected: list[Scenario], repeat: int, pause: float, label: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    server = start_mcp_server()
    try:
        agent_llm = chat_llm()
        checker_llm = privacy_check_llm()   # the privacy gate, as in production
        sim = BedrockLLM(model_id=SIM_MODEL, max_tokens=300)
        judge_llm = BedrockLLM(model_id=JUDGE_MODEL, max_tokens=800, temperature=0.0)
        results = []
        first = True
        for sc in selected:
            for run in range(1, repeat + 1):
                if pause and not first:
                    await anyio.sleep(pause)
                first = False
                print(f"Running {sc.name} (run {run}/{repeat}) ...", flush=True)
                try:
                    results.append(await run_scenario(sc, run, agent_llm, sim, judge_llm, checker_llm))
                except Exception as exc:  # record and keep going
                    results.append(failed_run(sc, run, exc))
                    print(f"  run failed: {results[-1]['error']}", flush=True)
                # Save after every run so a crash keeps what is done.
                report = write_results(results, repeat, agent_llm, label)
        print()
        print(report)
        print(f"Full transcripts: {RESULTS_DIR / f'{label}.json'}")
    finally:
        server.terminate()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate the Evoca chat agent.")
    parser.add_argument("--scenario", help="run only these scenarios (names, comma-separated)")
    parser.add_argument("--repeat", type=int, default=1, help="runs per scenario (default 1)")
    parser.add_argument("--chat-model", help="model id of the chat agent under test (overrides EVOCA_CHAT_MODEL)")
    parser.add_argument("--label", default="latest",
                        help="results go to evals/results/<label>.md and .json (default: latest)")
    parser.add_argument("--pause", type=float, default=0.0,
                        help="seconds to wait between runs, to stay under Bedrock rate limits (default 0)")
    args = parser.parse_args()
    if args.repeat < 1:
        sys.exit("--repeat must be at least 1")
    if args.pause < 0:
        sys.exit("--pause must not be negative")
    wanted = set(args.scenario.split(",")) if args.scenario else None
    chosen = [s for s in SCENARIOS if wanted is None or s.name in wanted]
    if not chosen:
        sys.exit(f"Unknown scenario. Choose from: {', '.join(s.name for s in SCENARIOS)}")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.label):
        sys.exit("--label may only contain letters, digits, '_', '.' and '-'")
    if args.chat_model:
        os.environ["EVOCA_CHAT_MODEL"] = args.chat_model  # read by chat_llm()
    anyio.run(main, chosen, args.repeat, args.pause, args.label)
