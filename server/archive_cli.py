"""
Run the archivist agent on one finished session.

Prerequisites
-------------
1. Start the MCP server in a separate terminal:
       uvicorn mcp_server.server:app --port 8000

2. Archive the most recent ended session of the first circle:
       python -m server.archive_cli
   or a specific session:
       python -m server.archive_cli <session_id>

The center person is used as the viewer identity.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import anyio

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import SessionLocal, init_db
from core.models import Circle, Question, Session as OrmSession, Story, StorySubject
from server.agents.archivist_agent import ArchivistAgent, archivist_model_id
from server.llm import BedrockLLM
from server.mcp_bridge import MCPBridge


def _pick_session(db, circle_id: str, session_id: str | None) -> OrmSession:
    if session_id:
        sess = db.get(OrmSession, session_id)
        if sess is None or sess.circle_id != circle_id:
            print(f"Session {session_id} not found in this circle.")
            sys.exit(1)
        return sess
    sess = (
        db.query(OrmSession)
        .filter(OrmSession.circle_id == circle_id, OrmSession.ended_at.isnot(None))
        .order_by(OrmSession.ended_at.desc())
        .first()
    )
    if sess is None:
        print("No ended session found.")
        sys.exit(1)
    return sess


async def main(argv: list[str]) -> None:
    init_db()

    with SessionLocal() as db:
        circle = db.query(Circle).first()
        if circle is None:
            print("No circle found in the database. Run: python -m core.seed")
            sys.exit(1)
        circle_id, person_id = circle.id, circle.center_person_id
        sess = _pick_session(db, circle_id, argv[1] if len(argv) > 1 else None)
        session_id = sess.id

    model_id = archivist_model_id()
    print(f"Circle    : {circle.name}")
    print(f"Session   : {session_id} (started {sess.started_at})")
    print(f"Model     : {model_id}")
    print(f"MCP server: {os.environ.get('EVOCA_MCP_URL', 'http://localhost:8000/mcp')}\n")

    llm = BedrockLLM(model_id=model_id, max_tokens=4096)
    async with MCPBridge(person_id, circle_id) as bridge:
        agent = ArchivistAgent(llm=llm, person_id=person_id, circle_id=circle_id, bridge=bridge)
        result = await agent.run(session_id)

    print("Trace:")
    for t in result.trace:
        status = "ERR" if t.is_error else "ok"
        print(f"  [{status}] {t.tool}({t.input}) -> {t.result_preview[:120]!r}  ({t.ms} ms)")

    with SessionLocal() as db:
        print(f"\nStories created ({len(result.story_ids)}):")
        for sid in result.story_ids:
            s = db.get(Story, sid)
            subjects = db.query(StorySubject).filter(StorySubject.story_id == sid).all()
            periods = ", ".join(f"{x.person_id[:8]}:{x.period}" for x in subjects) or "-"
            print(f"  - {s.title}  [{periods}]  place={s.place}  year={s.stated_year}")
            print(f"    {s.ai_summary}")
            print(f"    sources={list(s.sources)}")

        print(f"\nAnswers recorded ({len(result.answers_recorded)}):")
        for qid in result.answers_recorded:
            q = db.get(Question, qid)
            print(f"  - {q.text}  -> {dict(q.answer) if q.answer else None}")

        print(f"\nQuestions added ({len(result.questions_added)}):")
        for item in result.questions_added:
            q = db.get(Question, item["question_id"])
            print(f"  - [{item['status']}] {q.text if q else item['question_id']}")

    print(f"\nFinal text: {result.final_text}")
    lat = result.latency
    print(f"Latency: llm={lat['llm_ms']} ms  tools={lat['tools_ms']} ms  total={lat['total_ms']} ms")


if __name__ == "__main__":
    anyio.run(main, sys.argv)
