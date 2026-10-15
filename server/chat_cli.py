"""
Terminal chat interface for the Evoca chat agent.

Prerequisites
-------------
1. Run the seed:
       python -m core.seed

2. Start the MCP server in a separate terminal:
       uvicorn mcp_server.server:app --port 8000

3. Start the chat:
       python -m server.chat_cli

Type your message and press Enter.  Type /end to finish the session and exit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import anyio

# Allow running from the repo root without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.db import SessionLocal, init_db
from core.models import Circle, Membership
from core.enums import Role
from server.agents.chat_agent import ChatAgent, chat_llm
from server.mcp_bridge import MCPBridge


def _find_circle_and_center(db):
    """Return (circle, center_person_id) for the first active circle."""
    circle = db.query(Circle).first()
    if circle is None:
        print("No circle found in the database. Run: python -m core.seed")
        sys.exit(1)
    return circle, circle.center_person_id


async def main() -> None:
    init_db()

    with SessionLocal() as db:
        circle, person_id = _find_circle_and_center(db)
        circle_id = circle.id

    print(f"Circle  : {circle.name}")
    print(f"Talking as center person ID: {person_id}")
    print(f"MCP server: {__import__('os').environ.get('EVOCA_MCP_URL', 'http://localhost:8000/mcp')}")
    print("Type your message. /end to finish.\n")

    llm = chat_llm()

    async with MCPBridge(person_id, circle_id) as bridge:
        with SessionLocal() as db:
            agent = ChatAgent(
                llm=llm,
                person_id=person_id,
                circle_id=circle_id,
                db_session=db,
                bridge=bridge,
            )

            # Kick off with an empty first turn so the agent greets.
            result = await agent.turn("(Session started.)", store_user=False)
            print(f"\nEvoca: {result.reply_text}\n")
            _print_diagnostics(result)

            while True:
                try:
                    user_input = input("You: ").strip()
                except (EOFError, KeyboardInterrupt):
                    user_input = "/end"

                if user_input == "/end":
                    agent.end()
                    print("\nSession ended. Goodbye.")
                    break

                if not user_input:
                    continue

                result = await agent.turn(user_input)
                print(f"\nEvoca: {result.reply_text}\n")
                _print_diagnostics(result)


def _print_diagnostics(result) -> None:
    """Print trace and latency in a compact one-line-per-tool form."""
    if result.trace:
        for t in result.trace:
            status = "ERR" if t.is_error else "ok"
            print(
                f"  [{status}] {t.tool}({t.input}) "
                f"→ {t.result_preview[:80]!r}  ({t.ms} ms)"
            )
    lat = result.latency
    print(
        f"  latency: llm={lat['llm_ms']} ms  "
        f"tools={lat['tools_ms']} ms  "
        f"total={lat['total_ms']} ms\n"
    )


if __name__ == "__main__":
    anyio.run(main)
