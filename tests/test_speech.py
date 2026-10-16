"""
Tests for server.speech.decode_audio.

Real compressed audio is encoded in memory with PyAV (AAC in .m4a like the
experiments clips, Opus in .webm like a browser recording) and decoded back.
The decoded 16 kHz mono PCM must have the same length as the input: a padded
plane buffer once made every clip about 25% too long, with junk between frames.
"""

from __future__ import annotations

import io
import math

import anyio
import av
import numpy as np
import pytest

from server.speech import decode_audio


def _encode(container_format: str, codec: str, rate: int, seconds: float) -> bytes:
    """A stereo 440 Hz tone, encoded in memory."""
    buf = io.BytesIO()
    out = av.open(buf, mode="w", format=container_format)
    stream = out.add_stream(codec, rate=rate)
    stream.layout = "stereo"
    n_total = int(rate * seconds)
    frame_size = 1024
    t = 0
    while t < n_total:
        n = min(frame_size, n_total - t)
        tone = (np.sin(2 * math.pi * 440 * (np.arange(t, t + n) / rate)) * 0.5).astype(np.float32)
        frame = av.AudioFrame.from_ndarray(np.vstack([tone, tone]), format="fltp", layout="stereo")
        frame.sample_rate = rate
        frame.pts = t
        for packet in stream.encode(frame):
            out.mux(packet)
        t += n
    for packet in stream.encode(None):
        out.mux(packet)
    out.close()
    return buf.getvalue()


@pytest.mark.parametrize("container_format,codec,rate", [
    ("mp4", "aac", 48_000),       # like experiments/audio/*.m4a
    ("webm", "libopus", 48_000),  # like a browser MediaRecorder upload
])
def test_decode_keeps_the_real_length(container_format, codec, rate):
    try:
        data = _encode(container_format, codec, rate, seconds=2.0)
    except Exception as exc:  # encoder not in this PyAV build
        pytest.skip(f"{codec} encoder not available: {exc}")

    pcm = anyio.run(decode_audio, data)
    seconds = len(pcm) / 2 / 16_000
    # Encoders add a little priming/padding; a padded plane added ~25%.
    assert 1.95 <= seconds <= 2.1, seconds

    samples = np.frombuffer(pcm, dtype="<i2").astype(np.int32)
    middle = samples[16_000 // 2: -16_000 // 2]
    assert np.abs(middle).max() > 5_000          # the tone is there, not silence
