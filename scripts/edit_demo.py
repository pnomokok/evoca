"""
Edit the recording of scripts/record_demo.py into the product part of the demo video.

    python scripts/edit_demo.py                # after record_demo.py; re-run after editing the captions
    python scripts/edit_demo.py --layout full  # the same cut full frame, captions as an .srt instead

Needs: pip install imageio-ffmpeg (ffmpeg comes with it; no system install) and Pillow.

Reads data/video/raw/ (timeline.json, the page recordings, the audio files) and
docs/video/captions.txt. Writes data/video/ (not committed):
  B1.mp4 ... B8.mp4     each step without captions, with its audio, for re-editing (Clipchamp)
  product_part.mp4      the steps joined, captions burned in (H.264, 1920x1080, 30 fps, AAC)
  report/               one frame per main step, and edit.json with each step's length
With --layout full instead of the two above:
  product_part_full.mp4 the same cut and audio, full frame, no caption band, no captions
  product_part_full.srt the captions, timed to it (for Clipchamp)

What the edit does, and nothing more:
- Cuts each step out of its page recording at the times the recorder logged.
  B9's form filling plays at 3x after each wizard screen's first 1.5 s.
  A step recorded in two parts (B9) is joined; a part listed in CUTS (B3's second exchange) is
  left out, never inside a voice.
- Waits (the companion thinking, the archivist, the clock moving, a page loading) play at 4x, and a
  long one keeps only its start and end (the middle is cut). A moment when any audio plays is never
  sped up or cut, with a margin around it.
- Rebuilds the audio from the logged timeline: every audio file the app played, placed where it
  started, at its real speed, with short fades. Nothing is replaced or added.
- Layout (captioned, the default): the recording at 88% on a dark background; captions (one font,
  white, at most two lines) in their own band below it, never over the app. Full: the recording as
  it is, and the captions in an .srt file.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
RAW = REPO / "data" / "video" / "raw"
OUT = REPO / "data" / "video"
REPORT = OUT / "report"
CAPTIONS = REPO / "docs" / "video" / "captions.txt"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

W, H, FPS = 1920, 1080, 30
SPEED = 4.0                 # waits play at most this fast
# Per kind of wait: (a shorter one plays as it was, the longest it may last on screen after the
# speed-up; the middle of a longer one is cut). "idle" is the recorder's own pause between actions.
WAIT_RULES = {"thinking": (0.8, 0.5), "archivist": (1.0, 1.2), "clock": (0.8, 0.4),
              "loading": (0.6, 0.4), "idle": (0.25, 0.06)}
AUDIO_MARGIN_S = (0.12, 0.2)   # never speed up or cut this close before / after a voice
AUDIO_FADE_S = (0.04, 0.12)
END_FADE_S = 0.35

FONT_CANDIDATES = [
    "C:/Windows/Fonts/seguisb.ttf",                         # Segoe UI Semibold
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
FONT_SIZE = 36
LINE_GAP = 2
TEXT_MAX_W = 1680
# The final video: the recording scaled to 88% on a dark background, with the captions in their
# own band below it, so a caption never covers the app. The step clips stay full frame.
APP_SCALE = 0.88
APP_W, APP_H = int(W * APP_SCALE) // 2 * 2, int(H * APP_SCALE) // 2 * 2
APP_X, APP_TOP = (W - APP_W) // 2, 14
BAND_Y = APP_TOP + APP_H                # the caption band: from below the app to the bottom
BAND_H = H - BAND_Y
BACKGROUND = "0x141110"

# Parts of a step left out of the edit, between two of its markers (recorded, but not shown).
# A cut never falls inside a voice: the edit stops if one would.
CUTS = {"B3": [("exchange_2", "exchange_2_end")]}   # sample answer 2 and the companion's reply

# Form filling played faster (B9's wizard): between each pair of markers, the first FORM_HOLD_S
# play as recorded (the new screen is readable), the rest (typing, mouse moves) at FORM_SPEED.
FORM_FILLING = {"B9": [("wizard_1", "wizard_2"), ("wizard_2", "wizard_3"), ("wizard_3", "link")]}
FORM_SPEED = 3.0
FORM_HOLD_S = 1.5

# The frames for the report: (file name, step, marker or None for the middle, seconds after it).
REPORT_FRAMES = [("B0", "B0", None, 0.0), ("B1", "B1", None, 0.0), ("B2", "B2", "light", 1.5),
                 ("B3", "B3", "trace", 2.0), ("B4", "B4", "answered", 1.5), ("B6", "B6", "play", 3.0),
                 ("B7", "B7", "photo", 1.0), ("B8", "B8", "opening", 3.0),
                 ("B9_link", "B9", "link", 1.0), ("B9", "B9", "journal", 1.2)]


def ffmpeg(args: list[str]) -> None:
    out = subprocess.run([FFMPEG, "-hide_banner", "-v", "error", "-y", *args],
                         capture_output=True, text=True, errors="replace")
    if out.returncode != 0:
        raise SystemExit(f"ffmpeg failed:\n{out.stderr[-3000:]}")


def duration_of(path: Path) -> float:
    probe = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True, text=True, errors="replace").stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", probe)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


# ---------------------------------------------------------------------------------------------
# Time: which parts of a step play at what speed
# ---------------------------------------------------------------------------------------------

@dataclass
class Segment:
    start: float       # wall clock
    end: float
    speed: float
    out: float = 0.0   # where it starts in the step's output


def subtract(span: tuple[float, float], holes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pieces = [span]
    for h0, h1 in holes:
        nxt = []
        for a, b in pieces:
            if h1 <= a or h0 >= b:
                nxt.append((a, b))
                continue
            if h0 > a:
                nxt.append((a, h0))
            if h1 < b:
                nxt.append((h1, b))
        pieces = nxt
    return [(a, b) for a, b in pieces if b - a > 1e-3]


def plan_step(step: dict[str, Any], waits: list[dict[str, Any]], audio: list[dict[str, Any]]) -> list[Segment]:
    s0, s1 = step["start"], step["end"]
    cuts = [(step["markers"][a], step["markers"][b]) for a, b in CUTS.get(step["id"], [])
            if a in step["markers"] and b in step["markers"]]
    for c0, c1 in cuts:
        for a in audio:
            a1 = a["end"] or s1
            if a["start"] < c1 and a1 > c0 and not (c0 <= a["start"] and a1 <= c1):
                raise SystemExit(f"{step['id']}: the cut {c0 - s0:.1f}-{c1 - s0:.1f} s would fall inside a voice ({a['file']})")
    voices = [(a["start"] - AUDIO_MARGIN_S[0], (a["end"] or s1) + AUDIO_MARGIN_S[1]) for a in audio]
    fast: list[tuple[float, float, str]] = []
    for w in waits:
        if w["place"] != step["place"] or w["end"] <= s0 or w["start"] >= s1:
            continue
        for a, b in subtract((max(w["start"], s0), min(w["end"], s1)), voices):
            if b - a >= WAIT_RULES.get(w["kind"], (1.0, 1.0))[0]:
                fast.append((a, b, w["kind"]))
    markers = {**wizard_markers(step, waits), **step["markers"]}
    for a, b in FORM_FILLING.get(step["id"], []):
        if a in markers and b in markers and markers[b] - markers[a] > FORM_HOLD_S:
            fast.append((markers[a] + FORM_HOLD_S, markers[b], "form"))
    fast.sort()
    # Merge overlapping waits (a loading inside a clock move).
    merged: list[list[Any]] = []
    for a, b, kind in fast:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b, kind])

    segments: list[Segment] = []
    t = s0
    for a, b, kind in merged:
        if a > t:
            segments.append(Segment(t, a, 1.0))
        if kind == "form":
            segments.append(Segment(a, b, FORM_SPEED))
            t = b
            continue
        cap = WAIT_RULES.get(kind, (1.0, 1.0))[1]
        if (b - a) / SPEED <= cap:
            segments.append(Segment(a, b, SPEED))
        else:
            keep = cap * SPEED / 2                    # wall seconds kept at each end
            segments.append(Segment(a, a + keep, SPEED))
            segments.append(Segment(b - keep, b, SPEED))
        t = b
    if s1 > t:
        segments.append(Segment(t, s1, 1.0))
    if cuts:
        kept = []
        for seg in segments:
            kept += [Segment(a, b, seg.speed) for a, b in subtract((seg.start, seg.end), cuts)]
        segments = kept
    out = 0.0
    for seg in segments:
        seg.out = out
        out += (seg.end - seg.start) / seg.speed
    return segments


def wizard_markers(step: dict[str, Any], waits: list[dict[str, Any]]) -> dict[str, float]:
    """When each wizard screen appeared, for a B9 recorded before the recorder logged it. Every
    click is preceded by a short logged pause; a field's click is followed at once by a second
    pause (before typing), a button's is not. The buttons, in order: Create your family, Next,
    Next. A screen appears as its button is released (about 0.1 s after the pause)."""
    if step["id"] != "B9" or "link" not in step["markers"] or "wizard_1" in step["markers"]:
        return {}
    pauses = sorted((w["start"], w["end"]) for w in waits if w["place"] == step["place"] and w["kind"] == "idle"
                    and step["start"] <= w["start"] < step["markers"]["link"] and w["end"] - w["start"] < 0.2)
    buttons, i = [], 0
    while i < len(pauses):
        end = pauses[i][1]
        if i + 1 < len(pauses) and pauses[i + 1][0] - end < 0.2:
            i += 2                    # a field: its click's pause, then the one before typing
        else:
            buttons.append(end)
            i += 1
    if len(buttons) < 3:
        return {}
    return {f"wizard_{k + 1}": end + 0.1 for k, end in enumerate(buttons[:3])}


def to_output(segments: list[Segment], wall: float) -> float | None:
    """Where a wall-clock moment lands in the step's output; None if it was cut."""
    for seg in segments:
        if seg.start - 1e-3 <= wall <= seg.end + 1e-3:
            return seg.out + (min(max(wall, seg.start), seg.end) - seg.start) / seg.speed
    return None


