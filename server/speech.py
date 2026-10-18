"""
Speech services: STT and TTS behind small Protocol interfaces.

All blocking calls (Whisper, Polly, PyAV decode) are run via
anyio.to_thread.run_sync so they never block the async event loop.

STT
---
WhisperSTT   – faster-whisper on CPU (int8); model from env EVOCA_WHISPER_MODEL
               (default small.en).
               Loaded once at startup; set HF_HOME=data/hf-cache if not set.
               initial_prompt is built from the circle's member names and
               relations (spike results show names fail without hints).
FakeSTT      – returns a fixed transcript; for tests.

TTS
---
PollyTTS     – Amazon Polly, eu-north-1, standard engine.
               Voice from env EVOCA_TTS_VOICE (default Joanna).
               Returns mp3 bytes.
FakeTTS      – returns a silent 16 kHz WAV of the requested length; for tests.

Audio decode
------------
decode_audio(raw_bytes) -> bytes
    Any browser format (webm/ogg/wav/m4a) → 16 kHz mono 16-bit PCM bytes.
    Uses PyAV. Run via anyio.to_thread.run_sync for async callers.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import anyio
import anyio.to_thread

log = logging.getLogger(__name__)


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
    """Loads the faster-whisper model once (per process); transcribes in a thread.

    Settings, measured on experiments/audio (CPU, int8, warm model):
      beam_size=1 + vad_filter    answer1.m4a (9 s) 3.5 s, test1.m4a (73 s) 12.7 s,
                                  and the best transcripts ("the singer", "whenever I smell")
      beam_size=5 (old default)   3.9 s and 21.6 s
      cpu_threads 4 / 16          no gain over the default
      word_timestamps             about 15% of the time; kept, segments need them.
    VAD keeps word timestamps on the original audio timeline.
    preload() loads and warms the model at app startup, so the first turn does
    not pay the ~3 s load.
    """

    DEFAULT_MODEL = "small.en"
    BEAM_SIZE = 1
    VAD_FILTER = True

    _model = None   # class-level singleton
    _lock = threading.Lock()
    loads = 0       # how many times the model was loaded (tests check it stays 1)

    @classmethod
    def _ensure_model(cls):
        with cls._lock:
            if cls._model is None:
                if not os.environ.get("HF_HOME"):
                    os.environ["HF_HOME"] = str(Path("data") / "hf-cache")
                from faster_whisper import WhisperModel
                name = os.environ.get("EVOCA_WHISPER_MODEL") or cls.DEFAULT_MODEL
                t0 = time.perf_counter()
                cls._model = WhisperModel(name, device="cpu", compute_type="int8")
                cls.loads += 1
                log.info("Whisper %s loaded in %.1f s", name, time.perf_counter() - t0)
            return cls._model

    @classmethod
    def preload(cls) -> None:
        """Load the model and run one short transcription to warm it up."""
        cls._transcribe_sync(b"\x00\x00" * 16_000, "")

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

        model = cls._ensure_model()
        # 16 kHz mono int16 PCM -> float32 in [-1, 1], passed in memory (no temp file).
        audio = np.frombuffer(pcm_bytes, dtype="<i2").astype(np.float32) / 32768.0
        segments, info = model.transcribe(
            audio,
            language="en",
            beam_size=cls.BEAM_SIZE,
            vad_filter=cls.VAD_FILTER,
            word_timestamps=True,
            initial_prompt=initial_prompt or None,
        )
        segments = list(segments)

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


_MAX_QUESTION_CHARS = 200   # Whisper keeps only the last ~224 tokens of a prompt


def build_initial_prompt(members: list[dict], last_question: str | None = None) -> str:
    """Build a Whisper initial_prompt from member names and relations, plus the
    question the agent just asked (the person's answer usually reuses its words).

    Spike results: names fail without hints. Format:
    "A family story. Names: Fatma (grandmother), Elif (granddaughter), ...
     The question was: Did you ever meet anyone famous growing up?"
    """
    parts = []
    for m in members:
        name = m.get("name", "")
        rel  = m.get("relation_to_center")
        if rel:
            parts.append(f"{name} ({rel})")
        elif name:
            parts.append(name)
    prompt = f"A family story. Names: {', '.join(parts)}." if parts else ""
    if last_question:
        question = last_question.strip()[-_MAX_QUESTION_CHARS:]
        prompt = f"{prompt} The question was: {question}".strip()
    return prompt


class FakeSTT:
    """Returns a fixed transcript; used in tests."""

    def __init__(self, text: str = "hello", duration_ms: int = 1000):
        self._text = text
        self._duration_ms = duration_ms
        self.prompts: list[str] = []   # every initial_prompt received, for tests

    async def transcribe(self, pcm_bytes: bytes, initial_prompt: str = "") -> STTResult:
        self.prompts.append(initial_prompt)
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
    mp3_bytes: bytes        # the audio bytes, in audio_format
    duration_ms: int        # approximate; 0 if unknown
    audio_format: str = "mp3"   # "mp3" (Polly) or "wav" (FakeTTS); also the file extension


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


class FakeTTS:
    """Returns a silent 16 kHz mono WAV of duration_ms; used in tests.

    A real (decodable) payload, so the backend can append it to the session WAV.
    """

    def __init__(self, duration_ms: int = 500):
        self._duration_ms = duration_ms

    async def synthesize(self, text: str) -> TTSResult:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16_000)
            wf.writeframes(b"\x00\x00" * (16 * self._duration_ms))
        return TTSResult(mp3_bytes=buf.getvalue(), duration_ms=self._duration_ms,
                         audio_format="wav")


# ---------------------------------------------------------------------------
# Audio decode: any browser format → 16 kHz mono 16-bit PCM bytes
# ---------------------------------------------------------------------------

def _decode_audio_sync(raw_bytes: bytes) -> bytes:
    """Decode any browser audio format to 16 kHz mono int16 PCM bytes.

    For WAV files already at 16 kHz mono int16, the PCM frames are extracted
    directly (no PyAV resample needed). All other formats go through PyAV.
    Runs synchronously; call via anyio.to_thread.run_sync.
    """
    # Fast path: plain WAV at 16 kHz / mono / 16-bit PCM — just read frames.
    if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(raw_bytes), "rb") as wf:
                if wf.getnchannels() == 1 and wf.getsampwidth() == 2 and wf.getframerate() == 16_000:
                    return wf.readframes(wf.getnframes())
        except wave.Error:
            pass  # not a plain PCM WAV; let PyAV handle it

    import av

    buf = io.BytesIO(raw_bytes)
    container = av.open(buf, format=None)

    resampler = av.AudioResampler(
        format="s16",
        layout="mono",
        rate=16_000,
    )

    # A plane's buffer is padded for alignment; copy only the real samples
    # (s16 mono = 2 bytes per sample), or junk lands between frames and the
    # audio comes out about 25% too long.
    pcm_chunks: list[bytes] = []
    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            pcm_chunks.append(bytes(resampled.planes[0])[: resampled.samples * 2])

    for resampled in resampler.resample(None):
        pcm_chunks.append(bytes(resampled.planes[0])[: resampled.samples * 2])

    container.close()
    return b"".join(pcm_chunks)


async def decode_audio(raw_bytes: bytes) -> bytes:
    """Async wrapper: decode browser audio → 16 kHz mono int16 PCM."""
    return await anyio.to_thread.run_sync(
        lambda: _decode_audio_sync(raw_bytes),
        abandon_on_cancel=True,
    )
