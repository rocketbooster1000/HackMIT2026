"""Synthesize narration audio with edge-tts and report real durations.

`synthesize(text, out_path)` writes an mp3 and returns its duration in
seconds, measured from edge-tts WordBoundary metadata (offsets are
100-ns ticks). If a scene produces no boundary events the caller should
fall back to the script's duration_hint.

No API key required — edge-tts uses the Microsoft Edge speech service.
Voice/rate/pitch are configurable via EDGE_TTS_VOICE, EDGE_TTS_RATE and
EDGE_TTS_PITCH (env vars or Django settings, same as graph_builder).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, Union

import edge_tts

from .graph_builder import _env

_DEFAULT_VOICE = "en-US-AriaNeural"
_MIN_DURATION = 0.5


class TTSError(RuntimeError):
    pass


async def _run(text: str, out_path: Path, voice: str, rate: str, pitch: str) -> float:
    duration_ticks = 0.0
    communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
    with open(out_path, "wb") as audio:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                end = (chunk.get("offset") or 0) + (chunk.get("duration") or 0)
                duration_ticks = max(duration_ticks, end / 10_000_000)
    return duration_ticks


def synthesize(
    text: str,
    out_path: Union[str, Path],
    *,
    voice: Optional[str] = None,
    rate: Optional[str] = None,
    pitch: Optional[str] = None,
    retries: int = 1,
) -> float:
    """Write ``text`` as an mp3 at ``out_path``; return duration in seconds.

    Retries once (``retries``) on edge-tts failures before raising TTSError.
    A return value of 0 means the audio was written but no word-boundary
    timing was reported.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    voice = voice or _env("EDGE_TTS_VOICE", _DEFAULT_VOICE)
    rate = rate or _env("EDGE_TTS_RATE", "+0%")
    pitch = pitch or _env("EDGE_TTS_PITCH", "+0Hz")

    last_error: Optional[Exception] = None
    for _ in range(retries + 1):
        try:
            seconds = asyncio.run(_run(text, out_path, voice, rate, pitch))
            if out_path.stat().st_size == 0:
                raise TTSError("edge-tts produced empty audio")
            return max(seconds, 0.0)
        except Exception as exc:
            last_error = exc
    raise TTSError(f"edge-tts failed: {last_error}") from last_error


def scene_duration(measured: float, hint: float = 0.0,
                   *, min_seconds: float = 4.0, max_seconds: float = 20.0) -> float:
    """Pick a scene duration: real TTS length, else the clamped LLM hint."""
    if measured >= _MIN_DURATION:
        return measured
    if hint > 0:
        return min(max(hint, min_seconds), max_seconds)
    return min_seconds
