"""Audio format conversion between Plivo (mu-law 8kHz) and Gemini (PCM 16k in / 24k out).

Uses the stdlib `audioop`. On Python 3.13+ `audioop` was removed from the stdlib, so the
`audioop-lts` package (imported under the same name) provides it - see requirements.txt.
"""
from __future__ import annotations

import audioop

_SAMPLE_WIDTH = 2  # 16-bit PCM
_CHANNELS = 1

# ratecv needs to carry state across chunks for click-free resampling. We keep one state
# per direction per call; callers should use a fresh Resampler per stream.


class Resampler:
    """Stateful mono 16-bit PCM resampler (wraps audioop.ratecv)."""

    def __init__(self, in_rate: int, out_rate: int) -> None:
        self.in_rate = in_rate
        self.out_rate = out_rate
        self._state = None

    def process(self, pcm: bytes) -> bytes:
        if self.in_rate == self.out_rate:
            return pcm
        converted, self._state = audioop.ratecv(
            pcm, _SAMPLE_WIDTH, _CHANNELS, self.in_rate, self.out_rate, self._state
        )
        return converted


def mulaw_to_pcm(mulaw: bytes) -> bytes:
    """mu-law bytes -> 16-bit linear PCM bytes (same sample rate)."""
    return audioop.ulaw2lin(mulaw, _SAMPLE_WIDTH)


def pcm_to_mulaw(pcm: bytes) -> bytes:
    """16-bit linear PCM bytes -> mu-law bytes (same sample rate)."""
    return audioop.lin2ulaw(pcm, _SAMPLE_WIDTH)


def pcm_rms(pcm: bytes) -> int:
    """RMS level of 16-bit mono PCM (0 if empty)."""
    if not pcm:
        return 0
    return int(audioop.rms(pcm, _SAMPLE_WIDTH))


class FrameBuffer:
    """Accumulate PCM bytes and emit fixed-size frames (Exotel needs >=100ms chunks)."""

    def __init__(self, frame_bytes: int, align: int = 320) -> None:
        self.frame_bytes = frame_bytes
        self.align = align
        self._buf = bytearray()

    def push(self, data: bytes) -> list[bytes]:
        if not data:
            return []
        self._buf.extend(data)
        out: list[bytes] = []
        while len(self._buf) >= self.frame_bytes:
            # take largest multiple of align that is still >= frame_bytes from the front
            n = (self.frame_bytes // self.align) * self.align
            out.append(bytes(self._buf[:n]))
            del self._buf[:n]
        return out

    def clear(self) -> None:
        self._buf.clear()

    def flush(self) -> bytes | None:
        """Pad remaining bytes up to the next align multiple (silence) and return one frame."""
        if not self._buf:
            return None
        while len(self._buf) % self.align != 0:
            self._buf.append(0)
        if len(self._buf) < self.frame_bytes:
            self._buf.extend(b"\x00" * (self.frame_bytes - len(self._buf)))
        frame = bytes(self._buf)
        self._buf.clear()
        return frame
