"""Provider abstraction — AI backends speak PCM 8kHz to the telephony bridge."""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class AudioDelta:
    """AI speech chunk as linear PCM 16-bit mono @ 8kHz."""

    pcm8k: bytes


@dataclass
class SpeechStarted:
    """Caller began speaking; flush queued playback (barge-in)."""


@dataclass
class TurnComplete:
    """Model finished a spoken turn."""


@dataclass
class TranscriptDelta:
    """Finalized transcript snippet for call logging."""

    role: str  # "user" | "assistant"
    text: str


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class EndCallRequested:
    """Model (or watchdog) wants the phone call hung up."""

    reason: str = "completed"
    summary: str = ""


ProviderEvent = (
    AudioDelta | SpeechStarted | TurnComplete | TranscriptDelta | ToolCall | EndCallRequested
)


class RealtimeProvider(abc.ABC):
    @abc.abstractmethod
    async def connect(self) -> None: ...

    @abc.abstractmethod
    async def send_caller_audio(self, pcm8k: bytes) -> None: ...

    @abc.abstractmethod
    def events(self) -> AsyncIterator[ProviderEvent]: ...

    @abc.abstractmethod
    async def send_tool_result(self, call_id: str, name: str, output: str) -> None: ...

    async def nudge(self, hint: str = "") -> None:
        """Optional: ask the model to speak if it went quiet mid-call."""
        return

    async def refresh_session(self, digest: str = "") -> None:
        """Optional: soft-reset AI session mid-call (latency / context trim)."""
        return

    def needs_soft_reset(self) -> bool:
        return False

    @abc.abstractmethod
    async def close(self) -> None: ...


def make_provider() -> RealtimeProvider:
    import config

    if config.AI_PROVIDER == "gemini":
        from provider_gemini import GeminiLiveProvider

        return GeminiLiveProvider()
    if config.AI_PROVIDER == "openai":
        from provider_openai import OpenAIRealtimeProvider

        return OpenAIRealtimeProvider()
    raise RuntimeError(f"Unknown AI_PROVIDER: {config.AI_PROVIDER!r}")
