"""
Edit the recording of `scripts/record_demo.py --part 2` into the second product part of the demo
video (2:05-2:15).

    python scripts/edit_demo_2.py          # after record_demo.py --part 2; re-run after editing the captions
    python scripts/edit_demo_2.py --part 3 # the third product part (raw_3, captions_3.txt, product_part_3*)

Needs what scripts/edit_demo.py needs (imageio-ffmpeg, Pillow); it reuses its cutting and audio.

Reads data/video/raw_2/ and docs/video/captions_2.txt. Writes data/video/ (not committed):
  part_2/B*.mp4               each step, without captions, with its audio
  product_part_2_full.mp4     the steps joined with 0.4 s crossfades, three gentle zooms, no captions
  product_part_2_full.srt     the captions, timed to it
  product_part_2.mp4          the same with the captions burned in
  report_2/                   frames for the report, and edit.json with each step's length

What the edit does beyond edit_demo.py (cuts, sped-up waits, the audio rebuilt from the files):
- The steps in the video's order (ORDER), joined with crossfades instead of hard cuts.
- B6's answer: its first 6 s of her voice, then a 1 s fade-out; the step ends there.
- A zoom of about 1.15x, eased in and out, on the MCP panel (B3), the answer banner (B6) and Fatma's
  life chapters (end of B12), centred on where the recorder saw them.
- --part 3: 0.5 s crossfades (0.6 s out of B8), waits at most 3x, no MCP panel zoom but a slow
  one on B4's sensitive topics; B8 ends after the companion's first sentence with a 1.5 s fade.
- Captions full frame at the bottom centre: orange semi-bold with a dark outline and a soft shadow,
  so they read on light and dark screens; lifted (LIFT) where they would cover the device's Talk
  button or a toast.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import edit_demo as ed  # noqa: E402

REPO = ed.REPO
RAW = REPO / "data" / "video" / "raw_2"
OUT = REPO / "data" / "video"
CLIPS = OUT / "part_2"
REPORT = OUT / "report_2"
CAPTIONS = REPO / "docs" / "video" / "captions_2.txt"
W, H, FPS = ed.W, ed.H, ed.FPS

ORDER = ["B0", "B1", "B2", "B3", "B5", "B6", "B7", "B8", "B4", "B10", "B11", "B9", "B12"]
XFADE_S = 0.4

# A step that ends a set time after one of its markers: (marker, seconds). The audio is cut there
# with FADE_OUT_S of fade-out (a voice is trimmed, never edited).
# B6: her first 6 s, then 1 s of fade. B8: the companion's first sentence ("Elif laughed at your
# story about ..."), faded out in the pause before its next one.
STEP_END = {"B6": ("voice", 7.0), "B8": ("opening", 5.3)}
FADE_OUT_S = {"B6": 1.0, "B8": 0.3}

# Zooms: (step, box the recorder noted, from marker, seconds after it to start, seconds it holds
# or None to the step's end).
ZOOM = 1.15
ZOOM_RAMP_S = 0.6
ZOOMS = [("B3", "trace", "trace", 0.2, 3.6), ("B6", "banner", "banner", 0.0, 1.8),
         ("B12", "chapters", "fatma_end", 0.0, None)]

# Captions: Segoe UI Semibold 44 px, #FF7B22, 2 px #2B1A10 outline, a soft dark shadow.
FONT_SIZE = 44
TEXT_MAX_W = 1500
FILL = (0xFF, 0x7B, 0x22, 255)
OUTLINE = (0x2B, 0x1A, 0x10, 255)
BOTTOM_MARGIN = 54
BAND_H = 220
# Pixels a step's caption moves up (over the device's Talk button, or a toast).
LIFT: dict[str, int] = {"B5": 70}     # B5: the "Goodbye! Today's memories are being saved" toast

# Report frames: (name, step, marker or None for the middle, seconds after it).
# --part 3 replaces some of the above (configure()).
PART_3 = {
    # The film goes on after B9: it ends on the new family's journal (Getting started), with no fade.
    "order": ["B0", "B1", "B2", "B3", "B5", "B6", "B7", "B8", "B4", "B10", "B11", "B12", "B9"],
    "end_fade_out": False,
    "raw": "raw_3", "clips": "part_3", "report": "report_3", "captions": "captions_3.txt", "out": "product_part_3",
    "xfade": 0.5, "xfade_after": {"B8": 0.6}, "speed": 3.0,
    # Each step ends once its last screen has been on screen long enough (at least 2 s at normal
    # speed, before the crossfade starts).
    "step_end": {"B6": ("voice", 7.0), "B4": ("answered", 2.4), "B5": ("idle", 2.4), "B7": ("photo", 2.6),
                 "B10": ("tag", 2.6), "B12": ("elif", 2.4), "B9": ("journal", 2.4)},
    "fade_out": {"B6": 1.0, "B8": 1.5},
    # B9 starts on the landing page with "Create your family" (its first part, Exit demo, is left out).
    "skip_parts": {"B9": [0]},
    "zooms": [("B4", "topics", "topic", 0.3, 3.0), ("B6", "banner", "banner", 0.0, 1.8),
              ("B12", "chapters", "fatma", 0.2, 0.6)],
    "zoom_ramp": 1.0,
    "frames": [("B2", "B2", "light", 1.5), ("B4", "B4", "topic", 2.2), ("B5_idle", "B5", "idle", 1.2),
               ("B6", "B6", "banner", 1.0), ("B8", "B8", "opening", 2.0), ("B12", "B12", "fatma", 1.6),
               ("B12_scroll", "B12", "story", -1.0), ("B12_elif", "B12", "elif", 1.5),
               ("B9_end", "B9", "journal", 2.35)],
}
OUT_NAME = "product_part_2"
XFADE_AFTER: dict[str, float] = {}
SKIP_PARTS: dict[str, list[int]] = {}
END_FADE_OUT = True
# B8 in part 3: the step ends this long after the companion's first sentence (its first pause).
SENTENCE_FADE = {}

REPORT_FRAMES = [("B3", "B3", "trace", 2.0), ("B6", "B6", "banner", 1.0), ("B6_play", "B6", "voice", 2.5),
                 ("B10", "B10", "tag", 0.8), ("B11", "B11", "recording", 1.5),
                 ("B12_elif", "B12", "elif", 1.0), ("B12", "B12", "fatma_end", 1.5)]


def configure(part: int) -> None:
    global RAW, CLIPS, REPORT, CAPTIONS, XFADE_S, STEP_END, FADE_OUT_S, ZOOMS, ZOOM_RAMP_S, REPORT_FRAMES, OUT_NAME
    global XFADE_AFTER, SENTENCE_FADE, SKIP_PARTS, ORDER, END_FADE_OUT
    if part != 3:
        return
    c = PART_3
    RAW, CLIPS, REPORT = REPO / "data" / "video" / c["raw"], OUT / c["clips"], OUT / c["report"]
    CAPTIONS = REPO / "docs" / "video" / c["captions"]
    OUT_NAME, XFADE_S, XFADE_AFTER = c["out"], c["xfade"], c["xfade_after"]
    STEP_END, FADE_OUT_S, ZOOMS, ZOOM_RAMP_S = c["step_end"], c["fade_out"], c["zooms"], c["zoom_ramp"]
    REPORT_FRAMES = c["frames"]
    SENTENCE_FADE = {"B8": 1.5}
    SKIP_PARTS = c["skip_parts"]
    ORDER, END_FADE_OUT = c["order"], c["end_fade_out"]
    # B4: the topics section is at the bottom of Family settings, so its caption sits above it.
    LIFT["B4"] = 160
    ed.SPEED = c["speed"]
    # Long waits keep less of their start and end on screen (the companion thinking, the archivist).
    ed.WAIT_RULES = {**ed.WAIT_RULES, "thinking": (0.8, 0.3), "archivist": (1.0, 0.6)}


def first_pause(path: Path, after: float = 2.5) -> float | None:
    """Where the first pause (0.3 s of quiet) after `after` seconds starts in an audio file."""
    err = subprocess.run([ed.FFMPEG, "-hide_banner", "-i", str(path), "-af", "silencedetect=n=-35dB:d=0.3",
                          "-f", "null", "-"], capture_output=True, text=True, errors="replace").stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    return next((t for t in starts if t > after), None)


def read_captions() -> list[tuple[str, str, str]]:
    items = []
    for raw in CAPTIONS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^(B\d+)(?:@([\w.]+))?\s*:\s*(.+)$", line)
        if not m:
            raise SystemExit(f"Cannot read caption line: {raw!r}")
        items.append((m[1], m[2] or "", m[3].strip()))
    return items


def caption_png(text: str, font_path: str, target: Path) -> None:
    font = ImageFont.truetype(font_path, FONT_SIZE)
    lines = ed.wrap(text, font)
    line_h = int(FONT_SIZE * 1.25)
    y = BAND_H - BOTTOM_MARGIN - len(lines) * line_h
    shadow = Image.new("RGBA", (W, BAND_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    text_layer = Image.new("RGBA", (W, BAND_H), (0, 0, 0, 0))
    td = ImageDraw.Draw(text_layer)
    for i, line in enumerate(lines):
        x = (W - font.getlength(line)) / 2
        ly = y + i * line_h
        sd.text((x, ly + 3), line, font=font, fill=(0, 0, 0, 170), stroke_width=6, stroke_fill=(0, 0, 0, 170))
        td.text((x, ly), line, font=font, fill=FILL, stroke_width=2, stroke_fill=OUTLINE)
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    Image.alpha_composite(shadow, text_layer).save(target)


def zoom_filter(step: dict[str, Any], segments: list[ed.Segment], length: float) -> str:
    """A zoompan for the step's clip ("" when it has no zoom)."""
    for sid, box_name, marker, after, hold in ZOOMS:
        if sid != step["id"]:
            continue
        box = step.get("boxes", {}).get(box_name)
        at = ed.to_output(segments, step["markers"].get(marker, 0)) if marker in step["markers"] else None
        if box is None or at is None:
            print(f"{sid}: no zoom ({box_name} or {marker} missing)")
            return ""
        cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        a = at + after
        b = length + 10 if hold is None else a + ZOOM_RAMP_S + hold + ZOOM_RAMP_S
        t = f"(on/{FPS})"
        r = f"(clip(({t}-{a:.3f})/{ZOOM_RAMP_S},0,1)*clip(({b:.3f}-{t})/{ZOOM_RAMP_S},0,1))"
        z = f"(1+{ZOOM - 1:.3f}*{r}*{r}*(3-2*{r}))"
        x = f"clip({cx:.1f}-iw/zoom/2,0,iw-iw/zoom)"
        y = f"clip({cy:.1f}-ih/zoom/2,0,ih-ih/zoom)"
        return f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={FPS},"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Edit the second (or third) product part.")
    parser.add_argument("--part", type=int, choices=[2, 3], default=2)
    configure(parser.parse_args().part)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    ed.RAW = RAW
    ed.TEXT_MAX_W = TEXT_MAX_W
    timeline = json.loads((RAW / "timeline.json").read_text(encoding="utf-8"))
    CLIPS.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    font = ed.find_font()

    report: dict[str, Any] = {"steps": {}}
    plans: dict[str, list[tuple[dict[str, Any], list[ed.Segment], float]]] = {}
    files: list[Path] = []
    order = [sid for sid in ORDER if any(s["id"] == sid for s in timeline["steps"])]
    missing = [sid for sid in ORDER if sid not in order]
    for sid in order:
        parts = [dict(s) for k, s in enumerate(x for x in timeline["steps"] if x["id"] == sid)
                 if k not in SKIP_PARTS.get(sid, [])]
        target = CLIPS / f"{sid}.mp4"
        infos, part_files, plans[sid], local = [], [], [], 0.0
        for k, step in enumerate(parts):
            if sid in STEP_END and STEP_END[sid][0] in step["markers"]:
                marker, after = STEP_END[sid]
                step["end"] = min(step["end"], step["markers"][marker] + after)
            if sid in SENTENCE_FADE:
                voice = next((a for a in timeline["audio"] if a["step"] == sid and a.get("file")), None)
                if voice:
                    path = Path(voice["file"]) if Path(voice["file"]).is_absolute() else RAW / voice["file"]
                    pause = first_pause(path)
                    if pause is not None:
                        step["end"] = min(step["end"], voice["start"] + pause + SENTENCE_FADE[sid])
                        print(f"{sid}: the first sentence ends at {pause:.2f} s of the voice; then {SENTENCE_FADE[sid]} s of fade")
            clip = timeline["clips"][step["place"]]
            audio = [a for a in timeline["audio"] if a["step"] == sid and a["place"] == step["place"]
                     and step["start"] <= a["start"] <= step["end"]]
            segments = ed.plan_step(step, timeline["waits"], audio)
            part_file = target if len(parts) == 1 else CLIPS / f"{sid}_part{k + 1}.mp4"
            ed.AUDIO_FADE_S = (0.04, FADE_OUT_S.get(sid, 0.12))
            info = ed.render_step(step, clip, segments, audio, part_file)
            plans[sid].append((step, segments, local))
            local += info["seconds"]
            infos.append(info)
            part_files.append(part_file)
        if len(parts) > 1:
            listing = CLIPS / f"{sid}_parts.txt"
            listing.write_text("".join(f"file '{f.name}'\n" for f in part_files), encoding="utf-8")
            ed.ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart", str(target)])
            for f in [listing, *part_files]:
                f.unlink()
        info = {"seconds": round(ed.duration_of(target), 2), "audio": [a for i in infos for a in i["audio"]],
                "recorded_s": round(sum(s["end"] - s["start"] for s in parts), 1)}
        report["steps"][sid] = info
        files.append(target)
        print(f"{sid}: {info['seconds']:6.2f} s (recorded {info['recorded_s']} s), audio {len(info['audio'])}", flush=True)

    # Where each step starts in the joined video: each crossfade overlaps two steps by XFADE_S.
    xf = [XFADE_AFTER.get(sid, XFADE_S) for sid in order[:-1]]    # the crossfade after each step
    starts: dict[str, float] = {}
    t = 0.0
    for i, sid in enumerate(order):
        starts[sid] = t
        if i < len(xf):
            t += report["steps"][sid]["seconds"] - xf[i]
    total = t + report["steps"][order[-1]]["seconds"]

    def marker_at(sid: str, name: str) -> float | None:
        for step, segments, local in plans.get(sid, []):
            if name in step["markers"]:
                at = ed.to_output(segments, step["markers"][name])
                return None if at is None else local + at
        return None

    # The joined video: zooms, crossfades (picture and sound), fade in and out at the ends. One
    # graph with every clip ran out of memory (xfade holds the later clips until their turn), so
    # the pieces are made one by one (each clip's middle, each 0.4 s crossfade) and then joined
    # in order. Pieces are near-lossless with plain PCM audio, so the joins are seamless.
    full = OUT / f"{OUT_NAME}_full.mp4"

    def end_fade(name: str) -> str:
        return f"{name}=t=out:st={total - ed.END_FADE_S:.3f}:d={ed.END_FADE_S}," if END_FADE_OUT else ""

    lengths = [report["steps"][sid]["seconds"] for sid in order]
    piece_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "10", "-r", str(FPS), "-pix_fmt", "yuv420p",
                  "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]
    with tempfile.TemporaryDirectory() as tmp:
        sources = []
        for i, (sid, f) in enumerate(zip(order, files)):
            step, segments, _ = plans[sid][-1]
            zoom = zoom_filter(step, segments, lengths[i]) if len(plans[sid]) == 1 else ""
            if zoom:
                zoomed = Path(tmp) / f"zoom_{sid}.mkv"
                ed.ffmpeg(["-i", str(f), "-vf", f"{zoom}format=yuv420p", *piece_args, str(zoomed)])
                f = zoomed
            sources.append(f)
        pieces = []
        for i, f in enumerate(sources):
            a = xf[i - 1] if i > 0 else 0.0
            b = lengths[i] - xf[i] if i < len(sources) - 1 else lengths[i]
            mid = Path(tmp) / f"p{i:02d}_mid.mkv"
            ed.ffmpeg(["-i", str(f), "-filter_complex",
                       f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS,fps={FPS}[v];"
                       f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,aresample=48000[a]",
                       "-map", "[v]", "-map", "[a]", *piece_args, str(mid)])
            pieces.append(mid)
            if i == len(sources) - 1:
                break
            nxt = sources[i + 1]
            cross = Path(tmp) / f"p{i:02d}_x.mkv"
            d = xf[i]
            ed.ffmpeg(["-ss", f"{lengths[i] - d:.3f}", "-i", str(f), "-t", f"{d:.3f}", "-i", str(nxt),
                       "-filter_complex",
                       f"[0:v]trim=duration={d},setpts=PTS-STARTPTS,fps={FPS},settb=AVTB[v0];"
                       f"[1:v]trim=duration={d},setpts=PTS-STARTPTS,fps={FPS},settb=AVTB[v1];"
                       f"[v0][v1]xfade=transition=fade:duration={d - 1 / FPS:.3f}:offset=0[v];"
                       f"[0:a]atrim=duration={d},asetpts=PTS-STARTPTS,aresample=48000,afade=t=out:d={d}[a0];"
                       f"[1:a]atrim=duration={d},asetpts=PTS-STARTPTS,aresample=48000,afade=t=in:d={d}[a1];"
                       f"[a0][a1]amix=inputs=2:normalize=0:duration=longest[a]",
                       "-map", "[v]", "-map", "[a]", "-t", f"{d:.3f}", *piece_args, str(cross)])
            pieces.append(cross)
        listing = Path(tmp) / "pieces.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces), encoding="utf-8")
        ed.ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing),
                   "-vf", f"fade=t=in:d={ed.END_FADE_S}," + end_fade("fade") + "format=yuv420p",
                   "-af", f"afade=t=in:d={ed.END_FADE_S}" + ("," + end_fade("afade")).rstrip(","),
                   "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", str(FPS),
                   "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(full)])

    # Captions: each from its marker (or the middle of the crossfade into its step) to the next
    # caption of the same step, or the middle of the crossfade out of it.
    caps = []
    for sid, when, text in read_captions():
        if sid not in plans:
            print(f"Caption for {sid} skipped: no such step in the recording")
            continue
        if not when:
            at = xf[order.index(sid) - 1] / 2 if sid != order[0] else 0.0
        elif re.fullmatch(r"\d+(\.\d+)?", when):
            at = float(when)
        else:
            local = marker_at(sid, when)
            if local is None:
                raise SystemExit(f"Caption {sid}@{when}: no such marker in the recording")
            at = local
        caps.append([sid, starts[sid] + at, text])
    caps.sort(key=lambda c: c[1])
    timed = []
    for i, (sid, start, text) in enumerate(caps):
        same = [c[1] for c in caps[i + 1:] if c[0] == sid]
        k = order.index(sid)
        end = same[0] if same else min(total, starts[sid] + report["steps"][sid]["seconds"] - (xf[k] / 2 if k < len(xf) else 0))
        timed.append({"step": sid, "from": round(start, 2), "to": round(end, 2), "text": text})
    caption_font = ImageFont.truetype(font, FONT_SIZE)
    srt = OUT / f"{OUT_NAME}_full.srt"
    srt.write_text("".join(f"{i}\n{ed.srt_time(c['from'])} --> {ed.srt_time(c['to'])}\n{chr(10).join(ed.wrap(c['text'], caption_font))}\n\n"
                           for i, c in enumerate(timed, 1)), encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        inputs = ["-i", str(full)]
        parts = []
        last = "0:v"
        for i, c in enumerate(timed):
            png = Path(tmp) / f"cap{i}.png"
            caption_png(c["text"], font, png)
            dur = c["to"] - c["from"]
            inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(png)]
            parts.append(f"[{i + 1}:v]format=rgba,fade=t=in:st=0:d=0.25:alpha=1,"
                         f"fade=t=out:st={max(0.0, dur - 0.25):.3f}:d=0.25:alpha=1,setpts=PTS-STARTPTS+{c['from']:.3f}/TB[c{i}]")
            parts.append(f"[{last}][c{i}]overlay=0:{H - BAND_H - LIFT.get(c['step'], 0)}:eof_action=pass:repeatlast=0[o{i}]")
            last = f"o{i}"
        parts.append(f"[{last}]format=yuv420p[vout]")
        script = Path(tmp) / "filter.txt"
        script.write_text(";\n".join(parts), encoding="utf-8")
        product = OUT / f"{OUT_NAME}.mp4"
        ed.ffmpeg([*inputs, "-filter_complex_script", str(script), "-map", "[vout]", "-map", "0:a",
                   "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", str(FPS), "-c:a", "copy",
                   "-movflags", "+faststart", str(product)])

    report["captions"] = timed
    report["starts"] = {k: round(v, 2) for k, v in starts.items()}
    report["total_s"] = round(ed.duration_of(product), 2)
    report["missing_steps"] = missing
    frames = []
    for name, sid, marker, after in REPORT_FRAMES:
        if sid not in starts:
            continue
        local = marker_at(sid, marker) if marker else None
        at = starts[sid] + (local + after if local is not None else report["steps"][sid]["seconds"] / 2)
        target = REPORT / f"frame_{name}.png"
        ed.ffmpeg(["-ss", f"{at:.2f}", "-i", str(product), "-frames:v", "1", str(target)])
        frames.append({"step": sid, "at": round(at, 2), "file": str(target.relative_to(REPO))})
    for c in timed:     # one frame per caption, in its middle (to check light and dark screens)
        at = (c["from"] + c["to"]) / 2
        target = REPORT / f"caption_{c['step']}_{at:.0f}.png"
        ed.ffmpeg(["-ss", f"{at:.2f}", "-i", str(product), "-frames:v", "1", str(target)])
    report["frames"] = frames
    (REPORT / "edit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    m, s = divmod(report["total_s"], 60)
    print(f"\n{product.name}: {int(m)}:{s:05.2f}  ({product})")
    if missing:
        print(f"Missing steps: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
