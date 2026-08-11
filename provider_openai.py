"""OpenAI Realtime provider. Converts between bridge PCM 8kHz and OpenAI g711_ulaw."""
from __future__ import annotations

import base64
import json
import logging
from typing import AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection

import audio
import config
import knowledge
from provider_base import AudioDelta, ProviderEvent, RealtimeProvider, SpeechStarted, ToolCall
from tools import live_tool_defs

log = logging.getLogger("voice-agent.openai")

_URL = f"wss://api.openai.com/v1/realtime?model={config.OPENAI_REALTIME_MODEL}"


class OpenAIRealtimeProvider(RealtimeProvider):
    def __init__(self) -> None:
        self._ws: ClientConnection | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            _URL,
            additional_headers={
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                "OpenAI-Beta": "realtime=v1",
            },
            max_size=None,
        )
        system_prompt = knowledge.build_system_prompt()
        config.SYSTEM_PROMPT = system_prompt
        await self._ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["audio", "text"],
                        "instructions": system_prompt,
                        "voice": config.VOICE,
                        "input_audio_format": config.OPENAI_AUDIO_FORMAT,
                        "output_audio_format": config.OPENAI_AUDIO_FORMAT,
                        "turn_detection": {"type": "server_vad"},
                        "tools": live_tool_defs(),
                        "tool_choice": "auto",
                    },
                }
            )
        )
        await self._ws.send(
            json.dumps(
                {
                    "type": "response.create",
                    "response": {"instructions": f"Greet the caller now with: {config.GREETING}"},
                }
            )
        )
        log.info("OpenAI Realtime session ready (voice=%s)", config.VOICE)

    async def send_caller_audio(self, pcm8k: bytes) -> None:
        if self._ws is None or not pcm8k:
            return
        mulaw = audio.pcm_to_mulaw(pcm8k)
        payload = base64.b64encode(mulaw).decode("ascii")
        await self._ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": payload}))

    async def events(self) -> AsyncIterator[ProviderEvent]:
        assert self._ws is not None
        async for raw in self._ws:
            event = json.loads(raw)
            etype = event.get("type", "")

            if etype in ("response.output_audio.delta", "response.audio.delta"):
                delta = event.get("delta", "")
                if delta:
                    mulaw = base64.b64decode(delta)
                    yield AudioDelta(pcm8k=audio.mulaw_to_pcm(mulaw))

            elif etype == "input_audio_buffer.speech_started":
                await self._ws.send(json.dumps({"type": "response.cancel"}))
                yield SpeechStarted()

            elif etype == "response.function_call_arguments.done":
                try:
                    args = json.loads(event.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield ToolCall(
                    call_id=event.get("call_id", ""),
                    name=event.get("name", ""),
                    arguments=args,
                )

            elif etype == "error":
                log.error("OpenAI Realtime error: %s", event.get("error"))

    async def send_tool_result(self, call_id: str, name: str, output: str) -> None:
        if self._ws is None:
            return
        await self._ws.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": output,
                    },
                }
            )
        )
        await self._ws.send(json.dumps({"type": "response.create"}))

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
