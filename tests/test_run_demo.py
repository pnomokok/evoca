"""
Tests for the .env handling of scripts/run_demo.py.

  read_env_file  KEY=VALUE lines; comments, blank lines and lines without "="
                 are skipped; quotes are removed; a missing file is empty
  demo_env       .env fills in unset variables, never overrides one already
                 set, and the demo settings (EVOCA_DB_PATH, ...) always win
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "run_demo.py"
_spec = importlib.util.spec_from_file_location("run_demo", _PATH)
run_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_demo)


def test_read_env_file_parses_key_value_lines(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n"
        "\n"
        "POLLY_REGION=eu-north-1\n"
        "  EVOCA_TTS_VOICE = Joanna  \n"
        'QUOTED="a b"\n'
        "EMPTY=\n"
        "URL=http://localhost:8000/mcp?a=b\n"
        "not a setting\n",
        encoding="utf-8",
    )
    assert run_demo.read_env_file(env_file) == {
        "POLLY_REGION": "eu-north-1",
        "EVOCA_TTS_VOICE": "Joanna",
        "QUOTED": "a b",
        "EMPTY": "",
        "URL": "http://localhost:8000/mcp?a=b",
    }


def test_read_env_file_missing_is_empty(tmp_path: Path) -> None:
    assert run_demo.read_env_file(tmp_path / ".env") == {}


def test_demo_env_never_overrides_a_set_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(
        "POLLY_REGION=us-east-1\nEVOCA_TTS_VOICE=Matthew\nEVOCA_DB_PATH=data/evoca.db\n", encoding="utf-8"
    )
    monkeypatch.setattr(run_demo, "REPO", tmp_path)
    monkeypatch.setenv("POLLY_REGION", "eu-north-1")
    monkeypatch.delenv("EVOCA_TTS_VOICE", raising=False)

    env = run_demo.demo_env()

    assert env["POLLY_REGION"] == "eu-north-1"         # already set: kept
    assert env["EVOCA_TTS_VOICE"] == "Matthew"         # unset: from .env
    assert env["EVOCA_DB_PATH"] == str(run_demo.DEMO_DB)
