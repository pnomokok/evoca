"""
Widen the answers of one session to their whole story, as merge_stories now
does (core.services.archive_tools.extend_session_answers). For databases made
before that change.

    python scripts/fix_answers.py --db data/browser.db <session_id>

Refuses data/evoca.db.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", required=True, help="SQLite database to repair")
    parser.add_argument("session_id")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    if db_path == (ROOT / "data" / "evoca.db").resolve():
        sys.exit("Refusing to touch data/evoca.db.")
    if not db_path.exists():
        sys.exit(f"{db_path} does not exist.")
    os.environ["EVOCA_DB_PATH"] = str(db_path)  # read when core.db is imported

    from core.db import SessionLocal
    from core.models import Question
    from core.services.archive_tools import extend_session_answers

    with SessionLocal() as db:
        changed = extend_session_answers(db, args.session_id)
        db.commit()
        for qid in changed:
            ans = db.get(Question, qid).answer
            print(f"{qid}: {ans['start_ms']}-{ans['end_ms']} ms")
    print(f"{len(changed)} answer(s) widened.")


if __name__ == "__main__":
    main()