# ---------------------------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------------------------

def render_step(step: dict[str, Any], clip: dict[str, Any], segments: list[Segment],
                audio: list[dict[str, Any]], target: Path) -> dict[str, Any]:
    video = RAW / clip["file"]
    t0 = clip["t0"]
    length = segments[-1].out + (segments[-1].end - segments[-1].start) / segments[-1].speed
    inputs = ["-i", str(video)]
    parts = []
    for i, seg in enumerate(segments):
        parts.append(f"[0:v]trim=start={seg.start - t0:.3f}:end={seg.end - t0:.3f},"
                     f"setpts=(PTS-STARTPTS)/{seg.speed}[v{i}]")
    parts.append("".join(f"[v{i}]" for i in range(len(segments)))
                 + f"concat=n={len(segments)}:v=1:a=0,fps={FPS},scale={W}:{H},format=yuv420p[vout]")

    placed = []
    labels = []
    for a in audio:
        start = to_output(segments, a["start"])
        end_wall = min(a["end"] or step["end"], step["end"])
        dur = end_wall - a["start"]
        if start is None or dur <= 0.05 or not a.get("file"):
            continue
        path = Path(a["file"]) if Path(a["file"]).is_absolute() else RAW / a["file"]
        k = len(placed) + 1
        inputs += ["-i", str(path)]
        fade_out = min(AUDIO_FADE_S[1], dur / 3)
        delay = int(round(start * 1000))
        parts.append(f"[{k}:a]atrim=start={a['offset']:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS,"
                     f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"afade=t=in:d={AUDIO_FADE_S[0]},afade=t=out:st={dur - fade_out:.3f}:d={fade_out:.3f},"
                     f"adelay={delay}|{delay}[a{k}]")
        labels.append(f"[a{k}]")
        placed.append({"file": a["file"], "at": round(start, 2), "seconds": round(dur, 2)})
    silence = f"anullsrc=r=48000:cl=stereo,atrim=duration={length:.3f}[sil]"
    parts.append(silence)
    parts.append("[sil]" + "".join(labels) + f"amix=inputs={len(labels) + 1}:normalize=0:duration=first[aout]")

    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "filter.txt"
        script.write_text(";\n".join(parts), encoding="utf-8")
        ffmpeg([*inputs, "-filter_complex_script", str(script), "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", str(FPS),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{length:.3f}",
                "-movflags", "+faststart", str(target)])
    return {"seconds": round(duration_of(target), 2), "audio": placed,
            "sped_up": [{"kind": "wait", "wall_s": round(s.end - s.start, 1)} for s in segments if s.speed > 1]}


