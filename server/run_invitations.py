"""
Demo CLI: one pass of the invitation scheduler (core/services/invitations.py).

    python -m server.run_invitations
    DEMO_NOW=2026-10-18T07:05:00+00:00 python -m server.run_invitations

Prints the clock and every invitation it created (sent or skipped).
"""

from __future__ import annotations

from core.clock import now_utc
from core.db import SessionLocal, init_db
from core.models import Circle, Invitation
from core.services.invitations import run_invitations


def main() -> None:
    init_db()
    with SessionLocal() as db:
        created = run_invitations(db)
        print(f"now = {now_utc().isoformat()}: created {len(created)} invitation(s)")
        for inv_id in created:
            inv = db.get(Invitation, inv_id)
            circle = db.get(Circle, inv.circle_id)
            print(f"  {circle.name}  {inv.date}  {inv.status}  {inv.reason!r}")


if __name__ == "__main__":
    main()
