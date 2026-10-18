"""
Start the Evoca demo with one command (Windows, macOS, Linux):

    python scripts/run_demo.py

- Reads ./.env if it exists (KEY=VALUE lines) and passes it to both
  servers; a variable already set in the environment wins.
- Seeds data/demo.db if it does not exist yet (never touches data/evoca.db).
- Starts the MCP server on port 8000 and the backend on port 8080, both with
  EVOCA_DB_PATH=data/demo.db and EVOCA_DEMO_MODE=1, so the demo controls
  (/api/demo/*) work and both servers see the same demo clock.
- Ctrl+C stops both.

Start the web client separately (cd web && npm run dev). Bedrock, Whisper and
Polly need AWS credentials in the environment, as for the servers on their own.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMO_DB = REPO / "data" / "demo.db"
MCP_PORT, API_PORT = 8000, 8080
START_TIMEOUT_S = 240     # the backend loads Whisper on startup


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of a .env file; blank lines, comments and lines
    without "=" are skipped, and matching quotes around a value are removed."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def demo_env() -> dict[str, str]:
    env = dict(os.environ)
    # ./.env only fills in what the environment does not already set.
    for key, value in read_env_file(REPO / ".env").items():
        env.setdefault(key, value)
    env.update({
        "EVOCA_DB_PATH": str(DEMO_DB),
        "EVOCA_DEMO_MODE": "1",
        "EVOCA_MCP_URL": f"http://127.0.0.1:{MCP_PORT}/mcp",
        "PYTHONPATH": str(REPO) + os.pathsep + env.get("PYTHONPATH", ""),
        "PYTHONIOENCODING": "utf-8",
    })
    env.setdefault("HF_HOME", str(REPO / "data" / "hf-cache"))
    return env


def start(app: str, port: int) -> subprocess.Popen:
    # Own process group, so Ctrl+C reaches only this script and it stops the
    # servers itself, in order, on every platform.
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", app, "--port", str(port)],
        cwd=REPO, env=demo_env(), **kwargs,
    )


def stop(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        if p.poll() is None:
            # Let uvicorn shut down cleanly: CTRL_BREAK reaches a process group on Windows.
            p.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
    for p in procs:
        try:
            p.wait(timeout=15)
        except subprocess.TimeoutExpired:
            p.kill()


def _interrupt(*_args) -> None:
    raise KeyboardInterrupt


def main() -> int:
    # Being stopped (SIGTERM, or Ctrl+Break on Windows) stops the servers too, like Ctrl+C.
    signal.signal(signal.SIGTERM, _interrupt)
    if os.name == "nt":
        signal.signal(signal.SIGBREAK, _interrupt)

    busy = [port for port in (MCP_PORT, API_PORT) if port_in_use(port)]
    if busy:
        print(f"Port(s) {', '.join(map(str, busy))} already in use; stop the running server first.")
        return 1

    if not DEMO_DB.exists():
        print(f"Seeding {DEMO_DB.relative_to(REPO)} ...")
        out = subprocess.run([sys.executable, "-m", "core.seed"], cwd=REPO, env=demo_env())
        if out.returncode != 0:
            print("Seeding failed.")
            return 1
    else:
        print(f"Using {DEMO_DB.relative_to(REPO)} (delete it, or POST /api/demo/reset, to start over).")

    procs = [start("mcp_server.server:app", MCP_PORT), start("server.app:app", API_PORT)]
    try:
        deadline = time.time() + START_TIMEOUT_S
        while not (port_in_use(MCP_PORT) and port_in_use(API_PORT)):
            if any(p.poll() is not None for p in procs):
                print("A server exited on start; see the log above.")
                return 1
            if time.time() > deadline:
                print("The servers did not start in time.")
                return 1
            time.sleep(1)

        print()
        print("Evoca demo is running (demo mode on, database data/demo.db):")
        print(f"  Backend     http://localhost:{API_PORT}   (demo clock: /api/demo/clock)")
        print(f"  MCP server  http://localhost:{MCP_PORT}/mcp")
        print("  Web client  http://localhost:5173   (start it with: cd web && npm run dev)")
        print("Press Ctrl+C to stop both servers.")
        while all(p.poll() is None for p in procs):
            time.sleep(1)
        print("A server stopped; stopping the other one.")
        return 1
    except KeyboardInterrupt:
        print("\nStopping ...")
        return 0
    finally:
        stop(procs)


if __name__ == "__main__":
    sys.exit(main())