def find_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    raise SystemExit(f"No caption font found; tried {FONT_CANDIDATES}")


def wrap(text: str, font: ImageFont.FreeTypeFont) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and font.getlength(f"{lines[-1]} {word}") <= TEXT_MAX_W:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    if len(lines) > 2:
        raise SystemExit(f"Caption longer than two lines: {text!r}")
    # Two lines of balanced length read better than one long and one short.
    if len(lines) == 2:
        words = text.split()
        best = min(range(1, len(words)), key=lambda i: abs(font.getlength(" ".join(words[:i])) - font.getlength(" ".join(words[i:]))))
        a, b = " ".join(words[:best]), " ".join(words[best:])
        if max(font.getlength(a), font.getlength(b)) <= TEXT_MAX_W:
            lines = [a, b]
    return lines


def caption_png(text: str, font_path: str, target: Path) -> None:
    font = ImageFont.truetype(font_path, FONT_SIZE)
    lines = wrap(text, font)
    img = Image.new("RGBA", (W, BAND_H), (0, 0, 0, 0))     # the band itself is the dark background
    draw = ImageDraw.Draw(img)
    line_h = int(FONT_SIZE * 1.22)
    total = len(lines) * line_h + (len(lines) - 1) * LINE_GAP
    y = (BAND_H - total) / 2 - 2
    for line in lines:
        x = (W - font.getlength(line)) / 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_h + LINE_GAP
    img.save(target)


