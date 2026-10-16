"""
Per-session WAV file manager.

Each session stores audio as data/audio/<session_id>.wav (16 kHz, mono, 16-bit PCM).
All person turns and TTS replies are appended so that Segment.start_ms / end_ms
are real byte-accurate positions in the file.

Public surface
--------------
session_wav_path(session_id) -> Path
append_pcm(session_id, pcm_bytes) -> (start_ms, end_ms)
    Append raw 16-bit PCM to the session WAV and return the [start, end) span.
read_slice(session_id, start_ms, end_ms) -> bytes
    Return a self-contained WAV for the given millisecond range.
pcm_duration_ms(pcm_bytes) -> int
    Duration of a 16-bit 16 kHz mono PCM buffer.
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

# All audio in the project is 16 kHz, mono, 16-bit PCM.
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2   # bytes (int16)
CHANNELS = 1

_AUDIO_DIR = Path("data") / "audio"


def session_wav_path(session_id: str) -> Path:
    _AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    return _AUDIO_DIR / f"{session_id}.wav"


def pcm_duration_ms(pcm_bytes: bytes) -> int:
    """Return the duration in milliseconds of a 16-bit 16 kHz mono PCM buffer."""
    n_samples = len(pcm_bytes) // SAMPLE_WIDTH
    return int(n_samples * 1000 / SAMPLE_RATE)


def _count_existing_samples(path: Path) -> int:
    """Return the number of PCM samples already in the WAV file."""
    if not path.exists():
        return 0
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes()


def append_pcm(session_id: str, pcm_bytes: bytes) -> tuple[int, int]:
    """Append PCM frames to the session WAV.

    Returns (start_ms, end_ms) of the appended audio.
    The WAV file is created if it does not yet exist.
    """
    path = session_wav_path(session_id)

    # Determine start position.
    existing_samples = _count_existing_samples(path)
    start_ms = int(existing_samples * 1000 / SAMPLE_RATE)

    n_new_samples = len(pcm_bytes) // SAMPLE_WIDTH
    end_ms = int((existing_samples + n_new_samples) * 1000 / SAMPLE_RATE)

    if path.exists():
        # Read existing data, rewrite with appended frames.
        with wave.open(str(path), "rb") as wf:
            existing_pcm = wf.readframes(wf.getnframes())
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(existing_pcm + pcm_bytes)
    else:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_bytes)

    return start_ms, end_ms


def read_slice(session_id: str, start_ms: int, end_ms: int) -> bytes:
    """Return a complete WAV file containing [start_ms, end_ms) of the session.

    Raises FileNotFoundError if the WAV does not exist.
    Raises ValueError if the range is out of bounds or inverted.
    """
    path = session_wav_path(session_id)
    if not path.exists():
        raise FileNotFoundError(f"No audio file for session {session_id!r}")
    if start_ms < 0 or end_ms <= start_ms:
        raise ValueError(f"Invalid range: [{start_ms}, {end_ms})")

    start_sample = int(start_ms * SAMPLE_RATE / 1000)
    end_sample   = int(end_ms   * SAMPLE_RATE / 1000)

    with wave.open(str(path), "rb") as wf:
        total = wf.getnframes()
        if start_sample > total:
            raise ValueError(f"start_ms {start_ms} is beyond the end of the file")
        end_sample = min(end_sample, total)
        wf.setpos(start_sample)
        pcm = wf.readframes(end_sample - start_sample)

    # Build a self-contained WAV in memory.
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()
