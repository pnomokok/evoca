"""
Add the narration to the third product part of the demo video (after scripts/edit_demo_2.py --part 3).

    python scripts/narrate_demo.py <narration folder>

The narration files are numbered by their order in the video: B1 is the first caption in
data/video/product_part_3_full.srt, B2 the second, and so on (B1.mp3, B1.mp3.mpeg or B1.mpeg; all
MP3). Each file's words are checked against its caption (faster-whisper, the app's own model);
a file that does not match stops the run.

Each clip starts at its caption (or up to LEAD_S earlier, inside the crossfade into its step). It
never plays over the app's own voices (the companion, Fatma) or over another clip: if it would, it
starts up to MAX_LEAD_S earlier so it ends before that voice (moving the clips before it earlier too),
or else VOICE_GAP_S after the voice ends. A clip that would land more than MAX_LATE_S after its
caption stops the run; SKIP lists clips left out. The video and
its sound are left as they are; the narration is mixed on top.

Writes data/video/ (not committed): product_part_3_narrated.mp4 (captions burned in),
product_part_3_full_narrated.mp4 (no captions), and report_3/narration.json (the schedule).
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edit_demo as ed  # noqa: E402

REPO = ed.REPO
VIDEO = REPO / "data" / "video"
REPORT = VIDEO / "report_3"
SRT = VIDEO / "product_part_3_full.srt"
INPUTS = {"product_part_3.mp4": "product_part_3_narrated.mp4",
          "product_part_3_full.mp4": "product_part_3_full_narrated.mp4"}
LEAD_S = 0.25           # how much earlier than its caption a clip may start (half a crossfade)
VOICE_GAP_S = 0.2       # quiet kept between an app voice and a narration clip
CLIP_GAP_S = 0.15       # and between two narration clips
MATCH_MIN = 0.8         # word match between a file and its caption (punctuation ignored)
MAX_LATE_S = 1.5        # a clip pushed later than this, away from its screen, stops the run
MAX_LEAD_S = 1.2        # how much earlier than its caption a clip may start to end before an app voice
# Clips left out (by their number): B4, "A real conversation, with real follow-up questions", has no
# room between the app's own voices in B3; the conversation speaks for itself and its caption stays.
SKIP = {4}


def srt_captions() -> list[dict]:
    caps = []
    for block in SRT.read_text(encoding="utf-8").strip().split("\n\n"):
        lines = block.strip().split("\n")
        a, b = [ed_time(x.strip()) for x in lines[1].split("-->")]
        caps.append({"from": a, "to": b, "text": " ".join(lines[2:])})
    return caps


def ed_time(t: str) -> float:
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def narration_files(folder: Path) -> dict[int, Path]:
    files = {}
    for f in folder.iterdir():
        m = re.fullmatch(r"B(\d+)\.(mp3|mp3\.mpeg|mpeg)", f.name, re.I)
        if m:
            files[int(m[1])] = f
    return files


def words(text: str) -> list[str]:
    text = text.lower().replace("-", " ").replace("homepage", "home page")
    return re.sub(r"[^a-z0-9 ]", "", text).split()


def app_voices() -> list[tuple[float, float]]:
    """The app's own voices in the edited video, from edit_demo_2.py's report."""
    report = json.loads((REPORT / "edit.json").read_text(encoding="utf-8"))
    out = []
    for sid, step in report["steps"].items():
        for a in step["audio"]:
            start = report["starts"][sid] + a["at"]
            out.append((start, start + a["seconds"]))
    return sorted(out)


def pull_back(schedule: list[dict], start: float, clashes) -> bool:
    """Make room before `start`: move the clips before it earlier, each at most MAX_LEAD_S before its
    caption and still clear of the app's voices. False (and nothing moved) if they cannot move."""
    moved, limit = [], start - CLIP_GAP_S
    for s in reversed(schedule):
        if s["end"] <= limit:
            break
        t = limit - s["length"]
        if t < s["caption_from"] - MAX_LEAD_S or clashes(t, s["length"]):
            return False
        moved.append((s, t))
        limit = t - CLIP_GAP_S
    for s, t in moved:
        s["start"], s["end"] = t, t + s["length"]
    return True


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    if len(sys.argv) != 2:
        print(__doc__)
        return 1
    folder = Path(sys.argv[1])
    caps = srt_captions()
    files = narration_files(folder)
    missing = [n for n in range(1, len(caps) + 1) if n not in files]
    if missing:
        raise SystemExit(f"Missing narration files: {', '.join(f'B{n}' for n in missing)}")

    os.environ.setdefault("HF_HOME", str(REPO / "data" / "hf-cache"))
    from faster_whisper import WhisperModel
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    voices = app_voices()
    total = ed.duration_of(VIDEO / "product_part_3_full.mp4")

    def clashes(t: float, length: float) -> list[tuple[float, float]]:
        return [(a, b) for a, b in voices if a < t + length + VOICE_GAP_S and b + VOICE_GAP_S > t]

    schedule: list[dict] = []
    bad = []
    for n, cap in enumerate(caps, 1):
        f = files[n]
        heard = " ".join(s.text.strip() for s in model.transcribe(str(f), language="en", beam_size=5)[0])
        match = difflib.SequenceMatcher(None, words(heard), words(cap["text"])).ratio()
        if match < MATCH_MIN:
            bad.append(f"B{n} ({f.name}) says {heard!r}, its caption is {cap['text']!r}")
        if n in SKIP:
            print(f"B{n} left out: {cap['text']}")
            continue
        length = ed.duration_of(f)
        prev_end = schedule[-1]["end"] if schedule else 0.0
        t = max(cap["from"] - LEAD_S, prev_end + CLIP_GAP_S)
        if clashes(t, length):
            # First choice: earlier, to end before the app's next voice (up to MAX_LEAD_S before its
            # caption, moving the clips before it earlier too, each within its own limit).
            nxt = min(a for a, _ in clashes(t, length))
            early = nxt - VOICE_GAP_S - length
            if early >= cap["from"] - MAX_LEAD_S and not clashes(early, length) and pull_back(schedule, early, clashes):
                t = early
            else:
                # Otherwise after the voice it would play over.
                t = max(cap["from"], prev_end + CLIP_GAP_S)
                while clashes(t, length):
                    t = max(b for _, b in clashes(t, length)) + VOICE_GAP_S
        if t - cap["from"] > MAX_LATE_S:
            bad.append(f"B{n} ({f.name}) would start {t - cap['from']:.1f} s after its caption (app voices or the clip before)")
        if t + length > total:
            bad.append(f"B{n} ({f.name}) would end at {t + length:.2f} s, after the video ({total:.2f} s)")
        schedule.append({"n": n, "file": str(f), "caption": cap["text"], "heard": heard, "match": round(match, 2),
                         "caption_from": cap["from"], "start": t, "end": t + length, "length": length})
    if bad:
        raise SystemExit("Narration not added:\n  " + "\n  ".join(bad))
    for s in schedule:
        s.update(start=round(s["start"], 2), end=round(s["end"], 2), late_s=round(s["start"] - s["caption_from"], 2))

    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "narration.json").write_text(json.dumps(schedule, indent=2, ensure_ascii=False), encoding="utf-8")
    for s in schedule:
        print(f"B{s['n']:<2} {s['start']:7.2f}-{s['end']:7.2f} s  (caption {s['caption_from']:7.2f}, "
              f"{'+' if s['late_s'] >= 0 else ''}{s['late_s']:.2f} s)  {s['caption']}")

    for source, target in INPUTS.items():
        inputs = ["-i", str(VIDEO / source)]
        parts, labels = [], []
        for k, s in enumerate(schedule, 1):
            inputs += ["-i", s["file"]]
            delay = int(round(s["start"] * 1000))
            parts.append(f"[{k}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                         f"adelay={delay}|{delay}[n{k}]")
            labels.append(f"[n{k}]")
        parts.append("[0:a]" + "".join(labels) + f"amix=inputs={len(labels) + 1}:normalize=0:duration=first[aout]")
        ed.ffmpeg([*inputs, "-filter_complex", ";".join(parts), "-map", "0:v", "-map", "[aout]",
                   "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
                   str(VIDEO / target)])
        print(f"{target}: {ed.duration_of(VIDEO / target):.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
