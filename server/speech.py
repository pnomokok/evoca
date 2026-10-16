"""
Speech services: STT and TTS behind small Protocol interfaces.

All blocking calls (Whisper, Polly, PyAV decode) are run via
anyio.to_thread.run_sync so they never block the async event loop.

STT
---
WhisperSTT   – faster-whisper small.en on CPU (int8).
               Loaded once at startup; set HF_HOME=data/hf-cache if not set.
               initial_prompt is built from the circle's member names and
               relations (spike results show names fail without hints).
FakeSTT      – returns a fixed transcript; for tests.

TTS
---
PollyTTS     – Amazon Polly, eu-north-1, standard engine.
               Voice from env EVOCA_TTS_VOICE (default Joanna).
               Returns mp3 bytes.
FakeTTS      – returns a minimal valid mp3 header; for tests.

Audio decode
------------
decode_audio(raw_bytes) -> bytes
    Any browser format (webm/ogg/wav/m4a) → 16 kHz mono 16-bit PCM bytes.
    Uses PyAV. Run via anyio.to_thread.run_sync for async callers.
"""

from __future__ import annotations

import io
import os
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anyio
import anyio.to_thread


# ---------------------------------------------------------------------------
# STT Protocol + results
# ---------------------------------------------------------------------------

@dataclass
class STTResult:
    text: str
    words: list[dict]      # [{w, start_ms, end_ms}]
    duration_ms: int


class STT(Protocol):
    async def transcribe(
        self,
        pcm_bytes: bytes,
        initial_prompt: str = "",
    ) -> STTResult: ...


class WhisperSTT:
    """Loads faster-whisper small.en once; transcribes in a thread."""

    _model = None   # class-level singleton

    @classmethod
    def _ensure_model(cls):
        if cls._model is None:
            if not os.environ.get("HF_HOME"):
                os.environ["HF_HOME"] = str(Path("data") / "hf-cache")
            from faster_whisper import WhisperModel
            cls._model = WhisperModel("small.en", device="cpu", compute_type="int8")
        return cls._model

    async def transcribe(
        self,
        pcm_bytes: bytes,
        initial_prompt: str = "",
    ) -> STTResult:
        return await anyio.to_thread.run_sync(
            lambda: self._transcribe_sync(pcm_bytes, initial_prompt),
            abandon_on_cancel=True,
        )

    @classmethod
    def _transcribe_sync(cls, pcm_bytes: bytes, initial_prompt: str) -> STTResult:
        import numpy as np
        import tempfile, wave

        model = cls._ensure_model()

        # Write to a temp WAV file; faster-whisper accepts a file path.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name

        try:
            with wave.open(tmp_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16_000)
                wf.writeframes(pcm_bytes)

            segments, info = model.transcribe(
                tmp_path,
                language="en",
                word_timestamps=True,
                initial_prompt=initial_prompt or None,
            )
            segments = list(segments)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        text = " ".join(s.text.strip() for s in segments)
        words = []
        for seg in segments:
            if seg.words:
                for w in seg.words:
                    words.append({
                        "w": w.word.strip(),
                        "start_ms": int(w.start * 1000),
                        "end_ms": int(w.end * 1000),
                    })

        duration_ms = int(info.duration * 1000)
        return STTResult(text=text, words=words, duration_ms=duration_ms)


def build_initial_prompt(members: list[dict]) -> str:
    """Build a Whisper initial_prompt from member names and relations.

    Spike results: names fail without hints. Format:
    "A family story. Names: Fatma (grandmother), Elif (granddaughter), ..."
    """
    parts = []
    for m in members:
        name = m.get("name", "")
        rel  = m.get("relation_to_center")
        if rel:
            parts.append(f"{name} ({rel})")
        elif name:
            parts.append(name)
    return f"A family story. Names: {', '.join(parts)}." if parts else ""


