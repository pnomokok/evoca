"""
Generate the guided tour's sample answers once, with Polly (needs AWS credentials).

    python scripts/make_demo_audio.py              # every clip
    python scripts/make_demo_audio.py answer_1     # only the named clips

Writes web/public/demo-audio/answer_1.mp3, answer_2.mp3 and goodbye.mp3: Fatma's
voice (the same Polly voice as core/seed_assets), standard engine. On the stage's
device, "Use a sample answer" plays these and sends the same audio to
POST /api/device/turn, so speech-to-text, the companion and the archivist run for
real. They answer the tour's suggested question (web/src/utils/tour.js). Re-run
this script only when a text changes, and commit the files.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import boto3

OUT = Path(__file__).resolve().parent.parent / "web" / "public" / "demo-audio"
VOICE = "Kendra"          # Fatma (scripts/make_seed_audio.py)
SAMPLE_RATE = "16000"     # speech only; keeps the files small

CLIPS = {
    "answer_1": (
        # Every word easy for Whisper small.en: "My friend Ayten and I" was heard as "My friend
        # died and I", and the archivist's summary then had her friend die.
        "Oh, we played hopscotch in the street with the neighbours' girls. And in winter my father "
        "made us a wooden sled. My best friend and I raced down the hill behind the mosque on it, "
        "until our cheeks were red."
    ),
    "answer_2": (
        # "The sled" was heard as "This lead", and "grandson Can" as "grandson Ken"; the commas
        # around the name let Whisper hear it.
        "My sled was heavy, made of walnut wood. My father carved my initials on it. I kept it for "
        "years, until my grandson, Can, broke it when he was six."
    ),
    "goodbye": "That's enough for today, dear. Goodbye.",
}


def main(names: list[str]) -> None:
    unknown = set(names) - set(CLIPS)
    if unknown:
        raise SystemExit(f"Unknown clip(s): {', '.join(sorted(unknown))}; choose from {', '.join(CLIPS)}")
    polly = boto3.Session(region_name=os.environ.get("POLLY_REGION", "eu-north-1")).client("polly")
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in CLIPS.items():
        if names and name not in names:
            continue
        audio = polly.synthesize_speech(Text=text, OutputFormat="mp3", SampleRate=SAMPLE_RATE,
                                        VoiceId=VOICE, Engine="standard")["AudioStream"].read()
        path = OUT / f"{name}.mp3"
        path.write_bytes(audio)
        print(f"Wrote {path} ({len(audio) // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1:])