def read_captions() -> list[tuple[str, str, str]]:
    """(step, when, text); when is '' (the step's start), a marker name or seconds."""
    items = []
    for raw in CAPTIONS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(B\d)(?:@([\w.]+))?\s*:\s*(.+)$", line)
        if not m:
            raise SystemExit(f"Cannot read caption line: {raw!r}")
        items.append((m[1], m[2] or "", m[3].strip()))
    return items


# ---------------------------------------------------------------------------------------------

def srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Edit the recorded demo into the product part.")
    parser.add_argument("--layout", choices=["captioned", "full"], default="captioned",
                        help="captioned: 88%% with a caption band (product_part.mp4); "
                             "full: full frame, captions as .srt (product_part_full.mp4)")
    args = parser.parse_args()
    full = args.layout == "full"
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    timeline = json.loads((RAW / "timeline.json").read_text(encoding="utf-8"))
    REPORT.mkdir(parents=True, exist_ok=True)
    font = find_font()

    report: dict[str, Any] = {"steps": {}}
    starts: dict[str, float] = {}
    # Per step, its parts: (the recorded part, its segments, where it starts in the step's clip).
    # A step is usually one part; B9 has two (the stage, then a fresh browser).
    plans: dict[str, list[tuple[dict[str, Any], list[Segment], float]]] = {}
    files: list[Path] = []
    offset = 0.0
    order = list(dict.fromkeys(s["id"] for s in timeline["steps"]))
    for sid in order:
        parts = [s for s in timeline["steps"] if s["id"] == sid]
        target = OUT / f"{sid}.mp4"
        infos, part_files, plans[sid], local = [], [], [], 0.0
        for k, step in enumerate(parts):
            clip = timeline["clips"][step["place"]]
            audio = [a for a in timeline["audio"] if a["step"] == sid and a["place"] == step["place"]
                     and step["start"] <= a["start"] <= step["end"]]
            segments = plan_step(step, timeline["waits"], audio)
            part_file = target if len(parts) == 1 else OUT / f"{sid}_part{k + 1}.mp4"
            info = render_step(step, clip, segments, audio, part_file)
            plans[sid].append((step, segments, local))
            local += info["seconds"]
            infos.append(info)
            part_files.append(part_file)
        if len(parts) > 1:
            listing = OUT / f"{sid}_parts.txt"
            listing.write_text("".join(f"file '{f.name}'\n" for f in part_files), encoding="utf-8")
            ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(target)])
            for f in [listing, *part_files]:
                f.unlink()
        info = {"seconds": round(duration_of(target), 2), "audio": [a for i in infos for a in i["audio"]],
                "sped_up": [w for i in infos for w in i["sped_up"]],
                "recorded_s": round(sum(s["end"] - s["start"] for s in parts), 1)}
        report["steps"][sid] = info
        starts[sid] = offset
        offset += info["seconds"]
        files.append(target)
        print(f"{sid}: {info['seconds']:6.2f} s (recorded {info['recorded_s']} s), audio {len(info['audio'])}", flush=True)

    def marker_at(sid: str, name: str) -> float | None:
        """Where a step's marker lands in that step's clip; None if missing or cut."""
        for step, segments, local in plans.get(sid, []):
            if name in step["markers"]:
                at = to_output(segments, step["markers"][name])
                return None if at is None else local + at
        return None

    # Captions: each from its marker (or the step's start) to the next caption or the step's end.
    caps = []
    for sid, when, text in read_captions():
        if sid not in plans:
            print(f"Caption for {sid} skipped: no such step in the recording")
            continue
        if not when:
            at = 0.0
        elif re.fullmatch(r"\d+(\.\d+)?", when):
            at = float(when)
        else:
            local = marker_at(sid, when)
            if local is None:
                raise SystemExit(f"Caption {sid}@{when}: no such marker in the recording")
            at = local
        caps.append([sid, starts[sid] + at, text])
    caps.sort(key=lambda c: c[1])
    with tempfile.TemporaryDirectory() as tmp:
        inputs: list[str] = []
        for f in files:
            inputs += ["-i", str(f)]
        n = len(files)
        parts = ["".join(f"[{i}:v][{i}:a]" for i in range(n)) + f"concat=n={n}:v=1:a=1[cv][ca]"]
        last = "cv"
        if not full:
            parts.append(f"[cv]scale={APP_W}:{APP_H}:flags=lanczos,pad={W}:{H}:{APP_X}:{APP_TOP}:color={BACKGROUND}[app]")
            last = "app"
        timed = []
        for i, (sid, start, text) in enumerate(caps):
            same_step_next = [c[1] for c in caps[i + 1:] if c[0] == sid]
            end = same_step_next[0] if same_step_next else starts[sid] + report["steps"][sid]["seconds"]
            timed.append({"step": sid, "from": round(start, 2), "to": round(end, 2), "text": text})
            if full:
                continue
            png = Path(tmp) / f"cap{i}.png"
            caption_png(text, font, png)
            k = n + i
            dur = end - start
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(png)]
            parts.append(f"[{k}:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1,"
                         f"fade=t=out:st={max(0.0, dur - 0.25):.3f}:d=0.25:alpha=1,setpts=PTS-STARTPTS+{start:.3f}/TB[c{i}]")
            parts.append(f"[{last}][c{i}]overlay=0:{BAND_Y}:eof_action=pass:repeatlast=0[o{i}]")
            last = f"o{i}"
        total = offset
        parts.append(f"[{last}]fade=t=in:d={END_FADE_S},fade=t=out:st={total - END_FADE_S:.3f}:d={END_FADE_S},format=yuv420p[vout]")
        parts.append(f"[ca]afade=t=in:d={END_FADE_S},afade=t=out:st={total - END_FADE_S:.3f}:d={END_FADE_S}[aout]")
        script = Path(tmp) / "filter.txt"
        script.write_text(";\n".join(parts), encoding="utf-8")
        product = OUT / ("product_part_full.mp4" if full else "product_part.mp4")
        ffmpeg([*inputs, "-filter_complex_script", str(script), "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", str(FPS),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(product)])
    total_s = round(duration_of(product), 2)
    if full:
        # The captions as SubRip, wrapped as on screen (at most two lines).
        caption_font = ImageFont.truetype(font, FONT_SIZE)
        srt = OUT / "product_part_full.srt"
        srt.write_text("".join(f"{i}\n{srt_time(c['from'])} --> {srt_time(c['to'])}\n{chr(10).join(wrap(c['text'], caption_font))}\n\n"
                               for i, c in enumerate(timed, 1)), encoding="utf-8")
        m, s = divmod(total_s, 60)
        print(f"\nproduct_part_full.mp4: {int(m)}:{s:05.2f}  ({product})\n{srt.name}: {len(timed)} captions")
        return 0
    report["captions"] = timed
    report["total_s"] = total_s

    frames = []
    for name, sid, marker, after in REPORT_FRAMES:
        if sid not in starts:
            continue
        local = marker_at(sid, marker) if marker else None
        at = starts[sid] + (local + after if local is not None else report["steps"][sid]["seconds"] / 2)
        target = REPORT / f"frame_{name}.png"
        ffmpeg(["-ss", f"{at:.2f}", "-i", str(product), "-frames:v", "1", str(target)])
        frames.append({"step": sid, "at": round(at, 2), "file": str(target.relative_to(REPO))})
    report["frames"] = frames
    (REPORT / "edit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    m, s = divmod(report["total_s"], 60)
    print(f"\nproduct_part.mp4: {int(m)}:{s:05.2f}  ({product})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
