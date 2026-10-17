"""
End-to-end run of the demo story through the real REST API (docs/PROJECT.md
"Demo videosu senaryosu"): server.app on 8080 and the MCP server on 8000, real
Bedrock, Whisper and Polly.

    python scripts/e2e_demo.py              # temp folder is deleted afterwards
    python scripts/e2e_demo.py --keep       # keep it (database, audio, server logs)
    python scripts/e2e_demo.py --restart    # move the clock by restarting the servers

Never touches data/evoca.db: the seed runs into a fresh database in a temp
folder, and both servers run with that folder as their working directory, so
session audio and TTS files land there too. Whisper's model cache is shared
with the repo (data/hf-cache) so it is not downloaded again.

The clock is DEMO_NOW plus the demo offset (core/clock.py). By default both
servers start once with DEMO_NOW = D0 and EVOCA_DEMO_MODE=1, and the story
moves to another day with POST /api/demo/advance, as in the judges' demo (it
also publishes due stories and runs the invitation scheduler at once). With
--restart, the old path: both servers are restarted with a new DEMO_NOW every
time the story moves to another day (and server.run_invitations runs between):

  D0 08:00  seed; admin settings and family questions (steps 1-2)
  D1 09:35  after the new chat time: invitation, device session, archivist (3-5)
  D1+25h    the 24-hour wait is over: published story, reaction, correction (6),
            Elif's own recording (7)
  D3 09:35  next day: the invitation and the opening tell Fatma about the reaction (8)

Times are Europe/Istanbul (the seed circle's timezone), D0 is today.
Every step prints PASS/FAIL with its time; the exit code is 0 only if all pass.

Needs AWS credentials (Bedrock, Polly) and free ports 8000 and 8080.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import boto3
import httpx

REPO = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8080"
MCP_PORT, API_PORT = 8000, 8080
ISTANBUL = timezone(timedelta(hours=3))
SAMPLE_RATE = 16_000
FATMA_VOICE = "Kendra"   # the seed session's voice for Fatma (scripts/make_seed_audio.py)

CHAT_TIME = "09:30"
SENSITIVE_TOPIC = "Uncle Rasim's bankruptcy"
FILTERED_QUESTION = "Grandma, what happened with Uncle Rasim's bankruptcy?"
NORMAL_QUESTION = "Grandma, what was your favourite song when you were young?"

SCHOOL_ANSWER = (
    "School was a small stone building at the edge of our village. Our teacher, Mister Kaya, "
    "made us recite poems every morning, and in winter each child carried a piece of firewood "
    "for the stove."
)
SECRET_TURN = (
    "I will tell you something, but keep this between us. I once hid my cousin Nuri's silver "
    "bracelet inside the flour sack, and I never gave it back."
)
SECRET_WORDS = ["Nuri", "bracelet", "flour"]
LISTEN_TURN = "Could you play me my story about the mulberry tree?"
ELIF_MEMORY = (
    "When I was eight, my grandmother Fatma taught me how to roll stuffed grape leaves in her "
    "kitchen in Trabzon. My fingers were too small, and she laughed and said every leaf has its "
    "own shape."
)

ARCHIVIST_TIMEOUT_S = 300
SERVER_START_TIMEOUT_S = 240


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

class StepFailed(Exception):
    pass


@dataclass
class StepResult:
    name: str
    ok: bool = True
    seconds: float = 0.0
    failures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Audio (Polly)
# ---------------------------------------------------------------------------

_polly = None


def polly_pcm(text: str, voice: str = FATMA_VOICE) -> bytes:
    """16 kHz mono 16-bit PCM of the text, from Polly."""
    global _polly
    if _polly is None:
        _polly = boto3.Session(region_name=os.environ.get("POLLY_REGION", "eu-north-1")).client("polly")
    resp = _polly.synthesize_speech(Text=text, OutputFormat="pcm", SampleRate=str(SAMPLE_RATE),
                                    VoiceId=voice, Engine="standard")
    return resp["AudioStream"].read()


def wav_bytes(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


def speech_wav(text: str, voice: str = FATMA_VOICE) -> bytes:
    """A spoken clip with a little silence around it, like a real recording."""
    pad = b"\x00\x00" * (SAMPLE_RATE // 4)
    return wav_bytes(pad + polly_pcm(text, voice) + pad)


# ---------------------------------------------------------------------------
# Servers
# ---------------------------------------------------------------------------

def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


class Servers:
    """The MCP server and the backend: started once in demo mode, or restarted
    with a new DEMO_NOW (restart=True)."""

    def __init__(self, workdir: Path, restart: bool = False) -> None:
        self.workdir = workdir
        self.restart = restart
        self.logs = workdir / "logs"
        self.logs.mkdir(exist_ok=True)
        self.procs: list[subprocess.Popen] = []
        self.backend_log: Path | None = None
        self._files: list[Any] = []
        self._count = 0

    def env(self, demo_now: datetime) -> dict[str, str]:
        env = dict(os.environ)
        env.update({
            "DEMO_NOW": demo_now.astimezone(timezone.utc).isoformat(),
            "EVOCA_DB_PATH": str(self.workdir / "evoca.db"),
            "EVOCA_MCP_URL": f"http://127.0.0.1:{MCP_PORT}/mcp",
            "PYTHONPATH": str(REPO) + os.pathsep + env.get("PYTHONPATH", ""),
            "PYTHONIOENCODING": "utf-8",
        })
        if not self.restart:
            env["EVOCA_DEMO_MODE"] = "1"
        else:
            env.pop("EVOCA_DEMO_MODE", None)
        env.setdefault("HF_HOME", str(REPO / "data" / "hf-cache"))
        return env

    def run_module(self, module: str, demo_now: datetime, *args: str) -> str:
        out = subprocess.run([sys.executable, "-m", module, *args], cwd=self.workdir,
                             env=self.env(demo_now), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=120)
        if out.returncode != 0:
            raise StepFailed(f"{module} failed: {out.stderr.strip()[-400:]}")
        return out.stdout

    def start(self, demo_now: datetime) -> None:
        self.stop()
        self._count += 1
        env = self.env(demo_now)
        for name, app, port in (("mcp", "mcp_server.server:app", MCP_PORT),
                                ("backend", "server.app:app", API_PORT)):
            log_path = self.logs / f"{name}_{self._count}.log"
            f = open(log_path, "w", encoding="utf-8")
            self._files.append(f)
            self.procs.append(subprocess.Popen(
                [sys.executable, "-m", "uvicorn", app, "--port", str(port), "--log-level", "warning"],
                cwd=self.workdir, env=env, stdout=f, stderr=subprocess.STDOUT,
            ))
            if name == "backend":
                self.backend_log = log_path
        deadline = time.time() + SERVER_START_TIMEOUT_S
        while time.time() < deadline:
            if any(p.poll() is not None for p in self.procs):
                raise StepFailed(f"a server exited on start; see {self.logs}")
            if port_in_use(MCP_PORT):
                try:
                    if httpx.get(f"{API}/api/circles/demo", timeout=5).status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
            time.sleep(1)
        raise StepFailed("servers did not start in time")

    def stop(self) -> None:
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
        for f in self._files:
            f.close()
        self.procs, self._files = [], []

    def wait_for_log(self, done: list[str], failed: list[str], timeout: float) -> str:
        """Wait until the backend log has one of the lines; returns the line."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            text = self.backend_log.read_text(encoding="utf-8", errors="replace") if self.backend_log else ""
            for line in text.splitlines():
                if any(m in line for m in failed):
                    raise StepFailed(f"background job failed: {line.strip()[:300]}")
                if any(m in line for m in done):
                    return line.strip()
            time.sleep(2)
        raise StepFailed(f"timed out after {timeout:.0f} s waiting for: {done[0]}")


