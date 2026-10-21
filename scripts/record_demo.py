"""
Record the product part of the demo video from a real run of the app (Playwright, Chromium,
1920x1080, deviceScaleFactor 1). scripts/edit_demo.py turns the recording into the video.

    python scripts/run_demo.py                  # terminal 1: MCP server + backend, demo mode
    cd web && npm run dev                       # terminal 2: web client on :5173
    python scripts/record_demo.py               # terminal 3 (--headed to watch it)

Needs: pip install playwright imageio-ffmpeg; python -m playwright install chromium; AWS
credentials for the servers (Bedrock, Whisper, Polly run for real).

Honesty rule: every frame is the real app on real AWS. The script only adds, in the recording,
a visible cursor (a small dark dot) and a soft ring on each click. Nothing on screen is edited.
It resets the demo first (POST /api/demo/reset, as "Reset demo" does) and keeps the guided tour
closed; the stage's "Use a sample answer" button belongs to the tour's answer step, so the script
sends the device pane the tour's own "answer step" message (utils/stageChannel.js) to show it.

The loop, step by step (each step is cut into its own clip by edit_demo.py):
  B0 The landing page: "Try the demo", the demo dialog, "Watch the loop".
  B1 Elif sends the suggested question on her phone.
  B2 Next morning: the device lights up with "Elif has a question for you".
  B3 Talk: the opening, sample answer 1 (the MCP tools panel meanwhile), the follow-up, sample
     answer 2 and its reply (recorded for the story; the edit cuts that exchange).
  B4 In the archive: Ayse's Family settings with the topic, then Can asks about it.
  B5 Back on the stage: the goodbye sample; "Evoca is writing up the story...".
  B6 +1 day: the answer banner on Elif's phone, open the answer, play it.
  B7 Elif reacts with laugh, then adds a photo with its caption to that story.
  B8 Next morning, Talk: the device tells Fatma that Elif laughed.
  B9 Exit demo; then, in a fresh browser context, "Create your family": the wizard, the personal
     link, the new family's journal with Getting started.

Output (data/ is not committed): data/video/raw/
  stage.webm, archive.webm, family.webm   the page recordings (one per browser page)
  audio/                     every audio file the app played, as the browser received it
  timeline.json              steps, waits, markers, every audio (start, stop, file) and checks
  timeline.txt               the same, readable
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

import httpx
from playwright.sync_api import Frame, FrameLocator, Locator, Page, sync_playwright

REPO = Path(__file__).resolve().parent.parent
WEB = "http://localhost:5173"
API = "http://127.0.0.1:8080"
OUT = REPO / "data" / "video" / "raw"
DEMO_DB = REPO / "data" / "demo.db"
PHOTO = REPO / "core" / "seed_assets" / "photos" / "spare_sled.jpg"
PHOTO_CAPTION = "Fatma and her best friend on the sled, around 1956"
# B9's new family (the wizard's third step, "You", is the person who creates it).
NEW_FAMILY = {"circle_name": "The Demir Family", "center.name": "Nermin Demir", "center.birth_year": "1946",
              "creator.name": "Selin Demir", "creator.birth_year": "1975", "creator.relation_to_center": "daughter"}
SAMPLES = REPO / "web" / "public" / "demo-audio"
SIZE = {"width": 1920, "height": 1080}

SUGGESTED_QUESTION = "Grandma, what games did you play when you were little?"   # web/src/utils/tour.js
TOPIC = "1972 separation from Hatice"
TOPIC_QUESTION = "What happened with Hatice in 1972?"
TOPIC_WORDS = ["hatice", "1972", "separation"]

STEP_TIMEOUT_S = 180
ARCHIVIST_TIMEOUT_S = 300

# Runs in every frame before the app. Logs every audio the page plays (with the URL it was fetched
# from: the app plays blobs) and, in the top frame, draws the recording's cursor and click ring.
INIT_SCRIPT = r"""
(() => {
  const log = (event) => {
    try { window.__evocaLog && window.__evocaLog({ t: Date.now() / 1000, frame: location.pathname + location.search, ...event }); } catch (e) {}
  };
  const blobSource = new WeakMap();
  const urlSource = new Map();
  const blob = Response.prototype.blob;
  Response.prototype.blob = async function () {
    const b = await blob.call(this);
    try { blobSource.set(b, this.url); } catch (e) {}
    return b;
  };
  const createObjectURL = URL.createObjectURL;
  URL.createObjectURL = function (obj) {
    const url = createObjectURL.call(URL, obj);
    if (obj && blobSource.has(obj)) urlSource.set(url, blobSource.get(obj));
    return url;
  };
  let nextId = 1;
  const play = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () {
    if (!this.__recId) {
      const el = this;
      el.__recId = `${nextId++}-${Math.random().toString(36).slice(2, 7)}`;
      const source = () => urlSource.get(el.currentSrc || el.src) || el.currentSrc || el.src;
      el.addEventListener('playing', () => log({ kind: 'audio_start', id: el.__recId, src: source(), pos: el.currentTime }));
      for (const name of ['pause', 'ended', 'emptied', 'abort', 'error']) {
        el.addEventListener(name, () => log({ kind: 'audio_stop', id: el.__recId, why: name, pos: el.currentTime }));
      }
    }
    return play.apply(this, arguments);
  };
  // Who paused an audio: the app's own code, or the browser (no app frame in the stack).
  const pause = HTMLMediaElement.prototype.pause;
  HTMLMediaElement.prototype.pause = function () {
    if (this.__recId && !this.paused) log({ kind: 'audio_pause_call', id: this.__recId, pos: this.currentTime, stack: (new Error().stack || '').split(String.fromCharCode(10)).slice(2, 6).join(' | ') });
    return pause.apply(this, arguments);
  };

  if (window !== window.top) return;
  const install = () => {
    if (document.getElementById('__rec_cursor')) return;
    const style = document.createElement('style');
    style.textContent = `
      #__rec_cursor { position: fixed; left: 0; top: 0; width: 16px; height: 16px; margin: -8px 0 0 -8px;
        border-radius: 50%; background: rgba(28, 25, 23, 0.82); box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.9),
        0 1px 4px rgba(0, 0, 0, 0.35); pointer-events: none; z-index: 2147483647; }
      .__rec_ring { position: fixed; width: 54px; height: 54px; margin: -27px 0 0 -27px; border-radius: 50%;
        border: 3px solid rgba(28, 25, 23, 0.4); background: rgba(28, 25, 23, 0.08); pointer-events: none;
        z-index: 2147483646; animation: __rec_ring 0.6s ease-out forwards; }
      @keyframes __rec_ring { from { transform: scale(0.35); opacity: 1; } to { transform: scale(1.2); opacity: 0; } }`;
    document.documentElement.appendChild(style);
    const dot = document.createElement('div');
    dot.id = '__rec_cursor';
    document.documentElement.appendChild(dot);
  };
  window.__recCursor = (x, y) => {
    install();
    const dot = document.getElementById('__rec_cursor');
    dot.style.left = `${x}px`;
    dot.style.top = `${y}px`;
  };
  window.__recRing = (x, y) => {
    install();
    const ring = document.createElement('div');
    ring.className = '__rec_ring';
    ring.style.left = `${x}px`;
    ring.style.top = `${y}px`;
    document.documentElement.appendChild(ring);
    setTimeout(() => ring.remove(), 700);
  };
})();
"""

# The tour's "answer step" message to the device pane (utils/tour.js, stageChannel.js): with it the
# device shows "Use a sample answer" once the suggested question was asked, as on the tour. This is
# the only signal the script sends the app itself: the button, its clip and everything after it
# (speech-to-text, the companion, its reply audio) are the real ones; only the tour card is not shown.
SAMPLE_STEP_SCRIPT = """() => {
  const channel = new BroadcastChannel('evoca-stage');
  channel.postMessage({ type: 'tour', kind: 'targets', byPane: { device: ['answer'] }, key: 'video-answer' });
  channel.close();
}"""


# The end of that step: the tour's message with no targets, so the device shows neither the
# button nor its note again (the B8 conversation).
SAMPLE_STEP_END_SCRIPT = """() => {
  const channel = new BroadcastChannel('evoca-stage');
  channel.postMessage({ type: 'tour', kind: 'targets', byPane: {}, key: '' });
  channel.close();
}"""


def port_open(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


class StepError(Exception):
    pass


class Recorder:
    """One browser context; one recorded page per place (the stage, the archive). Every action is
    logged with the wall clock, the same clock the pages log their audio with."""

    def __init__(self, headed: bool) -> None:
        self.headed = headed
        self.events: list[dict[str, Any]] = []
        self.steps: list[dict[str, Any]] = []
        self.waits: list[dict[str, Any]] = []
        self.audio_files: dict[str, str] = {}
        self.responses: list[dict[str, Any]] = []
        self.pages: dict[str, dict[str, Any]] = {}
        self.contexts: list[Any] = []
        self.brisk = False          # a quick hand: shorter moves, pauses and typing (B9's form)
        self.page: Page | None = None
        self.place = ""
        self.step: dict[str, Any] | None = None
        self.cursor = (960.0, 600.0)
        self.ids: dict[str, str] = {}
        self.notes: list[str] = []
        self.rng = random.Random(7)

    # -- logging -------------------------------------------------------------------------------

    def on_log(self, _source: Any, event: dict[str, Any]) -> None:
        event["place"] = self.place
        self.events.append(event)

    def on_response(self, response: Any) -> None:
        url = response.url
        path = urlparse(url).path
        try:
            ctype = response.headers.get("content-type", "")
            if response.status == 200 and (ctype.startswith("audio/") or path.endswith((".mp3", ".wav"))):
                if url not in self.audio_files:
                    # Playwright may hand back an empty body for a fetched blob; then the same URL
                    # is fetched again with the page's own headers (the same file, as served).
                    body = response.body()
                    if not body:
                        headers = {k: v for k, v in response.request.headers.items() if k.lower().startswith("x-")}
                        body = httpx.get(url, headers=headers, timeout=30).content
                    if not body:
                        raise StepError(f"empty audio {url}")
                    ext = {"audio/mpeg": ".mp3", "audio/wav": ".wav", "audio/x-wav": ".wav",
                           "audio/webm": ".webm", "audio/ogg": ".ogg"}.get(ctype.split(";")[0], Path(path).suffix or ".bin")
                    name = f"{len(self.audio_files) + 1:02d}_{re.sub(r'[^A-Za-z0-9_.-]', '_', Path(unquote(path)).stem)[:40]}{ext}"
                    (OUT / "audio" / name).write_bytes(body)
                    self.audio_files[url] = f"audio/{name}"
            elif path.startswith("/api/device/") or (path == "/api/questions" and response.request.method == "POST"):
                if "json" in ctype:
                    self.responses.append({"t": time.time(), "step": self.step and self.step["id"],
                                           "method": response.request.method, "path": path, "body": response.json()})
        except Exception as exc:  # a response body can vanish with its page; note it and go on
            self.notes.append(f"response {path}: {type(exc).__name__}: {exc}")

    def mark(self, name: str) -> None:
        if self.step is not None:
            self.step["markers"][name] = time.time()

    def begin(self, step_id: str, what: str) -> None:
        self.step = {"id": step_id, "what": what, "place": self.place, "start": time.time(), "markers": {}}
        print(f"{step_id} {what}", flush=True)

    def end(self) -> None:
        assert self.step is not None
        self.step["end"] = time.time()
        self.steps.append(self.step)
        print(f"   {self.step['end'] - self.step['start']:.1f} s", flush=True)
        self.step = None

    def wait_region(self, kind: str, fn: Callable[[], Any]) -> Any:
        """A wait the editor may speed up (up to 4x) or shorten; audio inside it stays real time."""
        start = time.time()
        try:
            return fn()
        finally:
            self.waits.append({"place": self.place, "kind": kind, "start": start, "end": time.time()})

    # -- pages ---------------------------------------------------------------------------------

    def new_context(self, browser: Any) -> Any:
        """A browser context that records video, with the cursor and the audio log; the guided
        tour stays closed (the captions explain instead)."""
        ctx = browser.new_context(viewport=SIZE, device_scale_factor=1, screen=SIZE, timezone_id="Europe/Istanbul",
                                  record_video_dir=str(OUT / "video_tmp"), record_video_size=SIZE)
        ctx.add_init_script(INIT_SCRIPT)
        ctx.add_init_script("try { localStorage.setItem('evoca_tour_seen', '1'); } catch (e) {}")
        ctx.expose_binding("__evocaLog", self.on_log)
        self.contexts.append(ctx)
        return ctx

    def open_page(self, ctx: Any, place: str, url: str, ready: Callable[[Page], None],
                  storage: dict[str, str] | None = None) -> Page:
        page = ctx.new_page()
        created = time.time()
        page.on("response", self.on_response)
        self.pages[place] = {"page": page, "created": created}
        self.use(place)
        if storage:
            # The demo viewer lives in localStorage; set it on the origin before the app loads.
            page.goto(f"{WEB}/favicon.svg")
            page.evaluate("(items) => { for (const [k, v] of Object.entries(items)) localStorage.setItem(k, v); }", storage)
        loading_start = time.time()
        page.goto(url)
        ready(page)
        page.wait_for_timeout(600)
        self.waits.append({"place": place, "kind": "loading", "start": created, "end": time.time()})
        self.pages[place]["ready"] = time.time()
        self.pages[place]["loading_start"] = loading_start
        paint = page.evaluate("""() => {
          const p = performance.getEntriesByType('paint');
          const e = p.find(x => x.name === 'first-paint') || p[0];
          return e ? (performance.timeOrigin + e.startTime) / 1000 : null;
        }""")
        self.pages[place]["first_paint"] = paint
        page.evaluate("([x, y]) => window.__recCursor(x, y)", list(self.cursor))
        return page

    def use(self, place: str) -> None:
        self.place = place
        self.page = self.pages[place]["page"]
        self.page.bring_to_front()

    @property
    def device(self) -> FrameLocator:
        return self.page.frame_locator("iframe.device-frame")

    @property
    def phone(self) -> FrameLocator:
        return self.page.frame_locator("iframe.phone-frame")

    # -- human-paced input ---------------------------------------------------------------------

    def pause(self, seconds: float, keep: bool = False) -> None:
        """A human-paced pause. keep: time to read what is on screen; otherwise it is idle time the
        editor may shorten (dead time)."""
        start = time.time()
        self.page.wait_for_timeout(int(seconds * 1000))
        if not keep:
            self.waits.append({"place": self.place, "kind": "idle", "start": start, "end": time.time()})

    def move_to(self, x: float, y: float, seconds: float | None = None) -> None:
        x0, y0 = self.cursor
        distance = ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
        if seconds is None:
            seconds = min(0.35, 0.15 + distance / 3000) if self.brisk else min(0.7, 0.25 + distance / 2400)
        # Paced by the clock: each step costs two round trips to the browser, so a fixed sleep per
        # step made a move last about three times as long as planned.
        steps = max(6, int(seconds * 24))
        start = time.time()
        for i in range(1, steps + 1):
            k = i / steps
            k = k * k * (3 - 2 * k)       # ease in and out
            cx, cy = x0 + (x - x0) * k, y0 + (y - y0) * k
            self.page.mouse.move(cx, cy)
            self.page.evaluate("([x, y]) => window.__recCursor(x, y)", [cx, cy])
            left = start + seconds * i / steps - time.time()
            if left > 0.005:
                self.page.wait_for_timeout(int(left * 1000))
        self.cursor = (x, y)

    def point_at(self, target: Locator, dwell: float = 0.0) -> tuple[float, float]:
        target.wait_for(state="visible", timeout=STEP_TIMEOUT_S * 1000)
        box = target.bounding_box()
        # Scroll only when it is off screen (scroll_into_view_if_needed also waits for an animated
        # element, such as the "writing up" spinner, to be still).
        if box is None or box["y"] < 0 or box["y"] + box["height"] > SIZE["height"]:
            target.scroll_into_view_if_needed()
            box = target.bounding_box()
        if box is None:
            raise StepError(f"no box for {target}")
        x = box["x"] + box["width"] / 2 + self.rng.uniform(-3, 3)
        y = box["y"] + box["height"] / 2 + self.rng.uniform(-2, 2)
        self.move_to(x, y)
        if dwell:
            self.pause(dwell, keep=True)
        return x, y

    def click(self, target: Locator, before: float = 0.55) -> None:
        self.point_at(target)
        expect_enabled(target)
        self.pause(0.12 if self.brisk else before + self.rng.uniform(0, 0.2))
        x, y = self.cursor
        self.page.evaluate("([x, y]) => window.__recRing(x, y)", [x, y])
        self.page.mouse.down()
        self.page.wait_for_timeout(90)
        self.page.mouse.up()

    def type_into(self, target: Locator, text: str) -> None:
        self.click(target, before=0.35)
        self.pause(0.1 if self.brisk else 0.3)
        self.page.keyboard.type(text, delay=12 if self.brisk else 32)

    def scroll(self, dy: float, over: Locator | None = None) -> None:
        if over is not None:
            self.point_at(over)
        for _ in range(8):
            self.page.mouse.wheel(0, dy / 8)
            self.page.wait_for_timeout(35)

    # -- waiting -------------------------------------------------------------------------------

    def until(self, check: Callable[[], bool], what: str, timeout: float = STEP_TIMEOUT_S, every: float = 0.2) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            error = self.device_error()
            if error:
                raise StepError(f"the device shows an error while waiting for {what}: {error}")
            try:
                if check():
                    return
            except Exception:
                pass
            self.page.wait_for_timeout(int(every * 1000))
        raise StepError(f"timed out after {timeout:.0f} s waiting for {what}")

    def device_error(self) -> str:
        """The device's error line, if the stage's device shows one (a failed Talk, for example)."""
        if self.place != "stage":
            return ""
        try:
            error = self.device.locator(".device-error")
            return error.inner_text(timeout=200) if error.count() else ""
        except Exception:
            return ""

    def audio_started_since(self, since: float, src_part: str = "") -> bool:
        return any(e["kind"] == "audio_start" and e["t"] >= since and src_part in e.get("src", "") for e in self.events)

    def audio_playing(self) -> bool:
        open_ids: set[str] = set()
        for e in self.events:
            if e["kind"] == "audio_start":
                open_ids.add(e["id"])
            elif e["kind"] == "audio_stop":
                open_ids.discard(e["id"])
        return bool(open_ids)

    def wait_reply_done(self, what: str) -> None:
        """The device's reply is over: no audio playing and the device itself no longer shows Stop.
        Once the browser paused a reply mid-way without telling the app (an \"ended\" never came), so
        the device kept showing Stop; then this notes it and presses the device's own Stop."""
        self.until(lambda: not self.audio_playing(), f"{what} to finish")
        stop = self.device.locator(".device-controls button", has_text="Stop")
        deadline = time.time() + 2.5
        while time.time() < deadline and stop.count():
            self.page.wait_for_timeout(200)
        if stop.count():
            self.notes.append(f"{self.step and self.step['id']}: {what} was paused by the browser before its end; "
                              "the device's Stop was pressed")
            self.click(stop, before=0.2)

    def wait_for_voice(self, since: float, what: str, src_part: str = "") -> None:
        """Wait until an audio started after `since` (the reply) and every audio has finished."""
        self.until(lambda: self.audio_started_since(since, src_part), f"{what} to start")
        self.until(lambda: not self.audio_playing(), f"{what} to finish")


def expect_enabled(target: Locator, timeout: float = STEP_TIMEOUT_S) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if target.is_enabled():
            return
        time.sleep(0.15)
    raise StepError(f"{target} stayed disabled")


# ---------------------------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------------------------

class Demo:
    def __init__(self, rec: Recorder) -> None:
        self.rec = rec
        self.http = httpx.Client(base_url=API, timeout=60)

    def as_(self, who: str) -> dict[str, str]:
        return {"x-person-id": self.rec.ids[who]}

    def load_people(self) -> None:
        circle = self.http.get("/api/circles/demo").json()
        people = self.http.get(f"/api/people?circle_id={circle['id']}").json()
        for p in people:
            self.rec.ids[p["name"].split()[0].lower().replace("ş", "s")] = p["id"]
        missing = {"fatma", "elif", "ayse", "can"} - set(self.rec.ids)
        if missing:
            raise StepError(f"demo people missing: {missing}")

    def stage_ready(self, page: Page) -> None:
        page.frame_locator("iframe.device-frame").locator('[data-tour="talk"]').wait_for(timeout=60_000)
        page.frame_locator("iframe.phone-frame").locator(".first-question-composer, .answer-card, main").first.wait_for(timeout=60_000)

    # B0 ----------------------------------------------------------------------------------------
    def b0(self) -> None:
        rec = self.rec
        rec.begin("B0", "The landing page: Try the demo, then Watch the loop")
        rec.pause(0.8, keep=True)
        rec.click(rec.page.get_by_role("button", name="Try the demo").first)
        rec.page.locator(".demo-entry-option").nth(1).wait_for(timeout=10_000)
        rec.pause(1.0, keep=True)                  # both options on screen
        rec.click(rec.page.locator(".demo-entry-option.primary"))
        # "Watch the loop" always opens the guided tour, which starts the demo over (new ids) and
        # then shows its first card; it is closed with its own X (the captions explain instead).
        close = rec.page.get_by_role("button", name="Close the guide")
        rec.wait_region("loading", lambda: (close.wait_for(timeout=90_000), self.stage_ready(rec.page)))
        rec.pause(0.3)
        rec.click(close, before=0.3)
        rec.until(lambda: close.count() == 0, "the guide to close")
        self.load_people()
        rec.pause(0.2, keep=True)
        rec.end()

    # B1 ----------------------------------------------------------------------------------------
    def b1(self) -> None:
        rec = self.rec
        rec.begin("B1", "Elif sends the suggested question on her phone")
        rec.pause(1.2)
        box = rec.phone.locator("#first-question-text")
        # The guide's first card prefills the suggested question (the guide was open in B0);
        # Elif types it only when the box is empty.
        if not box.input_value().strip():
            rec.type_into(box, SUGGESTED_QUESTION)
        else:
            rec.point_at(box, dwell=0.8)
        rec.pause(0.6)
        rec.click(rec.phone.locator('.first-question-composer button[type="submit"]'))
        rec.until(lambda: rec.phone.locator(".first-question-composer").count() == 0
                  or rec.phone.get_by_text(SUGGESTED_QUESTION[:30]).count() > 0, "the question in My questions")
        rec.pause(1.4, keep=True)
        rec.end()

    # B2 ----------------------------------------------------------------------------------------
    def b2(self) -> None:
        rec = self.rec
        rec.begin("B2", "Next morning: the device lights up")
        rec.pause(0.8)
        rec.click(rec.page.locator('button[data-tour="next-morning"]'))
        reason = rec.device.locator(".device-reason", has_text="Elif has a question")
        rec.wait_region("clock", lambda: reason.wait_for(timeout=60_000))
        rec.mark("light")
        rec.point_at(reason)
        rec.pause(2.0, keep=True)
        rec.end()

    # B3 ----------------------------------------------------------------------------------------
    def sample(self, n: int, during: Callable[[], None] | None = None) -> None:
        """Send sample answer n; `during` runs while the clip plays (it is real time anyway)."""
        rec = self.rec
        button = rec.device.locator("button.device-quiet-btn.sample")
        if button.count() == 0:
            rec.page.evaluate(SAMPLE_STEP_SCRIPT)
        rec.point_at(button)
        expect_enabled(button)
        clicked = time.time()
        rec.click(button, before=0.4)
        rec.mark(f"sample_{n}")
        if during is not None:
            rec.until(lambda: rec.audio_playing(), "the sample to start")
            during()
        # The sample plays, speech-to-text and the companion run, then the reply plays.
        rec.wait_region("thinking", lambda: rec.until(
            lambda: rec.audio_started_since(clicked, "/api/"), "the reply audio", timeout=STEP_TIMEOUT_S))
        rec.mark(f"reply_{n}")
        rec.wait_reply_done(f"the reply to sample answer {n}")

    def b3(self) -> None:
        rec = self.rec
        rec.begin("B3", "Talk: opening, sample answer 1, follow-up, sample answer 2")
        rec.pause(0.6)
        clicked = time.time()
        rec.click(rec.device.locator('[data-tour="talk"]'))
        rec.wait_region("thinking", lambda: rec.until(
            lambda: rec.audio_started_since(clicked, "/api/"), "the opening audio"))
        rec.mark("opening")
        rec.wait_reply_done("the opening")
        rec.page.evaluate(SAMPLE_STEP_SCRIPT)
        rec.pause(0.8)
        self.sample(1, during=self.show_tools)
        # The second exchange (sample answer 2 and its reply) is recorded, so the story has it, and
        # edit_demo.py cuts it between these markers, never inside a voice.
        rec.mark("exchange_2")
        rec.pause(0.5)
        self.sample(2)
        rec.mark("exchange_2_end")
        rec.pause(0.6)
        rec.end()

    def show_tools(self) -> None:
        """The MCP tools panel, while sample answer 1 plays: the newest turn's tool calls, or, when
        that turn made none (a plain follow-up), the opening's, under the panel's "Earlier turns"."""
        rec = self.rec
        panel = rec.device.locator('[data-testid="trace-panel"]')
        rows = panel.locator('[data-testid="trace-row"]:visible')
        if rows.count() == 0:
            rec.click(panel.locator(".trace-earlier summary"), before=0.3)
            rec.until(lambda: rows.count() > 0, "the earlier tool calls")
        rec.point_at(rows.first)
        rec.mark("trace")
        rec.move_to(rec.cursor[0] + 120, rec.cursor[1] + 24 * max(0, min(rows.count(), 6) - 1), seconds=1.4)
        rec.pause(1.4, keep=True)
        earlier = panel.locator("details.trace-earlier[open] summary")
        if earlier.count():
            rec.click(earlier, before=0.2)    # fold it again, so the panel does not grow under the captions

    # B4 ----------------------------------------------------------------------------------------
    def b4(self, ctx: Any) -> None:
        rec = self.rec
        rec.open_page(ctx, "archive", f"{WEB}/archive/settings",
                      lambda p: p.get_by_text(TOPIC).first.wait_for(timeout=60_000),
                      storage={"evoca_viewer_id": rec.ids["ayse"], "evoca_viewer_chosen": "1", "evoca_tour_seen": "1"})
        rec.begin("B4", "Privacy: Ayse's sensitive topic, then Can asks about it")
        rec.pause(0.8)
        rec.point_at(rec.page.get_by_text(TOPIC).first, dwell=2.0)

        # Switching to Can through the demo's person picker is navigation: the editor speeds it up.
        def switch() -> None:
            rec.click(rec.page.locator(".demo-strip-btn.viewer"), before=0.3)
            rec.click(rec.page.locator("button.person-option", has=rec.page.locator("strong", has_text=re.compile(r"^Can$"))).first, before=0.3)
            rec.page.get_by_role("button", name="Ask a question").first.wait_for(timeout=30_000)
        rec.wait_region("loading", switch)
        rec.mark("can")
        rec.pause(0.5)
        rec.click(rec.page.get_by_role("button", name="Ask a question").first)
        rec.pause(0.4)
        rec.type_into(rec.page.locator('[role="dialog"] textarea').first, TOPIC_QUESTION)
        rec.pause(0.4)
        sent = time.time()
        rec.click(rec.page.locator('button[type="submit"][data-tour="ask"]'))
        rec.until(lambda: any(r["path"] == "/api/questions" and r["t"] >= sent for r in rec.responses), "the question reply")
        rec.mark("answered")
        result = next(r for r in reversed(rec.responses) if r["path"] == "/api/questions")
        rec.notes.append(f"B4 POST /api/questions as Can -> status {result['body'].get('status')!r}: "
                         f"{result['body'].get('message') or ''}")
        rec.pause(2.6, keep=True)
        rec.end()

    # B5 ----------------------------------------------------------------------------------------
    def b5(self) -> None:
        rec = self.rec
        rec.use("stage")
        rec.begin("B5", "Goodbye sample; Evoca is writing up the story")
        rec.pause(0.8)
        self.sample(3)
        rec.page.evaluate(SAMPLE_STEP_END_SCRIPT)
        goodbye = rec.device.locator(".device-controls button", has_text="Goodbye")
        if rec.device.locator('[data-tour="talk"] .device-talk-label.big').count() == 0 and goodbye.count():
            rec.pause(0.6)
            rec.click(goodbye)
            rec.notes.append("B5: the companion kept the session open after the goodbye sample; Goodbye was pressed")
        writing = rec.page.locator(".demo-archiving")
        rec.until(lambda: writing.count() > 0, "Evoca is writing up the story", timeout=30)
        rec.mark("writing")
        rec.point_at(writing, dwell=1.0)
        rec.wait_region("archivist", lambda: rec.until(lambda: writing.count() == 0, "the archivist",
                                                       timeout=ARCHIVIST_TIMEOUT_S, every=0.5))
        rec.pause(0.8)
        rec.end()

    # B6 ----------------------------------------------------------------------------------------
    def b6(self) -> None:
        rec = self.rec
        rec.begin("B6", "+1 day: the answer on Elif's phone, played")
        rec.pause(0.6)
        rec.click(rec.page.locator('button[data-tour="plus-day"]'))
        banner = rec.page.locator('[data-testid="answer-notice"] .answer-notice-body')
        rec.wait_region("clock", lambda: banner.wait_for(timeout=90_000))
        rec.mark("banner")
        rec.pause(0.8, keep=True)
        rec.click(banner)
        play = rec.phone.locator("button.answer-play").first
        rec.wait_region("loading", lambda: rec.until(lambda: play.get_attribute("data-state") == "ready", "the answer audio"))
        rec.pause(1.0)
        clicked = time.time()
        rec.click(play)
        rec.mark("play")
        # The answer may be several pieces played back to back: done when the card's own player
        # shows Play again and no audio has played for a moment.
        rec.until(lambda: rec.audio_started_since(clicked, "/api/"), "the answer to start")
        playing = lambda: rec.audio_playing() or play.get_attribute("aria-label") == "Pause the answer"
        rec.until(lambda: not playing(), "the answer to finish")
        rec.pause(0.6)
        rec.until(lambda: not playing(), "the answer to finish")
        rec.pause(0.8)
        rec.end()

    # B7 ----------------------------------------------------------------------------------------
    def b7(self) -> None:
        rec = self.rec
        rec.begin("B7", "Elif reacts with laugh and adds a photo")
        # The second reaction (😂); its title changes once pressed, so it is found by place.
        laugh = rec.phone.locator(".answer-card .answer-reactions button").nth(1)
        rec.click(laugh)
        rec.until(lambda: laugh.get_attribute("aria-pressed") == "true", "the laugh reaction")
        rec.pause(1.2)
        rec.click(rec.phone.locator("button.answer-open").first)
        add = rec.phone.get_by_role("button", name="Add a photo")
        rec.wait_region("loading", lambda: add.wait_for(timeout=30_000))
        rec.pause(0.8)
        rec.click(add)
        rec.pause(0.6)
        rec.phone.locator("#photo-file").set_input_files(str(PHOTO))
        rec.pause(0.5)
        rec.type_into(rec.phone.locator("#photo-caption"), PHOTO_CAPTION)
        rec.pause(0.5)
        save = rec.phone.get_by_role("button", name="Save the photo")
        rec.click(save)
        rec.wait_region("loading", lambda: rec.until(lambda: save.count() == 0, "the photo to be saved"))
        rec.pause(0.5)
        photo = rec.phone.locator("figure img").first
        rec.until(lambda: photo.count() > 0 and photo.is_visible(), "the photo on the story", timeout=30)
        rec.mark("photo")
        rec.point_at(photo, dwell=1.5)
        rec.end()

    # B8 ----------------------------------------------------------------------------------------
    def b8(self) -> None:
        rec = self.rec
        rec.begin("B8", "Next morning, Talk: Fatma hears that Elif laughed")
        rec.pause(0.6)
        rec.click(rec.page.locator('button[data-tour="next-morning"]'))
        reason = rec.device.locator(".device-reason", has_text="Elif")
        rec.wait_region("clock", lambda: reason.wait_for(timeout=60_000))
        rec.mark("light")
        rec.point_at(reason, dwell=1.4)
        clicked = time.time()
        rec.click(rec.device.locator('[data-tour="talk"]'))
        rec.wait_region("thinking", lambda: rec.until(lambda: rec.audio_started_since(clicked, "/api/"), "the opening"))
        rec.mark("opening")
        rec.wait_reply_done("the opening")
        rec.pause(0.6, keep=True)
        rec.end()
        goodbye = rec.device.locator(".device-controls button", has_text="Goodbye")
        if goodbye.count():
            goodbye.click()    # after the clip: close the session
        # Off camera: let the archivist finish, so B9 is not recorded on a busy machine.
        writing = rec.page.locator(".demo-archiving")
        rec.page.wait_for_timeout(4000)
        rec.until(lambda: writing.count() == 0, "the archivist", timeout=ARCHIVIST_TIMEOUT_S, every=0.5)

    # B9 ----------------------------------------------------------------------------------------
    def b9(self, browser: Any) -> None:
        """Exit demo on the stage, then "Create your family" in a fresh browser context: creating a
        family signs that browser in to it, so the demo family's context is left as it was. One
        step in two parts (two recordings); edit_demo.py joins them."""
        rec = self.rec
        rec.begin("B9", "Exit demo, then Create your family")
        rec.pause(0.6)
        rec.click(rec.page.get_by_role("button", name="Exit demo"))
        create = rec.page.get_by_role("button", name="Create your family").first
        rec.wait_region("loading", lambda: create.wait_for(timeout=30_000))
        rec.pause(0.5, keep=True)
        rec.end()
        # The demo family's pages are done: closing them ends their recordings (the files stay)
        # and frees the machine for the fresh browser.
        for c in list(rec.contexts):
            c.close()

        ctx = rec.new_context(browser)
        page = rec.open_page(ctx, "family", f"{WEB}/",
                             lambda p: p.get_by_role("button", name="Create your family").first.wait_for(timeout=60_000))
        rec.begin("B9", "Create your family: wizard, personal link, Getting started")
        rec.brisk = True
        rec.pause(0.3)
        rec.click(page.get_by_role("button", name="Create your family").first)
        field = lambda name: page.locator(f'[id="cf-{name}"]')
        submit = page.locator('[role="dialog"] button[type="submit"]')
        for n, names in enumerate((["circle_name"], ["center.name", "center.birth_year"],
                                   ["creator.name", "creator.birth_year", "creator.relation_to_center"])):
            field(names[0]).wait_for(timeout=10_000)
            rec.mark(f"wizard_{n + 1}")          # this wizard screen is on screen
            for name in names:
                rec.type_into(field(name), NEW_FAMILY[name])
            rec.click(submit, before=0.25)
        ready = page.get_by_role("heading", name="Your family is ready")
        rec.wait_region("loading", lambda: ready.wait_for(timeout=30_000))
        rec.mark("link")
        rec.point_at(page.locator('[role="dialog"] input').first, dwell=1.2)
        rec.click(page.get_by_role("button", name="Open my family"))
        started = page.locator('[data-testid="getting-started"]')
        rec.wait_region("loading", lambda: started.wait_for(timeout=30_000))
        rec.mark("journal")
        rec.point_at(started, dwell=1.4)
        rec.brisk = False
        rec.end()

    # Checks ------------------------------------------------------------------------------------
    def checks(self) -> dict[str, Any]:
        """What the run did, for the report: transcripts, the story, and the topic never reaching
        the device."""
        rec = self.rec
        out: dict[str, Any] = {}
        b4_end = next((s["end"] for s in rec.steps if s["id"] == "B4"), 0)
        device_after = [r for r in rec.responses if r["path"].startswith("/api/device/") and r["t"] >= b4_end]
        device_all = [r for r in rec.responses if r["path"].startswith("/api/device/")]
        leaked = [r["path"] for r in device_all if any(w in json.dumps(r["body"]).lower() for w in TOPIC_WORDS)]
        out["topic_on_device"] = {"device_responses_checked": len(device_all),
                                  "after_b4": len(device_after), "mentions": leaked}
        turns = []
        for r in rec.responses:
            if r["path"] in ("/api/device/session/start", "/api/device/turn"):
                b = r["body"]
                turns.append({"step": r["step"], "path": r["path"], "heard": b.get("heard_text"),
                              "reply": b.get("reply_text"), "tools": [t.get("tool") for t in b.get("trace", [])],
                              "cards": [c.get("type") for c in b.get("cards", [])]})
        out["turns"] = turns
        feed = self.http.get("/api/feed", headers=self.as_("elif")).json()
        answers = [i for i in feed.get("items", []) if i.get("type") == "question_answered"]
        if answers:
            story_id = answers[0]["answer"]["story_id"]
            story = self.http.get(f"/api/stories/{story_id}", headers=self.as_("fatma")).json()
            out["story"] = {k: story.get(k) for k in ("id", "title", "ai_summary", "transcript", "photo_url")}
            out["answer"] = answers[0]["answer"]
        if DEMO_DB.exists():
            with sqlite3.connect(f"file:{DEMO_DB}?mode=ro", uri=True) as db:
                rows = db.execute("SELECT text, status FROM question WHERE lower(text) LIKE '%hatice%'").fetchall()
            out["topic_questions_in_db"] = [{"text": t, "status": s} for t, s in rows]
        return out


def calibrate(video: Path, first_paint: float | None, created: float) -> tuple[float, str]:
    """The wall time of the video's frame 0. The page's first paint is the first frame that
    differs from the blank start; without one, the page's creation time."""
    if first_paint is None:
        return created, "page created (no paint entry)"
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    raw = subprocess.run([ffmpeg, "-v", "error", "-t", "30", "-i", str(video), "-vf", "scale=64:36,format=gray",
                          "-vsync", "passthrough", "-f", "rawvideo", "-"], capture_output=True).stdout
    probe = subprocess.run([ffmpeg, "-i", str(video)], capture_output=True, text=True, errors="replace").stderr
    fps = float((re.search(r"(\d+(?:\.\d+)?) fps", probe) or [None, "25"])[1])
    frame = 64 * 36
    means = [sum(raw[i:i + frame]) / frame for i in range(0, len(raw) - frame + 1, frame)]
    if not means:
        return created, "page created (no frames)"
    for i, m in enumerate(means):
        if abs(m - means[0]) > 2.0:
            return first_paint - i / fps, f"first paint at frame {i} ({i / fps:.2f} s)"
    return created, "page created (no change found)"


def write_timeline(rec: Recorder, checks: dict[str, Any]) -> None:
    def step_of(t: float) -> str | None:
        for s in rec.steps:
            if s["start"] <= t <= s["end"]:
                return s["id"]
        return None

    audio: list[dict[str, Any]] = []
    open_: dict[str, dict[str, Any]] = {}
    for e in sorted(rec.events, key=lambda e: e["t"]):
        if e["kind"] == "audio_start":
            src = e.get("src", "")
            local = rec.audio_files.get(src)
            if local is None and urlparse(src).path.startswith("/demo-audio/"):
                local = str(SAMPLES / Path(urlparse(src).path).name)
            item = {"place": e["place"], "step": step_of(e["t"]), "start": e["t"], "offset": e.get("pos", 0.0),
                    "url": src, "file": local, "frame": e.get("frame")}
            open_[e["id"]] = item
            audio.append(item)
        elif e["kind"] == "audio_pause_call" and e["id"] in open_:
            open_[e["id"]]["pause_call"] = e.get("stack")
        elif e["kind"] == "audio_stop" and e["id"] in open_:
            item = open_.pop(e["id"])
            item["end"] = e["t"]
            item["end_pos"] = e.get("pos")
            item["stopped_by"] = e.get("why")
    for item in open_.values():
        item["end"] = None

    clips = {}
    for place, info in rec.pages.items():
        clips[place] = {k: v for k, v in info.items() if k != "page"}
    data = {"clips": clips, "steps": rec.steps, "waits": rec.waits, "audio": audio,
            "responses": rec.responses, "checks": checks, "notes": rec.notes}
    (OUT / "timeline.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = []
    for s in rec.steps:
        lines.append(f"{s['id']} {s['what']}  [{s['place']}]  {s['end'] - s['start']:.1f} s")
        for a in audio:
            if a["step"] == s["id"]:
                length = f"{a['end'] - a['start']:.1f} s" if a.get("end") else "open"
                lines.append(f"   +{a['start'] - s['start']:6.2f} s  audio {length:>7}  {a['file'] or a['url']}")
        for name, t in s["markers"].items():
            lines.append(f"   +{t - s['start']:6.2f} s  marker {name}")
    lines.append("")
    lines += [f"note: {n}" for n in rec.notes]
    (OUT / "timeline.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the demo video's product part from a real run.")
    parser.add_argument("--headed", action="store_true", help="show the browser while recording")
    parser.add_argument("--until", default="B9", help="stop after this step (to try a part of the loop)")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    missing = [name for name, port in (("MCP server", 8000), ("backend", 8080), ("web client", 5173)) if not port_open(port)]
    if missing:
        print(f"Not running: {', '.join(missing)}. Start scripts/run_demo.py and (cd web && npm run dev) first.")
        return 1
    if not PHOTO.exists():
        print(f"Missing {PHOTO}")
        return 1

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "audio").mkdir(parents=True)
    video_tmp = OUT / "video_tmp"

    rec = Recorder(args.headed)
    demo = Demo(rec)
    # Start from a reset demo (the same call as "Reset demo"); its people have new ids.
    r = demo.http.post("/api/demo/reset")
    if r.status_code != 200:
        print(f"POST /api/demo/reset: HTTP {r.status_code} {r.text[:200]}")
        return 1
    demo.load_people()

    ok = False
    checks: dict[str, Any] = {}
    with sync_playwright() as p:
        # Muted, and deaf to the system's media keys and controls: twice a reply was paused half-way
        # with no pause() from the app. The sound is rebuilt from the files, so nothing is lost.
        browser = p.chromium.launch(headless=not args.headed,
                                    args=["--autoplay-policy=no-user-gesture-required", "--hide-scrollbars",
                                          "--mute-audio",
                                          "--disable-features=HardwareMediaKeyHandling,GlobalMediaControls,MediaSessionService"])
        ctx = rec.new_context(browser)
        try:
            rec.open_page(ctx, "stage", f"{WEB}/",
                          lambda p: p.get_by_role("button", name="Try the demo").first.wait_for(timeout=60_000))
            steps = [("B0", demo.b0), ("B1", demo.b1), ("B2", demo.b2), ("B3", demo.b3), ("B4", lambda: demo.b4(ctx)),
                     ("B5", demo.b5), ("B6", demo.b6), ("B7", demo.b7), ("B8", demo.b8),
                     ("B9", lambda: demo.b9(browser))]
            for step_id, run in steps:
                run()
                if step_id == args.until:
                    break
            rec.pause(1.0)
            ok = True
        except Exception as exc:
            rec.notes.append(f"FAILED in {rec.step and rec.step['id']}: {type(exc).__name__}: {exc}")
            print(f"FAILED: {exc}", flush=True)
            try:
                rec.page.screenshot(path=str(OUT / "failure.png"))
            except Exception:
                pass
            if rec.step is not None:
                rec.end()
        finally:
            videos = {place: info["page"].video for place, info in rec.pages.items()}
            for c in rec.contexts:
                c.close()
            browser.close()
        for place, video in videos.items():
            # The context is closed, so each recording is complete on disk.
            target = OUT / f"{place}.webm"
            shutil.move(video.path(), target)
            info = rec.pages[place]
            t0, how = calibrate(target, info.get("first_paint"), info["created"])
            info.update(file=target.name, t0=t0, t0_method=how)
        shutil.rmtree(video_tmp, ignore_errors=True)
    try:
        checks = demo.checks()
    except Exception as exc:
        rec.notes.append(f"checks failed: {type(exc).__name__}: {exc}")
    write_timeline(rec, checks)
    print(f"\n{'Recorded' if ok else 'Recording FAILED'}: {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
