"""
Generate the seed sessions' audio once, with Polly (needs AWS credentials).

    python scripts/make_seed_audio.py                   # every seed session
    python scripts/make_seed_audio.py seed_session_2    # only the named ones

For each session, writes core/seed_assets/<name>.wav (16 kHz, mono, 16-bit PCM)
and core/seed_assets/<name>.json: every segment's speaker, transcript,
start_ms/end_ms in the WAV and word timings from Polly speech marks. core.seed
only copies these files, so seeding works without AWS. Re-run this script only
for a session whose lines change (its stories' ranges follow its timings), and
commit both files.

  seed_session    The Mulberry Tree, the private Hatice part, The Tailor's Shop.
  seed_session_2  Father's Workshop (the pending story Ayşe sees).
"""

from __future__ import annotations

import io
import sys
import json
import os
import wave
from pathlib import Path

import boto3

ASSETS = Path(__file__).resolve().parent.parent / "core" / "seed_assets"
SAMPLE_RATE = 16_000
LEAD_MS = 300      # silence before the first segment
GAP_MS = 500       # silence between segments

CENTER_VOICE = "Kendra"   # Fatma
AGENT_VOICE = "Joanna"    # the companion (server/speech.py's default)

# Each session: (speaker, private, transcript), in the order they were said.
SEGMENTS = [
    ("center", False,
     "When I was a little girl in the village, we had a big mulberry tree in the garden. "
     "Every summer we would climb it and eat until our hands turned purple."),
    ("agent", False, "That sounds wonderful. Did you have siblings to climb with?"),
    ("center", True,
     "Yes, my sister Hatice and I. We were inseparable. She moved to Germany in 1972, and I did "
     "not see her for three years. Those were hard times, but let us not talk about that today."),
    ("agent", False, "Of course. What did you do when you were a young woman?"),
    ("center", False,
     "I worked at the tailor's shop in our neighbourhood. I learned to sew by hand, and I still "
     "remember the hum of the old Singer machine and the smell of fresh cotton on warm afternoons."),
]
SEGMENTS_2 = [
    # "Watch him plane the wood" was heard by Whisper small.en as "watch him play in the wood":
    # "plane the wooden boards" is heard exactly.
    ("center", False,
     "My father had a small carpentry workshop behind our house. I used to sit on a stool and watch "
     "him plane the wooden boards. The whole place smelled of fresh sawdust. Even now, that smell "
     "makes me feel safe."),
]
SESSIONS = {"seed_session": SEGMENTS, "seed_session_2": SEGMENTS_2}


def _ms_to_bytes(ms: int) -> int:
    return ms * SAMPLE_RATE // 1000 * 2


def build(polly, name: str, lines: list[tuple[str, bool, str]]) -> None:
    pcm = bytearray(b"\x00" * _ms_to_bytes(LEAD_MS))
    segments = []
    for speaker, private, text in lines:
        voice = CENTER_VOICE if speaker == "center" else AGENT_VOICE
        audio = polly.synthesize_speech(Text=text, OutputFormat="pcm", SampleRate=str(SAMPLE_RATE),
                                        VoiceId=voice, Engine="standard")["AudioStream"].read()
        marks_raw = polly.synthesize_speech(Text=text, OutputFormat="json", SpeechMarkTypes=["word"],
                                            VoiceId=voice, Engine="standard")["AudioStream"].read()
        marks = [json.loads(line) for line in marks_raw.decode("utf-8").splitlines() if line.strip()]
        start = len(pcm) // 2 * 1000 // SAMPLE_RATE
        end = start + len(audio) // 2 * 1000 // SAMPLE_RATE
        words = []
        for i, m in enumerate(marks):
            w_start = start + m["time"]
            w_end = (start + marks[i + 1]["time"] - 1) if i + 1 < len(marks) else end
            words.append({"w": m["value"], "start_ms": w_start, "end_ms": max(w_end, w_start + 1)})
        segments.append({"speaker": speaker, "is_private": private, "transcript": text,
                         "start_ms": start, "end_ms": end, "words": words})
        pcm += audio + b"\x00" * _ms_to_bytes(GAP_MS)

    ASSETS.mkdir(exist_ok=True)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(pcm))
    (ASSETS / f"{name}.wav").write_bytes(buf.getvalue())
    (ASSETS / f"{name}.json").write_text(
        json.dumps({"voices": {"center": CENTER_VOICE, "agent": AGENT_VOICE}, "segments": segments},
                   indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    total_ms = len(pcm) // 2 * 1000 // SAMPLE_RATE
    print(f"Wrote {ASSETS / (name + '.wav')} ({total_ms} ms, {len(buf.getvalue()) // 1024} KB) and {name}.json")
    for s in segments:
        print(f"  {s['speaker']:6} {s['start_ms']:>6}-{s['end_ms']:<6} private={s['is_private']}  {s['transcript'][:50]}")


def main(names: list[str]) -> None:
    unknown = set(names) - set(SESSIONS)
    if unknown:
        raise SystemExit(f"Unknown session(s): {', '.join(sorted(unknown))}; choose from {', '.join(SESSIONS)}")
    polly = boto3.Session(region_name=os.environ.get("POLLY_REGION", "eu-north-1")).client("polly")
    for name, lines in SESSIONS.items():
        if not names or name in names:
            build(polly, name, lines)


if __name__ == "__main__":
    main(sys.argv[1:])