# ---------------------------------------------------------------------------
# The demo
# ---------------------------------------------------------------------------

class Demo:
    def __init__(self, workdir: Path, restart: bool = False) -> None:
        self.workdir = workdir
        self.restart = restart
        self.servers = Servers(workdir, restart)
        self.http = httpx.Client(base_url=API, timeout=240)
        self.results: list[StepResult] = []
        self.current: StepResult | None = None

        today = datetime.now(ISTANBUL).date()
        day = lambda n, h, m: datetime(today.year, today.month, today.day, h, m, tzinfo=ISTANBUL) + timedelta(days=n)
        self.t0 = day(0, 8, 0)
        self.t1 = day(1, 9, 35)
        self.t2 = self.t1 + timedelta(hours=25)
        self.t3 = day(3, 9, 35)
        self.now = self.t0

        self.ids: dict[str, str] = {}
        self.seed_story_ids: set[str] = set()
        self.session_id: str | None = None
        self.new_story_ids: list[str] = []
        self.answer_story_id: str | None = None

    # -- helpers ------------------------------------------------------------

    def check(self, ok: bool, what: str) -> bool:
        if not ok:
            self.current.failures.append(what)
        return ok

    def note(self, text: str) -> None:
        self.current.notes.append(text)

    def req(self, method: str, url: str, who: str | None = None, expect: int = 200, **kw) -> httpx.Response:
        headers = {"x-person-id": self.ids[who]} if who else {}
        r = self.http.request(method, url, headers=headers, **kw)
        if r.status_code != expect:
            raise StepFailed(f"{method} {url} as {who}: HTTP {r.status_code} (expected {expect}): {r.text[:300]}")
        return r

    def json(self, method: str, url: str, who: str | None = None, **kw) -> Any:
        return self.req(method, url, who, **kw).json()

    def audio_ok(self, url: str, who: str) -> bool:
        r = self.http.get(url, headers={"x-person-id": self.ids[who]})
        return r.status_code == 200 and len(r.content) > 44

    def no_secret(self, payload: Any, where: str) -> None:
        text = json.dumps(payload, ensure_ascii=False).lower()
        found = [w for w in SECRET_WORDS if w.lower() in text]
        self.check(not found, f"secret words {found} in {where}")

    def lifeline_ids(self, person: str, who: str) -> set[str]:
        body = self.json("GET", f"/api/lifeline/{self.ids[person]}", who)
        return {s["id"] for p in body["periods"] for s in p["stories"]}

    def turn(self, text: str) -> dict[str, Any]:
        r = self.req("POST", "/api/device/turn", "fatma", data={"session_id": self.session_id},
                     files={"audio": ("turn.wav", speech_wav(text), "audio/wav")})
        return r.json()

    def check_turn_shape(self, body: dict[str, Any], label: str) -> None:
        self.check(bool(body.get("reply_text")), f"{label}: empty reply_text")
        url = body.get("reply_audio_url")
        self.check(bool(url) and self.audio_ok(url, "fatma"), f"{label}: reply audio does not play")
        self.check(isinstance(body.get("trace"), list) and all(
            {"tool", "input", "result_preview", "ms", "is_error"} <= set(t) for t in body["trace"]
        ), f"{label}: trace items malformed")
        want = {"llm_ms", "tools_ms", "tts_ms", "total_ms", "mcp_connect_ms"}
        if label != "opening":
            want |= {"stt_ms"}
        self.check(want <= set(body.get("latency", {})), f"{label}: latency fields missing")
        self.note(f"{label}: {body['latency'].get('total_ms')} ms · {body.get('reply_text', '')[:90]!r}")

    def move_to(self, when: datetime) -> None:
        """Move the story's clock to `when`: restart the servers (--restart) or
        POST /api/demo/advance, which also publishes and runs the invitations."""
        if self.restart:
            self.servers.stop()
            if when in (self.t1, self.t3):
                out = self.servers.run_module("server.run_invitations", when)
                self.check("created 1 invitation" in out, f"run_invitations: {out.strip()}")
            self.servers.start(when)
        else:
            hours = (when - self.now).total_seconds() / 3600
            body = self.json("POST", "/api/demo/advance", json={"hours": hours})
            self.check(datetime.fromisoformat(body["now"]) == when,
                       f"advance {hours:.2f} h: now {body['now']}, wanted {when.isoformat()}")
            clock = self.json("GET", "/api/demo/clock")
            self.check(clock["now"] == body["now"], f"demo clock: {clock}")
            self.note(f"advanced {hours:.2f} h to {body['now']}")
        self.now = when

    def run_step(self, name: str, fn: Callable[[], None]) -> None:
        self.current = StepResult(name)
        t = time.monotonic()
        try:
            fn()
        except StepFailed as exc:
            self.current.failures.append(str(exc))
        except Exception as exc:  # report and go on to the next step
            self.current.failures.append(f"{type(exc).__name__}: {exc}")
        self.current.seconds = time.monotonic() - t
        self.current.ok = not self.current.failures
        self.results.append(self.current)
        mark = "PASS" if self.current.ok else "FAIL"
        print(f"[{mark}] {name} ({self.current.seconds:.1f} s)", flush=True)
        for n in self.current.notes:
            print(f"       {n}", flush=True)
        for f in self.current.failures:
            print(f"       ! {f}", flush=True)

    # -- steps --------------------------------------------------------------

    def setup(self) -> None:
        for port in (MCP_PORT, API_PORT):
            if port_in_use(port):
                raise StepFailed(f"port {port} is in use; stop the running server first")
        (self.workdir / "data" / "audio").mkdir(parents=True)
        (self.workdir / "data" / "tts").mkdir(parents=True)
        # The seed copies its session audio to data/audio under the working directory.
        self.servers.run_module("core.seed", self.t0)
        self.servers.start(self.t0)
        self.note(f"workdir {self.workdir}; D0 = {self.t0.isoformat()}")

    def step1_people(self) -> None:
        circle = self.json("GET", "/api/circles/demo")
        people = self.json("GET", f"/api/people?circle_id={circle['id']}")
        def pick(role: str, first: str) -> str:
            for p in people:
                if p["name"].split()[0] == first and p["role"] == role:
                    return p["id"]
            raise StepFailed(f"no {role} named {first}")
        self.ids = {"elif": pick("member", "Elif"), "ayse": pick("admin", "Ayşe"),
                    "fatma": pick("center", "Fatma")}
        self.seed_story_ids = self.lifeline_ids("fatma", "fatma")

    def step2_admin_and_questions(self) -> None:
        body = self.json("PATCH", "/api/admin/circle", "ayse", json={"chat_time": CHAT_TIME})
        self.check(body.get("chat_time") == CHAT_TIME, f"chat_time not {CHAT_TIME}: {body}")
        self.req("POST", "/api/admin/sensitive-topics", "ayse", json={"text": SENSITIVE_TOPIC})
        topics = self.json("GET", "/api/admin/sensitive-topics", "ayse")
        self.check(SENSITIVE_TOPIC in json.dumps(topics, ensure_ascii=False), "topic not listed")
        filtered = self.json("POST", "/api/questions", "elif",
                             json={"target_person_id": self.ids["fatma"], "text": FILTERED_QUESTION})
        self.check(filtered.get("status") == "filtered", f"touching question not filtered: {filtered}")
        self.check("Rasim" not in json.dumps(filtered), "filtered message names the topic")
        normal = self.json("POST", "/api/questions", "elif",
                           json={"target_person_id": self.ids["fatma"], "text": NORMAL_QUESTION})
        self.check(normal.get("status") == "waiting", f"normal question not waiting: {normal}")

    def step3_invitation(self) -> None:
        self.move_to(self.t1)
        body = self.json("GET", "/api/device/invitation", "fatma")
        self.check(datetime.fromisoformat(body.get("now", "")) == self.t1, f"device clock: {body.get('now')}")
        self.check(body.get("active") is True, f"light is off: {body}")
        reason = (body.get("invitation") or {}).get("reason", "")
        self.check("Elif" in reason, f"reason does not mention Elif: {reason!r}")
        self.note(f"reason: {reason!r}")

    def step4_device_session(self) -> None:
        start = self.json("POST", "/api/device/session/start", "fatma")
        self.session_id = start["session_id"]
        self.check_turn_shape(start, "opening")
        kinds = {c["type"] for c in start["cards"]}
        self.check("reaction" in kinds, f"opening has no reaction card: {start['cards']}")
        self.check("question" in kinds, f"opening has no question card: {start['cards']}")

        t1 = self.turn(SCHOOL_ANSWER)
        self.check_turn_shape(t1, "answer")
        self.check(bool(t1.get("heard_text")), "answer: nothing heard")

        t2 = self.turn(SECRET_TURN)
        self.check_turn_shape(t2, "secret")
        self.check(any(t["tool"] == "keep_private" for t in t2["trace"])
                   or any(t["tool"] == "mark_private" for t in t2["trace"]), "secret: nothing marked private")
        self.no_secret(t2["reply_text"], "the reply to the secret")

        t3 = self.turn(LISTEN_TURN)
        self.check_turn_shape(t3, "listen")
        self.no_secret(t3["reply_text"], "the playlist reply")
        playlists = [c for c in t3["cards"] if c["type"] == "playlist"]
        if self.check(len(playlists) == 1, f"listen: no playlist card ({t3['trace'] and [t['tool'] for t in t3['trace']]})"):
            items = playlists[0]["items"]
            self.check(bool(items), "playlist card is empty")
            self.check(all(self.audio_ok(i["url"], "fatma") for i in items), "a playlist url does not play")
            self.note(f"playlist: {[i['title'] for i in items]}")

        end = self.json("POST", "/api/device/session/end", "fatma", json={"session_id": self.session_id})
        self.check(end.get("processing") == "started", f"session/end: {end}")

    def step5_archivist(self) -> None:
        line = self.servers.wait_for_log(
            [f"Archivist finished session {self.session_id}"],
            [f"Archivist failed for session {self.session_id}", "is NOT run for this session"],
            ARCHIVIST_TIMEOUT_S,
        )
        self.note(line.split(": ", 1)[-1])
        new = self.lifeline_ids("fatma", "fatma") - self.seed_story_ids
        self.check(bool(new), "no new story about Fatma")
        self.new_story_ids = sorted(new)
        feed = self.json("GET", "/api/feed", "elif")
        self.check(not [i for i in feed["items"] if i["type"] == "question_answered"],
                   "answer shown to Elif while its story is pending")
        self.no_secret(feed, "Elif's feed")
        self.no_secret(self.json("GET", f"/api/lifeline/{self.ids['fatma']}", "fatma"), "Fatma's lifeline")
        for sid in self.new_story_ids:
            self.no_secret(self.json("GET", f"/api/stories/{sid}", "fatma"), f"story {sid} (teller's view)")
        self.note(f"answer held back while pending; new stories: {len(self.new_story_ids)}")

    def step6_published(self) -> None:
        self.move_to(self.t2)
        deadline = time.time() + 20
        visible: set[str] = set()
        while time.time() < deadline:   # the publisher runs right after startup
            visible = self.lifeline_ids("fatma", "elif")
            if set(self.new_story_ids) & visible:
                break
            time.sleep(1)
        self.check(bool(set(self.new_story_ids) & visible), "new story not on Fatma's lifeline for Elif")

        feed = self.json("GET", "/api/feed", "elif")
        self.no_secret(feed, "Elif's feed")
        answers = [i for i in feed["items"] if i["type"] == "question_answered"]
        if self.check(bool(answers), "no answer card in Elif's feed"):
            a = answers[0]["answer"]
            self.answer_story_id = a["story_id"]
            self.check(bool(a.get("audio_url")), "answer card has no audio_url")
            if a.get("audio_url"):
                self.check(self.audio_ok(a["audio_url"], "elif"), "answer audio does not play for Elif")
            self.note(f"answer: {answers[0]['question']['text']!r} -> {a.get('story_title')!r}")
        for sid in visible & set(self.new_story_ids):
            self.no_secret(self.json("GET", f"/api/stories/{sid}", "elif"), f"story {sid}")

        target = self.answer_story_id or next(iter(visible & set(self.new_story_ids)), None)
        if target is None:
            raise StepFailed("no published story to react to")
        r = self.json("POST", f"/api/stories/{target}/reactions", "elif",
                      json={"emoji": "heart", "action": "add"})
        self.check("heart" in r.get("present", []) and "heart" in r.get("mine", []), f"reaction: {r}")
        c = self.json("PATCH", f"/api/stories/{target}/subjects/{self.ids['fatma']}", "elif",
                      json={"period": "childhood"})
        self.check(c.get("period") == "childhood" and c.get("period_source") == "family",
                   f"period correction: {c}")

    def step7_recording(self) -> None:
        before = self.lifeline_ids("elif", "elif") | self.lifeline_ids("fatma", "elif")
        r = self.req("POST", "/api/recordings", "elif", expect=202,
                     files={"audio": ("memory.wav", speech_wav(ELIF_MEMORY, "Salli"), "audio/wav")})
        sid = r.json()["session_id"]
        line = self.servers.wait_for_log(
            [f"Archivist finished recording session {sid}"],
            [f"Archivist failed for recording session {sid}", f"Transcription failed for recording session {sid}",
             f"Recording session {sid}: no speech heard"],
            ARCHIVIST_TIMEOUT_S,
        )
        self.note(line.split(": ", 1)[-1])
        mine = self.lifeline_ids("elif", "elif") - before
        on_fatma = self.lifeline_ids("fatma", "elif") - before
        new = mine | on_fatma
        if not self.check(bool(new), "the recording made no story on any lifeline"):
            return
        for story_id in new:
            story = self.json("GET", f"/api/stories/{story_id}", "elif")
            subjects = {s["person_id"] for s in story.get("subjects", [])}
            if self.ids["elif"] in subjects:
                self.check(story_id in mine, f"{story_id} not on Elif's lifeline")
            if self.ids["fatma"] in subjects:
                self.check(story_id in on_fatma, f"{story_id} not on Fatma's lifeline")
            self.note(f"{story['title']!r}: subjects {sorted('elif' if s == self.ids['elif'] else 'fatma' if s == self.ids['fatma'] else s for s in subjects)}, "
                      f"links {len(story.get('linked_stories', []))}")
        self.check(bool(mine), "the recording is not on Elif's own lifeline")

    def step8_next_day(self) -> None:
        self.move_to(self.t3)
        inv = self.json("GET", "/api/device/invitation", "fatma")
        reason = (inv.get("invitation") or {}).get("reason", "")
        self.check(inv.get("active") is True, f"light is off: {inv}")
        self.check("Elif" in reason and "react" in reason, f"reason does not mention the reaction: {reason!r}")
        self.note(f"reason: {reason!r}")
        start = self.json("POST", "/api/device/session/start", "fatma")
        self.check_turn_shape(start, "opening")
        self.check(any(c["type"] == "reaction" and c["from"]["id"] == self.ids["elif"] for c in start["cards"]),
                   f"no reaction card from Elif: {start['cards']}")
        self.check("Elif" in start["reply_text"], "opening does not mention Elif")
        self.json("POST", "/api/device/session/end", "fatma", json={"session_id": start["session_id"]})

    # -- run ----------------------------------------------------------------

    def run(self) -> bool:
        t = time.monotonic()
        try:
            self.run_step("0. Fresh seed in a temp folder, servers up", self.setup)
            if self.results[-1].ok:
                for name, fn in [
                    ("1. People: Elif, Ayse (admin), Fatma (center)", self.step1_people),
                    ("2. Admin chat time + topic; filtered and waiting questions", self.step2_admin_and_questions),
                    ("3. Invitation after chat time mentions Elif", self.step3_invitation),
                    ("4. Device session: answer, secret, playlist", self.step4_device_session),
                    ("5. Archivist; answer held back while pending; no secret", self.step5_archivist),
                    ("6. +25 h: published, answer audio, reaction, correction", self.step6_published),
                    ("7. Elif's recording reaches the lifelines", self.step7_recording),
                    ("8. Next day: invitation and opening mention the reaction", self.step8_next_day),
                ]:
                    self.run_step(name, fn)
        finally:
            self.servers.stop()
            self.http.close()
        total = time.monotonic() - t
        print("\n| Step | Result | Time (s) |\n|---|---|---|")
        for r in self.results:
            print(f"| {r.name} | {'PASS' if r.ok else 'FAIL'} | {r.seconds:.1f} |")
        passed = sum(r.ok for r in self.results)
        print(f"\n{passed}/{len(self.results)} steps passed · total {total:.0f} s")
        return passed == len(self.results) == 9


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end demo run against the real API.")
    parser.add_argument("--keep", action="store_true", help="keep the temp folder (database, audio, logs)")
    parser.add_argument("--restart", action="store_true",
                        help="move the clock by restarting the servers with a new DEMO_NOW (no demo mode)")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    workdir = Path(tempfile.mkdtemp(prefix="evoca_e2e_"))
    ok = False
    try:
        ok = Demo(workdir, restart=args.restart).run()
    finally:
        if args.keep:
            print(f"Kept {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