class FakeSTT:
    """Returns a fixed transcript; used in tests."""

    def __init__(self, text: str = "hello", duration_ms: int = 1000):
        self._text = text
        self._duration_ms = duration_ms

    async def transcribe(self, pcm_bytes: bytes, initial_prompt: str = "") -> STTResult:
        return STTResult(
            text=self._text,
            words=[{"w": w, "start_ms": i * 200, "end_ms": i * 200 + 180}
                   for i, w in enumerate(self._text.split())],
            duration_ms=self._duration_ms,
        )


# ---------------------------------------------------------------------------
# TTS Protocol + results
# ---------------------------------------------------------------------------

@dataclass
class TTSResult:
    mp3_bytes: bytes
    duration_ms: int    # approximate; 0 if unknown


class TTS(Protocol):
    async def synthesize(self, text: str) -> TTSResult: ...


class PollyTTS:
    """Calls Amazon Polly in a thread (blocking boto3 call)."""

    def __init__(self) -> None:
        import boto3
        region = os.environ.get("POLLY_REGION", "eu-north-1")
        self._voice = os.environ.get("EVOCA_TTS_VOICE", "Joanna")
        self._client = boto3.Session(region_name=region).client("polly")

    async def synthesize(self, text: str) -> TTSResult:
        return await anyio.to_thread.run_sync(
            lambda: self._synthesize_sync(text),
            abandon_on_cancel=True,
        )

    def _synthesize_sync(self, text: str) -> TTSResult:
        resp = self._client.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=self._voice,
            Engine="standard",
        )
        mp3_bytes = resp["AudioStream"].read()
        # Rough duration: Polly standard ~150 wpm → 150/60 words/sec.
        word_count = len(text.split())
        duration_ms = max(500, int(word_count / 150 * 60 * 1000))
        return TTSResult(mp3_bytes=mp3_bytes, duration_ms=duration_ms)


# Minimal valid MP3 frame (silence) for FakeTTS — just the header bytes.
_FAKE_MP3 = (
    b"\xff\xfb\x90\x00"   # MPEG1 Layer3 128kbps 44.1kHz
    + b"\x00" * 413        # padding to one frame
)


class FakeTTS:
    """Returns a minimal mp3 payload; used in tests."""

    def __init__(self, duration_ms: int = 500):
        self._duration_ms = duration_ms

    async def synthesize(self, text: str) -> TTSResult:
        return TTSResult(mp3_bytes=_FAKE_MP3, duration_ms=self._duration_ms)


# ---------------------------------------------------------------------------
# Audio decode: any browser format → 16 kHz mono 16-bit PCM bytes
# ---------------------------------------------------------------------------

def _decode_audio_sync(raw_bytes: bytes) -> bytes:
    """Decode any browser audio format to 16 kHz mono int16 PCM bytes.

    For WAV files already at 16 kHz mono int16, the PCM frames are extracted
    directly (no PyAV resample needed). All other formats go through PyAV.
    Runs synchronously; call via anyio.to_thread.run_sync.
    """
    import av

    # Fast path: plain WAV at 16 kHz / mono / 16-bit PCM — just read frames.
    if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WAVE":
        try:
            buf_in = io.BytesIO(raw_bytes)
            with wave.open(buf_in, "rb") as wf:
                if wf.getnchannels() == 1 and wf.getsampwidth() == 2 and wf.getframerate() == 16_000:
                    return wf.readframes(wf.getnframes())
        except Exception:
            pass  # fall through to PyAV for malformed WAVs

    buf = io.BytesIO(raw_bytes)
    container = av.open(buf, format=None)

    resampler = av.AudioResampler(
        format="s16",
        layout="mono",
        rate=16_000,
    )

    pcm_chunks: list[bytes] = []
    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            pcm_chunks.append(bytes(resampled.planes[0]))

    for resampled in resampler.resample(None):
        pcm_chunks.append(bytes(resampled.planes[0]))

    container.close()
    return b"".join(pcm_chunks)


async def decode_audio(raw_bytes: bytes) -> bytes:
    """Async wrapper: decode browser audio → 16 kHz mono int16 PCM."""
    return await anyio.to_thread.run_sync(
        lambda: _decode_audio_sync(raw_bytes),
        abandon_on_cancel=True,
    )
