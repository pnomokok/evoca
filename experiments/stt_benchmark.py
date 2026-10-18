"""
Speed and name accuracy of faster-whisper models with Evoca's STT settings
(server/speech.py: CPU, int8, beam_size=1, vad_filter, word timestamps, the
seed family's initial_prompt).

    python experiments/stt_benchmark.py                       # small.en, distil-small.en, base.en
    python experiments/stt_benchmark.py --models small.en --runs 1

Audio: every file in experiments/audio/, core/seed_assets/seed_session.wav and
three Polly answers (Kendra, like scripts/e2e_demo.py) that use the seed
family's names. The Polly clips are cached in experiments/audio_polly/, so a
rerun needs no AWS call. Each model is warmed up once, then every clip runs
`--runs` times; the table reports the median seconds per 10 s of audio, which
hint names were missed, and the transcript of every clip but the seed session
(it has a private segment) for a manual check of common words.
"""

from __future__ import annotations

import argparse
import io
import os
import statistics
import sys
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("HF_HOME", str(REPO / "data" / "hf-cache"))

from faster_whisper import WhisperModel, decode_audio  # noqa: E402

from server.speech import WhisperSTT, build_initial_prompt  # noqa: E402

SAMPLE_RATE = 16_000
MODELS = ["small.en", "distil-small.en", "base.en"]

# The seed family as the device sees it (core/seed.py).
MEMBERS = [
    {"name": "Fatma Yilmaz", "relation_to_center": None},
    {"name": "Ayşe Yilmaz", "relation_to_center": "daughter"},
    {"name": "Elif Yilmaz", "relation_to_center": "granddaughter"},
    {"name": "Can Yilmaz", "relation_to_center": "grandson"},
]
HINT_NAMES = ["Fatma", "Ayşe", "Elif", "Can", "Yilmaz"]

# (file stem, question the companion asked, answer) for the Polly clips.
POLLY_ANSWERS = [
    ("polly_elif", "Who did you tell your stories to?",
     "When Elif was little, she sat with me in the kitchen and I told her about the school in our "
     "village. Ayşe always says Elif has my patience."),
    ("polly_can", "When did you last go to the harbour?",
     "Can visited me last summer with his mother Ayşe. We walked to the harbour in Trabzon and ate "
     "fresh fish, like I did with my father."),
    ("polly_fatma", "What do you remember about your wedding?",
     "My name is Fatma Yilmaz. I married young, and when Ayşe was born, I sewed her first dress on "
     "the old Singer machine."),
]
POLLY_DIR = REPO / "experiments" / "audio_polly"
SEED_CLIP = "seed_session.wav"


def fold(text: str) -> str:
    """Lowercase without diacritics, so "Ayse" counts as "Ayşe"."""
    norm = unicodedata.normalize("NFKD", text.replace("ı", "i"))
    return "".join(c for c in norm if not unicodedata.combining(c)).lower()


def polly_clip(stem: str, text: str) -> Path:
    path = POLLY_DIR / f"{stem}.wav"
    if path.exists():
        return path
    import boto3

    polly = boto3.Session(region_name=os.environ.get("POLLY_REGION", "eu-north-1")).client("polly")
    pcm = polly.synthesize_speech(Text=text, OutputFormat="pcm", SampleRate=str(SAMPLE_RATE),
                                  VoiceId="Kendra", Engine="standard")["AudioStream"].read()
    pad = b"\x00\x00" * (SAMPLE_RATE // 4)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pad + pcm + pad)
    POLLY_DIR.mkdir(exist_ok=True)
    path.write_bytes(buf.getvalue())
    return path


def clips() -> list[tuple[str, np.ndarray, str, list[str]]]:
    """(name, audio, initial_prompt, names expected in the transcript)."""
    base_prompt = build_initial_prompt(MEMBERS)
    out = []
    for path in sorted((REPO / "experiments" / "audio").iterdir()):
        out.append((path.name, decode_audio(str(path), sampling_rate=SAMPLE_RATE), base_prompt, []))
    seed = REPO / "core" / "seed_assets" / SEED_CLIP
    out.append((seed.name, decode_audio(str(seed), sampling_rate=SAMPLE_RATE), base_prompt, []))
    for stem, question, text in POLLY_ANSWERS:
        path = polly_clip(stem, text)
        expected = [n for n in HINT_NAMES if not missed_names(text, [n])]
        out.append((path.name, decode_audio(str(path), sampling_rate=SAMPLE_RATE),
                    build_initial_prompt(MEMBERS, question), expected))
    return out


def transcribe(model: WhisperModel, audio: np.ndarray, prompt: str) -> str:
    # The same call as WhisperSTT._transcribe_sync.
    segments, _ = model.transcribe(
        audio,
        language="en",
        beam_size=WhisperSTT.BEAM_SIZE,
        vad_filter=WhisperSTT.VAD_FILTER,
        word_timestamps=True,
        initial_prompt=prompt or None,
    )
    return " ".join(s.text.strip() for s in segments)


def missed_names(text: str, expected: list[str]) -> list[str]:
    words = {w.strip(".,!?;:'\"") for w in fold(text).split()}
    return [n for n in expected if fold(n) not in words]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default=",".join(MODELS))
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    data = clips()
    rows, transcripts = [], {}
    for name in args.models.split(","):
        t0 = time.perf_counter()
        model = WhisperModel(name, device="cpu", compute_type="int8")
        load_s = time.perf_counter() - t0
        transcribe(model, np.zeros(SAMPLE_RATE, dtype=np.float32), "")   # warm-up
        per_10s, missed = [], []
        for clip, audio, prompt, expected in data:
            secs = []
            for _ in range(args.runs):
                t = time.perf_counter()
                text = transcribe(model, audio, prompt)
                secs.append(time.perf_counter() - t)
            duration = len(audio) / SAMPLE_RATE
            med = statistics.median(secs)
            per_10s.append(med / duration * 10)
            missed += [f"{clip}: {n}" for n in missed_names(text, expected)]
            transcripts[(name, clip)] = text
            print(f"{name:16} {clip:22} {duration:6.1f} s audio  {med:6.2f} s  "
                  f"({med / duration * 10:.2f} s / 10 s)", flush=True)
        rows.append((name, load_s, statistics.median(per_10s), missed))
        del model

    print("\n| Model | Load (s) | Median s per 10 s audio | Hint names missed |")
    print("|---|---|---|---|")
    for name, load_s, med, missed in rows:
        print(f"| {name} | {load_s:.1f} | {med:.2f} | {', '.join(missed) or 'none'} |")
    print("\nTranscripts:")
    for (name, clip), text in transcripts.items():
        if clip == SEED_CLIP:
            continue   # the seed session has a private segment; its text is never printed
        print(f"\n[{name}] {clip}\n{text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
