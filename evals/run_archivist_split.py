"""
Archivist eval: is one memory saved as one story, and two memories as two?

Usage (from the repo root, with AWS credentials):
    python -m evals.run_archivist_split                   # 3 runs per scenario, label "split"
    python -m evals.run_archivist_split --repeat 3 --label split_v1
    python -m evals.run_archivist_split --scenario two_memories --label check

The real archivist (Bedrock, the production prompt and checker) runs against an
in-memory SQLite database through the test harness's FakeArchiveBridge
(tests/test_archivist_agent.py), which calls the real archive services. The
model is offered the MCP server's real tool schemas, read in-process from
mcp_server.server (its own database is set to :memory:). No real database and
no MCP server process are used.

Scenarios:
  one_memory    the harbour memory with several details (like the real run that
                became "The Harbour in Akcaabat" and "The Fishing Boats of Akcaabat")
  two_memories  a childhood harbour memory, then a wedding years later elsewhere

Writes evals/results/<label>.md (table) and <label>.json (titles, splits, trace).
"""

from __future__ import annotations

import os

# Importing mcp_server.server runs init_db(); never against data/evoca.db.
os.environ["EVOCA_DB_PATH"] = ":memory:"

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import anyio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.clock import now_utc
from core.enums import CircleStatus, Role, SessionKind, SessionStart
from core.models import Base, Circle, Membership, Person, Segment, Session as OrmSession, Story
from server.agents.archivist_agent import ArchivistAgent, answer_check_llm, archivist_llm
from mcp_server.server import mcp
from tests.test_archivist_agent import FakeArchiveBridge

RESULTS_DIR = Path("evals") / "results"


@dataclass
class SplitScenario:
    name: str
    expected_stories: int
    lines: list[tuple[str, str]]   # (speaker: "center" | "agent", text)


SCENARIOS = [
    SplitScenario("one_memory", 1, [
        ("center", "On Sunday mornings my father took me down to the harbour in Akcaabat. The sea smelled "
                   "of salt and diesel, and the gulls were screaming over the water."),
        ("agent", "That sounds lively. What else do you remember about the harbour?"),
        ("center", "The fishing boats were painted blue and red, and every one had its name written on the "
                   "side. My favourite was called Deniz Yildizi, the starfish."),
        ("agent", "What a lovely name. What did your father do there?"),
        ("center", "He talked with the fishermen while they mended their nets. Sometimes one of them gave me "
                   "a small fish to carry home, and I felt so proud walking back up the hill with it."),
    ]),
    SplitScenario("two_memories", 2, [
        ("center", "When I was a little girl, my father took me to the harbour in Akcaabat on Sunday "
                   "mornings to watch the fishing boats come in with their catch."),
        ("agent", "What a lovely picture. What do you remember from later in your life?"),
        ("center", "Years later I got married in Trabzon. The wedding was in my aunt's garden, and my "
                   "husband's family came all the way from Rize by bus, with drums and a zurna."),
        ("agent", "That must have been quite a celebration."),
        ("center", "It was. We danced the horon until midnight, and my mother cried the whole evening."),
    ]),
]


class SchemaBridge(FakeArchiveBridge):
    """The fake bridge, offering the real MCP tool schemas (the test fake's are empty)."""

    async def bedrock_tool_config(self) -> dict:
        return {"tools": [
            {"toolSpec": {"name": t.name, "description": t.description or "",
                          "inputSchema": {"json": t.input_schema or {"type": "object", "properties": {}}}}}
            for t in await mcp.list_tools()
        ]}


