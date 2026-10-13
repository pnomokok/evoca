"""Quick test: transcribe an English audio file locally with Whisper (free, no account).

Prints the transcript, word-level timestamps and how long it took.
Usage: python experiments/whisper_test.py experiments/audio/test1.m4a
"""

import sys
import time

from faster_whisper import WhisperModel

MODEL_SIZE = "small.en"  # try "base.en" if this is too slow


def main(audio_path: str) -> None:
    print(f"Loading model {MODEL_SIZE} (first run downloads it, ~500 MB)...")
    model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

    started = time.time()
    segments, info = model.transcribe(
        audio_path,
        language="en",
        word_timestamps=True,
        initial_prompt="A family story. Names: Ahmet, Zeynep. Places: Kaz Dağları.",
    )    
    segments = list(segments)  # transcription actually runs here
    elapsed = time.time() - started

    print(f"\nAudio length {info.duration:.1f}s, transcription took {elapsed:.1f}s")
    print("\nTranscript:")
    print(" ".join(segment.text.strip() for segment in segments))

    words = [word for segment in segments for word in segment.words]
    print(f"\nWords with timestamps ({len(words)} total, first 15 shown):")
    for word in words[:15]:
        print(f"  {word.start:>7.2f}s - {word.end:>7.2f}s  {word.word.strip()}  (probability {word.probability:.2f})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python experiments/whisper_test.py <audio file>")
    main(sys.argv[1])