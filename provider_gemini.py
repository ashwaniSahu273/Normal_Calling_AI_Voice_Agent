"""Gemini Live provider — multi-turn keep-alive + session resumption."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from google import genai
from google.genai import types

import audio
import config
import knowledge
from provider_base import (
    AudioDelta,
    ProviderEvent,
    RealtimeProvider,
    SpeechStarted,
    ToolCall,
    TranscriptDelta,
    TurnComplete,
)
from tools import TOOL_DEFS

log = logging.getLogger("voice-agent.gemini")

_THINKING_LEVEL_MAP = {
    "minimal": types.ThinkingLevel.MINIMAL,
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}

_END_SPEECH_MAP = {
    "low": types.EndSensitivity.END_SENSITIVITY_LOW,
    "high": types.EndSensitivity.END_SENSITIVITY_HIGH,
}


def _gemini_31_or_newer(model: str) -> bool:
    m = (model or "").lower()
    return "3.1" in m or "3-1" in m or m.startswith("gemini-3")

_JSON_TYPE_MAP = {
    "object": types.Type.OBJECT,
    "string": types.Type.STRING,
    "number": types.Type.NUMBER,
    "integer": types.Type.INTEGER,
    "boolean": types.Type.BOOLEAN,
    "array": types.Type.ARRAY,
}


def _to_gemini_schema(js: dict[str, Any]) -> types.Schema:
    kwargs: dict[str, Any] = {
        "type": _JSON_TYPE_MAP.get(js.get("type", "object"), types.Type.OBJECT),
    }
    if "description" in js:
        kwargs["description"] = js["description"]
    if "properties" in js:
        kwargs["properties"] = {
            key: _to_gemini_schema(val) for key, val in js["properties"].items()
        }
    if "required" in js:
        kwargs["required"] = js["required"]
    if "items" in js:
        kwargs["items"] = _to_gemini_schema(js["items"])
    return types.Schema(**kwargs)


def _gemini_tools() -> list[types.Tool]:
    declarations = [
        types.FunctionDeclaration(
            name=t["name"],
            description=t.get("description", ""),
            parameters=_to_gemini_schema(t.get("parameters", {"type": "object"})),
        )
        for t in TOOL_DEFS
    ]
    return [types.Tool(function_declarations=declarations)]


def _audio_chunks(response: types.LiveServerMessage) -> list[bytes]:
    chunks: list[bytes] = []
    sc = response.server_content
    if sc and sc.model_turn and sc.model_turn.parts:
        for part in sc.model_turn.parts:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                chunks.append(inline.data)
    if chunks:
        return chunks
    data = getattr(response, "data", None)
    if data:
        chunks.append(data)
    return chunks


class GeminiLiveProvider(RealtimeProvider):
    def __init__(self) -> None:
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        self._cm: Any = None
        self._session: Any = None
        self._out_resampler = audio.Resampler(config.GEMINI_OUTPUT_RATE, config.TELEPHONY_SAMPLE_RATE)
        self._in_resampler = audio.Resampler(config.TELEPHONY_SAMPLE_RATE, config.GEMINI_INPUT_RATE)
        self._resume_handle: str | None = None
        self._closed = False
        self._send_lock = asyncio.Lock()
        self._greeted = False
        self._continuity_digest = ""
        self._session_started = time.monotonic()

    def set_continuity_digest(self, digest: str) -> None:
        self._continuity_digest = (digest or "").strip()

    def _continuity_hint(self, *, after_reconnect: bool = False) -> str:
        prefix = (
            "Technical refresh — the caller is still on the line. "
            if after_reconnect
            else "Continue the same live call. "
        )
        hint = (
            f"{prefix}"
            "Do NOT call end_call. Do NOT greet from scratch or ask 'how may I help' again. "
            "Do NOT re-ask language or repeat facts you already shared. "
            "Listen for their next question; if they were mid-topic, continue that topic in ONE short sentence.\n"
        )
        digest = self._continuity_digest
        if digest.strip():
            hint += f"Remember:\n{digest.strip()}\n"
        return hint

    async def refresh_session(self, digest: str = "") -> None:
        """New Live session with conversation digest (reduces long-call latency)."""
        if self._closed:
            return
        if digest.strip():
            self._continuity_digest = digest.strip()
        log.info("Gemini soft session reset")
        self._resume_handle = None
        self._session_started = time.monotonic()
        await self._open_session(greet=False)
        await self.nudge(self._continuity_hint(after_reconnect=False))

    def needs_soft_reset(self) -> bool:
        return False

    def _thinking_config(self) -> types.ThinkingConfig:
        if _gemini_31_or_newer(config.GEMINI_MODEL):
            level = _THINKING_LEVEL_MAP.get(
                config.GEMINI_THINKING_LEVEL, types.ThinkingLevel.MINIMAL
            )
            return types.ThinkingConfig(thinking_level=level)
        return types.ThinkingConfig(thinking_budget=config.GEMINI_THINKING_BUDGET)

    def _end_speech_sensitivity(self) -> types.EndSensitivity:
        return _END_SPEECH_MAP.get(
            config.GEMINI_END_SPEECH_SENSITIVITY,
            types.EndSensitivity.END_SENSITIVITY_LOW,
        )

    def _compression_config(self) -> types.ContextWindowCompressionConfig | None:
        if not config.GEMINI_CONTEXT_COMPRESSION:
            return None
        return types.ContextWindowCompressionConfig(
            trigger_tokens=12_000,
            sliding_window=types.SlidingWindow(target_tokens=8_192),
        )

    def _live_config(self) -> types.LiveConnectConfig:
        system_prompt = (config.SYSTEM_PROMPT or "").strip() or knowledge.build_system_prompt()
        config.SYSTEM_PROMPT = system_prompt
        resume_kwargs: dict[str, Any] = {}
        if self._resume_handle:
            resume_kwargs["handle"] = self._resume_handle
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=types.Content(parts=[types.Part(text=system_prompt)]),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.VOICE)
                )
            ),
            tools=_gemini_tools(),
            thinking_config=self._thinking_config(),
            context_window_compression=self._compression_config(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_HIGH,
                    end_of_speech_sensitivity=self._end_speech_sensitivity(),
                    prefix_padding_ms=config.GEMINI_PREFIX_PADDING_MS,
                    silence_duration_ms=config.GEMINI_SILENCE_MS,
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            session_resumption=types.SessionResumptionConfig(**resume_kwargs),
        )

    async def _open_session(self, *, greet: bool) -> None:
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._cm = None
            self._session = None

        self._cm = self._client.aio.live.connect(
            model=config.GEMINI_MODEL, config=self._live_config()
        )
        self._session = await self._cm.__aenter__()
        if greet and not self._greeted:
            await self._session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=(
                                "Greet the caller now in ONE short sentence. "
                                f"Use this greeting idea: {config.GREETING} "
                                "Offer English or Hindi briefly if natural. "
                                "Then keep listening — do not end the call."
                            )
                        )
                    ],
                ),
                turn_complete=True,
            )
            self._greeted = True
        log.info(
            "Gemini Live ready voice=%s model=%s silence_ms=%s resume=%s",
            config.VOICE,
            config.GEMINI_MODEL,
            config.GEMINI_SILENCE_MS,
            bool(self._resume_handle),
        )

    async def connect(self) -> None:
        self._closed = False
        await self._open_session(greet=True)

    async def send_caller_audio(self, pcm8k: bytes) -> None:
        if self._session is None or not pcm8k or self._closed:
            return
        pcm16k = self._in_resampler.process(pcm8k)
        if not pcm16k:
            return
        try:
            async with self._send_lock:
                if self._session is None:
                    return
                await self._session.send_realtime_input(
                    audio=types.Blob(
                        data=pcm16k,
                        mime_type=f"audio/pcm;rate={config.GEMINI_INPUT_RATE}",
                    )
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("send_caller_audio failed: %s", exc)

    async def nudge(self, hint: str = "") -> None:
        """Unstick a quiet model mid-call without hanging up."""
        if self._session is None or self._closed:
            return
        text = hint or (
            "The caller has finished speaking and is waiting for your answer. "
            "Reply once in ONE or TWO short sentences. Do NOT ask a new question if you "
            "already asked one they are answering. Do NOT call end_call."
        )
        try:
            async with self._send_lock:
                if self._session is None:
                    return
                await self._session.send_client_content(
                    turns=types.Content(
                        role="user",
                        parts=[types.Part(text=text)],
                    ),
                    turn_complete=True,
                )
            log.info("Gemini nudge sent")
        except Exception as exc:  # noqa: BLE001
            log.warning("nudge failed: %s", exc)

    async def events(self) -> AsyncIterator[ProviderEvent]:
        reconnects = 0
        while not self._closed:
            assert self._session is not None
            try:
                async for response in self._session.receive():
                    update = getattr(response, "session_resumption_update", None)
                    if update is not None:
                        handle = getattr(update, "new_handle", None)
                        if handle and getattr(update, "resumable", True):
                            self._resume_handle = handle

                    for raw_pcm in _audio_chunks(response):
                        pcm8k = self._out_resampler.process(raw_pcm)
                        if pcm8k:
                            yield AudioDelta(pcm8k=pcm8k)

                    server_content = response.server_content
                    if server_content is not None:
                        if server_content.interrupted:
                            yield SpeechStarted()

                        in_t = server_content.input_transcription
                        if in_t and in_t.text:
                            text = in_t.text.strip()
                            finished = getattr(in_t, "finished", None)
                            if text and finished is not False:
                                yield TranscriptDelta(role="user", text=text)

                        out_t = server_content.output_transcription
                        if out_t and out_t.text:
                            text = out_t.text.strip()
                            finished = getattr(out_t, "finished", None)
                            if text and finished is not False:
                                yield TranscriptDelta(role="assistant", text=text)

                        if getattr(server_content, "turn_complete", False):
                            yield TurnComplete()

                    tool_call = response.tool_call
                    if tool_call is not None:
                        for fc in tool_call.function_calls or []:
                            yield ToolCall(
                                call_id=getattr(fc, "id", "") or "",
                                name=fc.name,
                                arguments=dict(fc.args or {}),
                            )

                    if getattr(response, "go_away", None) is not None:
                        log.warning("Gemini go_away — will resume session")
                        break
                else:
                    # receive() ended a generation turn; keep listening
                    yield TurnComplete()
                    continue

            except Exception as exc:  # noqa: BLE001
                if self._closed:
                    return
                log.warning("Gemini receive error: %s", exc)

            if self._closed:
                return
            reconnects += 1
            if reconnects > 8:
                log.error("Too many Gemini reconnects — stopping")
                return
            try:
                await self._open_session(greet=False)
                await self.nudge(self._continuity_hint(after_reconnect=True))
            except Exception:  # noqa: BLE001
                log.exception("Gemini resume failed")
                await asyncio.sleep(0.5)

    async def send_tool_result(self, call_id: str, name: str, output: str) -> None:
        if self._session is None:
            return
        try:
            async with self._send_lock:
                if self._session is None:
                    return
                await self._session.send_tool_response(
                    function_responses=[
                        types.FunctionResponse(
                            id=call_id, name=name, response={"result": output}
                        )
                    ]
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("send_tool_result failed: %s", exc)

    async def close(self) -> None:
        self._closed = True
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
            self._cm = None
            self._session = None