def build_world(sc: SplitScenario):
    """A fresh in-memory family with one ended session holding the scenario's lines."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)()
    now = now_utc()
    fatma = Person(name="Fatma Yilmaz", birth_year=1948, language="en")
    db.add(fatma)
    db.flush()
    circle = Circle(name="Eval Family", center_person_id=fatma.id, status=CircleStatus.active,
                    chat_time="10:00", timezone="Europe/Istanbul")
    db.add(circle)
    db.flush()
    db.add(Membership(person_id=fatma.id, circle_id=circle.id, role=Role.center))
    sess = OrmSession(circle_id=circle.id, kind=SessionKind.solo, started_by=SessionStart.spontaneous,
                      participant_ids=[fatma.id], started_at=(now - timedelta(minutes=20)).isoformat(),
                      ended_at=now.isoformat())
    db.add(sess)
    db.flush()
    cursor = 0
    for speaker, text in sc.lines:
        length = 400 * len(text.split())   # about 150 words per minute
        db.add(Segment(session_id=sess.id, speaker_id=fatma.id if speaker == "center" else None,
                       start_ms=cursor, end_ms=cursor + length, transcript=text,
                       words=[], is_private=False))
        cursor += length + 500
    db.commit()
    return db, fatma, circle, sess


async def run_once(sc: SplitScenario, run: int) -> dict[str, Any]:
    db, fatma, circle, sess = build_world(sc)
    try:
        bridge = SchemaBridge(db, fatma.id, circle.id, session_id=sess.id)
        agent = ArchivistAgent(llm=archivist_llm(), person_id=fatma.id, circle_id=circle.id,
                               bridge=bridge, checker_llm=answer_check_llm())
        result = await agent.run(sess.id)
        titles = [db.get(Story, sid).title for sid in result.story_ids]
        return {
            "scenario": sc.name, "run": run, "expected": sc.expected_stories,
            "stories": len(result.story_ids), "titles": titles,
            "possible_splits": [list(p) for p in result.possible_splits],
            "ok": len(result.story_ids) == sc.expected_stories,
            "tools": [t.tool for t in result.trace],
            "tool_errors": [f"{t.tool}: {t.result_preview[:150]}" for t in result.trace if t.is_error],
            "total_ms": result.latency.get("total_ms"),
        }
    finally:
        db.close()


async def main(repeat: int, label: str, chosen: list[SplitScenario]) -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    for sc in chosen:
        for run in range(1, repeat + 1):
            print(f"Running {sc.name} (run {run}/{repeat}) ...", flush=True)
            try:
                runs.append(await run_once(sc, run))
            except Exception as exc:   # record and keep going
                runs.append({"scenario": sc.name, "run": run, "expected": sc.expected_stories,
                             "stories": None, "titles": [], "possible_splits": [], "ok": False,
                             "error": f"{type(exc).__name__}: {exc}"[:300]})
            r = runs[-1]
            print(f"  {r['stories']} stories {r['titles']}" + (f"  ERROR {r['error']}" if r.get("error") else ""))

    lines = ["# Archivist split eval", "",
             f"Archivist model: `{archivist_llm().model_id}` · runs per scenario: {repeat}", "",
             "| Scenario | Expected stories | Correct runs | Stories per run | Possible splits logged | Titles |",
             "|---|---|---|---|---|---|"]
    for sc in chosen:
        rs = [r for r in runs if r["scenario"] == sc.name]
        titles = " / ".join("; ".join(r["titles"]) or "–" for r in rs)
        lines.append(
            f"| {sc.name} | {sc.expected_stories} | {sum(r['ok'] for r in rs)}/{len(rs)} | "
            f"{', '.join(str(r['stories']) for r in rs)} | {sum(len(r['possible_splits']) for r in rs)} | "
            f"{titles.replace('|', '/')} |"
        )
    report = "\n".join(lines) + "\n"
    (RESULTS_DIR / f"{label}.md").write_text(report, encoding="utf-8")
    (RESULTS_DIR / f"{label}.json").write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print(report)
    return 0 if all(r["ok"] for r in runs) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Archivist split eval (one memory = one story).")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--label", default="split")
    parser.add_argument("--scenario", help="run only these scenarios (names, comma-separated)")
    args = parser.parse_args()
    wanted = set(args.scenario.split(",")) if args.scenario else None
    chosen = [sc for sc in SCENARIOS if wanted is None or sc.name in wanted]
    if not chosen:
        sys.exit(f"Unknown scenario. Choose from: {', '.join(sc.name for sc in SCENARIOS)}")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    sys.exit(anyio.run(main, args.repeat, args.label, chosen))
