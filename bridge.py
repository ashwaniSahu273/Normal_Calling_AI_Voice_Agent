"""Core switchboard: telephony <-> AI, hang-up rules, call-end summary to n8n."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect

import audio
import config
from call_digest import (
    build_call_digest,
    count_transcript_turns,
    detect_language_hint,
    format_conversation_full,
    format_conversation_preview,
)
from provider_base import (
    AudioDelta,
    EndCallRequested,
    RealtimeProvider,
    SpeechStarted,
    ToolCall,
    TranscriptDelta,
    TurnComplete,
    make_provider,
)
from tools import call_n8n, dispatch_tool

log = logging.getLogger("voice-agent.bridge")


class CallBridge:
    def __init__(self, tel_ws: WebSocket, telephony: str) -> None:
        self.tel_ws = tel_ws
        self.telephony = telephony
        self.provider: RealtimeProvider | None = None
        self.stream_id: str | None = None
        self.call_id: str | None = None
        self.caller: str | None = None
        self._closing = False
        self._exotel_out = audio.FrameBuffer(config.EXOTEL_FRAME_BYTES)
        self._in_resampler: audio.Resampler | None = None
        self._out_resampler: audio.Resampler | None = None
        self._tel_rate = config.TELEPHONY_SAMPLE_RATE

        self._started_at = time.monotonic()
        self._last_activity = time.monotonic()
        self._hangup_task: asyncio.Task | None = None
        self._end_reason = "hangup"
        self._end_summary = ""
        self._caller_intent = ""
        self._transcript: list[dict[str, str]] = []
        self._ai_speaking = False
        self._awaiting_ai_since: float | None = None
        self._nudge_task: asyncio.Task | None = None
        self._nudge_count = 0
        self._appointment_booked = False
        self._lead_captured = False
        self._follow_up = "none"
        self._direction = "inbound"
        self._soft_reset_busy = False

    async def run(self) -> None:
        await self.tel_ws.accept()
        self.provider = make_provider()
        try:
            await self.provider.connect()
        except Exception:
            log.exception("AI provider failed to connect — closing call")
            await self._teardown()
            return

        log.info(
            "Bridge established (telephony=%s, ai=%s)",
            self.telephony,
            config.AI_PROVIDER,
        )
        self._touch()

        tel_task = asyncio.create_task(self._telephony_to_provider(), name="tel->ai")
        ai_task = asyncio.create_task(self._provider_to_telephony(), name="ai->tel")
        watch_task = asyncio.create_task(self._watchdog(), name="watchdog")
        nudge_task = asyncio.create_task(self._response_nudge_loop(), name="nudge")
        done, pending = await asyncio.wait(
            {tel_task, ai_task, watch_task, nudge_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            if task.exception():
                log.error("Task %s failed: %s", task.get_name(), task.exception())
            else:
                log.info("Task %s finished first — ending call", task.get_name())
        for task in pending:
            task.cancel()
        if self._hangup_task and not self._hangup_task.done():
            self._hangup_task.cancel()
        await self._teardown()

    def _touch(self) -> None:
        self._last_activity = time.monotonic()

    # ---- watchdog: silence + max duration --------------------------------
    async def _watchdog(self) -> None:
        while not self._closing:
            await asyncio.sleep(1.0)
            now = time.monotonic()
            elapsed = now - self._started_at
            idle = now - self._last_activity

            if elapsed >= config.MAX_CALL_DURATION_SEC:
                log.info("Max call duration reached (%.0fs)", elapsed)
                self._end_reason = "max_duration"
                await self._request_hangup(grace=0.5)
                return

            # Only silence-timeout after AI finished speaking (not mid-greeting).
            # Require a longer idle so multi-question calls are not cut short.
            if (
                not self._ai_speaking
                and idle >= config.SILENCE_TIMEOUT_SEC
                and elapsed > 15.0
            ):
                log.info("Silence timeout (%.0fs idle) — ending call", idle)
                self._end_reason = "silence"
                if not self._end_summary:
                    self._end_summary = self._fallback_summary()
                await self._request_hangup(grace=0.3)
                return

    async def _response_nudge_loop(self) -> None:
        """If caller spoke but AI stays quiet, gently poke Gemini to reply."""
        while not self._closing:
            await asyncio.sleep(0.4)
            if self._awaiting_ai_since is None or self._ai_speaking:
                continue
            waited = time.monotonic() - self._awaiting_ai_since
            if waited < config.AI_RESPONSE_NUDGE_SEC:
                continue
            if self._nudge_count >= 3:
                continue
            if self.provider is None:
                continue
            self._nudge_count += 1
            self._awaiting_ai_since = time.monotonic()
            try:
                await self.provider.nudge()
            except Exception:  # noqa: BLE001
                log.exception("nudge failed")

    async def _request_hangup(self, grace: float | None = None) -> None:
        delay = config.END_CALL_GRACE_SEC if grace is None else grace
        if self._hangup_task and not self._hangup_task.done():
            return

        async def _do() -> None:
            await asyncio.sleep(delay)
            try:
                await self.tel_ws.close()
            except Exception:  # noqa: BLE001
                pass

        self._hangup_task = asyncio.create_task(_do(), name="hangup")

    # ---- telephony -> AI ------------------------------------------------
    async def _telephony_to_provider(self) -> None:
        assert self.provider is not None
        try:
            while True:
                raw = await self.tel_ws.receive_text()
                event = json.loads(raw)
                kind = event.get("event")

                if kind == "connected":
                    log.info("Telephony WebSocket connected (%s)", self.telephony)
                    continue

                if kind == "start":
                    self._on_start(event)
                    continue

                if kind == "media":
                    payload = event.get("media", {}).get("payload")
                    if payload:
                        pcm8k = self._decode_inbound(base64.b64decode(payload))
                        if pcm8k:
                            if audio.pcm_rms(pcm8k) >= config.SPEECH_RMS_THRESHOLD:
                                self._touch()
                            await self.provider.send_caller_audio(pcm8k)
                    continue

                if kind == "stop":
                    log.info("%s sent stop; ending call", self.telephony)
                    self._end_reason = self._end_reason or "hangup"
                    break
        except WebSocketDisconnect:
            log.info("%s WebSocket disconnected", self.telephony)
        except Exception:  # noqa: BLE001
            log.exception("Error in telephony->provider loop")

    def _on_start(self, event: dict) -> None:
        start = event.get("start", {})
        if self.telephony == "exotel":
            self.stream_id = (
                start.get("stream_sid") or event.get("stream_sid") or start.get("streamSid")
            )
            self.call_id = start.get("call_sid") or start.get("callSid")
            self.caller = start.get("from")
            mf = start.get("media_format") or {}
            try:
                rate = int(mf.get("sample_rate") or config.EXOTEL_SAMPLE_RATE)
            except (TypeError, ValueError):
                rate = config.EXOTEL_SAMPLE_RATE
            self._set_tel_rate(rate)
        else:
            self.stream_id = start.get("streamId") or start.get("stream_sid")
            self.call_id = start.get("callId") or start.get("call_sid")
            self.caller = start.get("from")
            self._set_tel_rate(config.PLIVO_SAMPLE_RATE)
        log.info("Stream start call_id=%s stream_id=%s from=%s", self.call_id, self.stream_id, self.caller)

    def _set_tel_rate(self, rate: int) -> None:
        self._tel_rate = rate
        if rate == config.TELEPHONY_SAMPLE_RATE:
            self._in_resampler = None
            self._out_resampler = None
        else:
            self._in_resampler = audio.Resampler(rate, config.TELEPHONY_SAMPLE_RATE)
            self._out_resampler = audio.Resampler(config.TELEPHONY_SAMPLE_RATE, rate)

    def _decode_inbound(self, raw: bytes) -> bytes:
        if self.telephony == "plivo":
            pcm = audio.mulaw_to_pcm(raw)
        else:
            pcm = raw
        if self._in_resampler is not None:
            pcm = self._in_resampler.process(pcm)
        return pcm

    # ---- AI -> telephony ------------------------------------------------
    async def _provider_to_telephony(self) -> None:
        assert self.provider is not None
        try:
            async for ev in self.provider.events():
                if isinstance(ev, AudioDelta):
                    self._ai_speaking = True
                    self._awaiting_ai_since = None
                    self._nudge_count = 0
                    self._touch()
                    await self._send_audio(ev.pcm8k)
                elif isinstance(ev, SpeechStarted):
                    self._touch()
                    await self._barge_in()
                elif isinstance(ev, TurnComplete):
                    self._ai_speaking = False
                    self._touch()
                    if self.telephony == "exotel":
                        await self._flush_exotel()
                    await self._maybe_soft_reset_session()
                elif isinstance(ev, TranscriptDelta):
                    if ev.text:
                        self._transcript.append({"role": ev.role, "text": ev.text})
                        if ev.role == "user":
                            self._touch()
                            if not self._ai_speaking:
                                self._awaiting_ai_since = time.monotonic()
                        elif ev.role == "assistant":
                            self._awaiting_ai_since = None
                elif isinstance(ev, ToolCall):
                    await self._handle_tool_call(ev)
                elif isinstance(ev, EndCallRequested):
                    self._end_reason = ev.reason or "completed"
                    self._end_summary = ev.summary or self._end_summary
                    await self._request_hangup()
        except Exception:  # noqa: BLE001
            log.exception("Error in provider->telephony loop")

    async def _send_audio(self, pcm8k: bytes) -> None:
        if not pcm8k:
            return
        if self.telephony == "exotel":
            pcm = pcm8k
            if self._out_resampler is not None:
                pcm = self._out_resampler.process(pcm)
            for frame in self._exotel_out.push(pcm):
                await self._send_exotel_media(frame)
        else:
            mulaw = audio.pcm_to_mulaw(pcm8k)
            await self.tel_ws.send_text(
                json.dumps(
                    {
                        "event": "playAudio",
                        "media": {
                            "contentType": config.PLIVO_CONTENT_TYPE,
                            "sampleRate": config.PLIVO_SAMPLE_RATE,
                            "payload": base64.b64encode(mulaw).decode("ascii"),
                        },
                    }
                )
            )

    async def _send_exotel_media(self, pcm: bytes) -> None:
        msg: dict[str, object] = {
            "event": "media",
            "media": {"payload": base64.b64encode(pcm).decode("ascii")},
        }
        if self.stream_id:
            msg["stream_sid"] = self.stream_id
            msg["streamSid"] = self.stream_id
        await self.tel_ws.send_text(json.dumps(msg))

    async def _flush_exotel(self) -> None:
        frame = self._exotel_out.flush()
        if frame:
            await self._send_exotel_media(frame)

    async def _barge_in(self) -> None:
        self._exotel_out.clear()
        self._ai_speaking = False
        if self.telephony == "exotel":
            msg: dict[str, object] = {"event": "clear"}
            if self.stream_id:
                msg["stream_sid"] = self.stream_id
            await self.tel_ws.send_text(json.dumps(msg))
        else:
            msg = {"event": "clearAudio"}
            if self.stream_id:
                msg["streamId"] = self.stream_id
            await self.tel_ws.send_text(json.dumps(msg))

    async def _handle_tool_call(self, call: ToolCall) -> None:
        assert self.provider is not None
        log.info("Tool call: %s(%s)", call.name, call.arguments)
        ctx = {"call_id": self._stable_call_id(), "from": self.caller}
        payload_ctx = {**ctx, "direction": self._direction, "language": detect_language_hint(self._transcript)}
        result = await dispatch_tool(call.name, call.arguments, payload_ctx)
        await self.provider.send_tool_result(call.call_id, call.name, result)

        if call.name == "end_call":
            self._end_reason = str(call.arguments.get("reason") or "thanks")
            self._end_summary = str(call.arguments.get("summary") or "")
            self._caller_intent = str(call.arguments.get("caller_intent") or "")
            log.info("end_call reason=%s", self._end_reason)
            await self._request_hangup()
            return

        if call.name == "book_appointment":
            self._appointment_booked = True
            self._follow_up = "appointment"
        elif call.name == "create_lead":
            self._lead_captured = True
            if self._follow_up == "none":
                self._follow_up = "callback"
        elif call.name == "send_notification":
            if self._follow_up == "none":
                self._follow_up = "team_notified"

    async def _maybe_soft_reset_session(self) -> None:
        if self._closing or self._soft_reset_busy or self.provider is None:
            return
        if not self.provider.needs_soft_reset():
            return
        self._soft_reset_busy = True
        try:
            digest = build_call_digest(
                self._transcript,
                caller_intent=self._guess_intent(),
                max_chars=config.GEMINI_DIGEST_MAX_CHARS,
            )
            await self.provider.refresh_session(digest)
            log.info("Soft session reset completed call_id=%s", self.call_id)
        except Exception:  # noqa: BLE001
            log.exception("Soft session reset failed")
        finally:
            self._soft_reset_busy = False

    def _stable_call_id(self) -> str:
        if self.call_id:
            return str(self.call_id)
        return f"voice-{int(self._started_at * 1000)}"

    def _conversation_text(self) -> str:
        if not self._transcript:
            return "No spoken transcript captured."
        lines: list[str] = []
        for t in self._transcript:
            who = "Caller" if t["role"] == "user" else "Agent"
            lines.append(f"{who}: {t['text']}")
        return "\n".join(lines)

    def _guess_intent(self) -> str:
        if self._caller_intent:
            return self._caller_intent
        user_bits = " ".join(t["text"] for t in self._transcript if t["role"] == "user").lower()
        checks = [
            ("website", "Website / web development"),
            ("app", "Mobile app"),
            ("crm", "CRM / WhatsApp CRM"),
            ("hosting", "Hosting"),
            ("seo", "SEO / marketing"),
            ("demo", "Product demo"),
            ("price", "Pricing enquiry"),
            ("callback", "Callback request"),
            ("hindi", "General enquiry (Hindi)"),
        ]
        for key, label in checks:
            if key in user_bits:
                return label
        return "General enquiry"

    def _friendly_outcome(self) -> str:
        mapping = {
            "thanks": "Caller said thanks / done",
            "goodbye": "Caller said goodbye",
            "completed": "Request completed",
            "silence": "Ended after silence",
            "max_duration": "Max call time reached",
            "hangup": "Caller hung up",
            "other": "Ended",
        }
        return mapping.get(self._end_reason, self._end_reason or "Ended")

    def _fallback_summary(self) -> str:
        if not self._transcript:
            return (
                "Short call with little spoken detail captured. "
                "Please check if the caller needs a callback."
            )
        intent = self._guess_intent()
        user_lines = [t["text"] for t in self._transcript if t["role"] == "user"][-4:]
        agent_lines = [t["text"] for t in self._transcript if t["role"] == "assistant"][-3:]
        parts = [f"Caller interest: {intent}."]
        if user_lines:
            parts.append("Caller said: " + " | ".join(user_lines))
        if agent_lines:
            parts.append("Agent covered: " + " | ".join(agent_lines))
        parts.append("Follow-up: review and call back if needed.")
        return " ".join(parts)

    def _format_duration(self, seconds: int) -> str:
        minutes, sec = divmod(max(0, seconds), 60)
        if minutes:
            return f"{minutes} min {sec} sec"
        return f"{sec} sec"

    async def _notify_call_ended(self) -> None:
        duration = int(time.monotonic() - self._started_at)
        summary = (self._end_summary or self._fallback_summary()).strip()
        conversation_full = self._conversation_text()
        conversation_preview = format_conversation_preview(
            self._transcript,
            max_turns=config.SHEET_CONVERSATION_PREVIEW_TURNS,
            max_total_chars=config.SHEET_CONVERSATION_PREVIEW_MAX_CHARS,
        )
        transcript_turns = count_transcript_turns(self._transcript)
        intent = self._guess_intent()
        outcome = self._friendly_outcome()
        # IST wall clock for the sheet
        try:
            from zoneinfo import ZoneInfo

            now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        except Exception:  # noqa: BLE001
            now_ist = datetime.now(timezone.utc)
        date_str = now_ist.strftime("%Y-%m-%d")
        time_str = now_ist.strftime("%I:%M %p")
        language = detect_language_hint(self._transcript)
        yes_no = lambda b: "yes" if b else "no"  # noqa: E731

        args = {
            "call_id": self._stable_call_id(),
            "date": date_str,
            "time_ist": time_str,
            "caller_phone": self.caller or "",
            "duration": self._format_duration(duration),
            "duration_sec": duration,
            "direction": self._direction,
            "language": language,
            "outcome": outcome,
            "caller_intent": intent,
            "summary": summary,
            "conversation_preview": conversation_preview,
            "conversation_full": conversation_full,
            "transcript_turns": transcript_turns,
            "transcript_ref": "voice_transcripts tab",
            "conversation": conversation_preview,
            "transcript": conversation_full,
            "appointment_booked": yes_no(self._appointment_booked),
            "lead_captured": yes_no(self._lead_captured),
            "follow_up": self._follow_up,
            "reason": self._end_reason,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "notify_whatsapp": config.NOTIFY_WHATSAPP or None,
        }
        ctx = {"call_id": self._stable_call_id(), "from": self.caller}
        try:
            await call_n8n("call_ended", args, ctx)
        except Exception:  # noqa: BLE001
            log.exception("Failed to post call_ended to n8n")

    async def _teardown(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            await self._notify_call_ended()
        except Exception:  # noqa: BLE001
            log.exception("call_ended notify error")
        if self.provider is not None:
            await self.provider.close()
        try:
            await self.tel_ws.close()
        except Exception:  # noqa: BLE001
            pass
        log.info(
            "Bridge torn down call_id=%s reason=%s",
            self.call_id,
            self._end_reason,
        )


async def run_bridge(ws: WebSocket, telephony: str | None = None) -> None:
    tel = (telephony or config.TELEPHONY_PROVIDER).lower()
    await CallBridge(ws, telephony=tel).run()
