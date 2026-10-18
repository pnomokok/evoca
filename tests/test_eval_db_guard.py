"""
Tests for the eval-only reset guard (core.db.require_eval_db, used by
evals/run_evals.build_family before it drops every table).

  require_eval_db   accepts a file named *eval*.db; refuses evoca.db, demo.db,
                    browser.db, any other name and :memory:
  import order      importing the chat agent first binds core.db to the default
                    data/evoca.db; the eval reset then refuses instead of
                    dropping it (fresh interpreter, drop_all replaced by a
                    sentinel so a broken guard still cannot touch the file)
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from sqlalchemy import create_engine

from core.db import UnsafeResetError, require_eval_db

REPO = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", ["eval.db", "eval_chat.db", "split-eval.db"])
def test_eval_named_file_is_accepted(tmp_path, name):
    path = tmp_path / name
    assert require_eval_db(create_engine(f"sqlite:///{path}")) == path.resolve()


@pytest.mark.parametrize("name", ["evoca.db", "demo.db", "browser.db", "evoca.backup-1018.db", "eval.sqlite"])
def test_other_files_are_refused(tmp_path, name):
    with pytest.raises(UnsafeResetError, match="named \\*eval\\*.db"):
        require_eval_db(create_engine(f"sqlite:///{tmp_path / name}"))


def test_in_memory_database_is_refused():
    with pytest.raises(UnsafeResetError):
        require_eval_db(create_engine("sqlite:///:memory:"))


def test_eval_reset_after_importing_the_chat_agent_cannot_touch_evoca_db(tmp_path):
    evoca_db = REPO / "data" / "evoca.db"
    before = (evoca_db.stat().st_size, evoca_db.stat().st_mtime_ns) if evoca_db.exists() else None

    script = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(REPO)!r})
        import server.agents.chat_agent          # binds core.db before the eval harness sets EVOCA_DB_PATH
        import evals.run_evals as run_evals
        from core.db import UnsafeResetError, engine
        from core.models import Base

        def sentinel(*args, **kwargs):
            raise SystemExit("drop_all reached")
        Base.metadata.drop_all = sentinel

        print("ENGINE", engine.url.database)
        try:
            run_evals.build_family(run_evals.SCENARIOS[0])
        except UnsafeResetError as exc:
            print("REFUSED", exc)
            sys.exit(0)
        sys.exit("not refused")
    """)
    env = {k: v for k, v in os.environ.items() if k != "EVOCA_DB_PATH"}
    out = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env,
                         capture_output=True, text=True, timeout=120)

    assert out.returncode == 0, out.stdout + out.stderr
    assert f"ENGINE {evoca_db.resolve()}" in out.stdout      # the dangerous setup was reproduced
    assert "REFUSED" in out.stdout and "evoca.db" in out.stdout
    after = (evoca_db.stat().st_size, evoca_db.stat().st_mtime_ns) if evoca_db.exists() else None
    assert after == before
