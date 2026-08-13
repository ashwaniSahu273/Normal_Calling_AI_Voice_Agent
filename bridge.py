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
    build_owner_summary,
    count_transcript_turns,
    detect_language_hint,
    format_conversation_full,
    infer_topic_label,
    merge_transcript_line,
    pick_summary_for_sheet,
    sheet_next_step_label,
    user_wants_to_end,
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
    def __init__(
        self,
        tel_ws: WebSocket,
        telephony: str,
        direction: str = "inbound",
        caller: str | None = None,
        called: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        self.tel_ws = tel_ws
        self.telephony = telephony
        self.provider: RealtimeProvider | None = None
        self.stream_id: str | None = None
        self.call_id: str | None = None
        self.caller: str | None = self._normalize_phone(caller)
        self._called = self._normalize_phone(called) or ""
        self._tenant_id = str(tenant_id or "").strip()
        self._tenant_overlay: dict = {}
        self._knowledge_text = ""
        self._human_agent = (config.HUMAN_AGENT_NUMBER or "").strip()
        self._notify_whatsapp = (config.NOTIFY_WHATSAPP or "").strip()
        self._business_name = (config.BUSINESS_NAME or "").strip()
        self._closing = False
        self._call_logged = False
        self._transfer_pending = False
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
        self._direction = (direction or "inbound").strip().lower()
        self._followup_purpose = ""
        self._soft_reset_busy = False
        self._farewell_pending = False
        self._farewell_force_task: asyncio.Task | None = None
        self._soft_reset_epoch = time.monotonic()
        self._caller_turns_since_reset = 0
        self._user_spoke_this_cycle = False
        self._caller_voice_active = False
        self._last_caller_loud_at = 0.0
        self._digest_sync_at = 0.0

    def _sync_continuity_digest(self, *, force: bool = False) -> None:
        if self.provider is None:
            return
        now = time.monotonic()
        if not force and (now - self._digest_sync_at) < 1.5:
            return
        self._digest_sync_at = now
        digest = build_call_digest(
            self._transcript,
            caller_intent=self._guess_intent(),
            max_chars=config.GEMINI_DIGEST_MAX_CHARS,
        )
        self.provider.set_continuity_digest(digest)

    def _caller_is_listening_window(self) -> bool:
        """True while caller may still be talking (do not nudge or treat turn as done)."""
        now = time.monotonic()
        if self._caller_voice_active:
            return True
        return (now - self._last_caller_loud_at) < config.CALLER_LISTEN_GRACE_SEC

    def _note_caller_speech_energy(self, rms: int) -> None:
        """Track caller speech; start nudge timer only after a clear pause."""
        now = time.monotonic()
        if rms >= config.SPEECH_RMS_THRESHOLD:
            self._caller_voice_active = True
            self._last_caller_loud_at = now
            self._awaiting_ai_since = None
            self._nudge_count = 0
            return
        if not self._caller_voice_active:
            return
        if (now - self._last_caller_loud_at) < config.SPEECH_END_GAP_SEC:
            return
        self._caller_voice_active = False
        if self._farewell_pending or self._ai_speaking:
            return
        if self._awaiting_ai_since is None:
            self._awaiting_ai_since = now

    def _bridge_needs_soft_reset(self) -> bool:
        if config.GEMINI_SOFT_RESET_EVERY_TURNS <= 0 and config.GEMINI_SOFT_RESET_EVERY_SEC <= 0:
            return False
        elapsed = time.monotonic() - self._soft_reset_epoch
        if (
            config.GEMINI_SOFT_RESET_EVERY_SEC > 0
            and elapsed >= config.GEMINI_SOFT_RESET_EVERY_SEC
        ):
            return True
        if (
            config.GEMINI_SOFT_RESET_EVERY_TURNS > 0
            and self._caller_turns_since_reset >= config.GEMINI_SOFT_RESET_EVERY_TURNS
        ):
            return True
        return False

    async def _load_tenant(self) -> None:
        """Pull per-business settings from Node if BACKEND_URL is set."""
        from backend import get_tenant_config

        row = await get_tenant_config(number=self._called, tenant_id=self._tenant_id)
        if not row:
            return
        self._tenant_overlay = row
        if row.get("tenant_id") is not None:
            self._tenant_id = str(row.get("tenant_id"))
        if row.get("knowledge_text"):
            self._knowledge_text = str(row["knowledge_text"]).strip()
        if row.get("human_agent_number"):
            self._human_agent = str(row["human_agent_number"]).strip()
        if row.get("notify_whatsapp"):
            self._notify_whatsapp = str(row["notify_whatsapp"]).strip()
        if row.get("business_name"):
            self._business_name = str(row["business_name"]).strip()
        if row.get("phone_number") and not self._called:
            self._called = self._normalize_phone(str(row["phone_number"])) or self._called

    async def run(self) -> None:
        await self.tel_ws.accept()
        await self._load_tenant()
        self.provider = make_provider()
        self.provider.set_call_direction(self._direction)
        if self._followup_purpose:
            self.provider.set_followup_purpose(self._followup_purpose)
        if self._tenant_overlay:
            self.provider.set_tenant_overlay(self._tenant_overlay)

        # Read Plivo WebSocket immediately — waiting for Gemini first drops outbound calls.
        tel_task = asyncio.create_task(self._telephony_to_provider(), name="tel->ai")
        try:
            await self.provider.connect()
        except Exception:
            log.exception("AI provider failed to connect — closing call")
            tel_task.cancel()
            await self._teardown()
            return

        log.info(
            "Bridge established (telephony=%s, ai=%s, direction=%s)",
            self.telephony,
            config.AI_PROVIDER,
            self._direction,
        )
        self._touch()

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
            if self._farewell_pending:
                continue
            if self._awaiting_ai_since is None or self._ai_speaking:
                continue
            if self._caller_is_listening_window():
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

    async def _request_transfer(self, summary: str = "", reason: str = "") -> None:
        """Human handover: default = callback (missed call + WhatsApp). Optional live transfer."""
        if self._transfer_pending:
            return
        if not self._human_agent:
            log.error("transfer_to_human requested but no human agent number")
            return
        self._transfer_pending = True
        if summary:
            self._end_summary = summary
        elif not self._end_summary:
            self._end_summary = self._fallback_summary()

        mode = (config.HUMAN_HANDOVER_MODE or "callback").strip().lower()
        if mode != "transfer":
            await self._request_human_callback(reason=reason)
            return

        self._end_reason = "transferred"
        self._follow_up = "human_agent"

        async def _do_live() -> None:
            await asyncio.sleep(config.TRANSFER_GRACE_SEC)
            try:
                await self._notify_call_ended()
            except Exception:  # noqa: BLE001
                log.exception("Failed to log call before transfer")
            if self.telephony == "plivo" and self.call_id:
                try:
                    from plivo_client import configured, redirect_call

                    if configured():
                        from urllib.parse import quote

                        agent_qs = quote(self._human_agent)
                        await redirect_call(
                            self.call_id,
                            f"https://{config.PUBLIC_HOST.rstrip('/')}/plivo/transfer?agent={agent_qs}",
                        )
                        self._closing = True
                        return
                    log.error("Plivo creds missing — cannot redirect call for transfer")
                except Exception:  # noqa: BLE001
                    log.exception("Plivo transfer redirect failed")
            self._closing = True
            try:
                await self.tel_ws.close()
            except Exception:  # noqa: BLE001
                pass

        self._hangup_task = asyncio.create_task(_do_live(), name="transfer")

    async def _request_human_callback(self, reason: str = "") -> None:
        """No live connect. Ping agent + WhatsApp; hang up customer. Agent calls back off-Plivo."""
        self._end_reason = "callback_requested"
        self._follow_up = "human_callback"
        caller = self.caller or ""

        async def _do_callback() -> None:
            await asyncio.sleep(config.TRANSFER_GRACE_SEC)
            try:
                from tools import call_n8n

                await call_n8n(
                    "human_callback",
                    {
                        "reason": reason or "caller requested a human",
                        "summary": self._end_summary or "",
                        "caller": caller,
                        "agent_number": self._human_agent,
                    },
                    {
                        "call_id": self._stable_call_id(),
                        "from": caller,
                        "direction": self._direction,
                    },
                )
            except Exception:  # noqa: BLE001
                log.exception("human_callback n8n notify failed")
            try:
                from plivo_client import configured, create_missed_call_ping

                if configured() and self._human_agent:
                    await create_missed_call_ping(self._human_agent)
                else:
                    log.warning("Missed-call ping skipped — Plivo not configured")
            except Exception:  # noqa: BLE001
                log.exception("Missed-call ping to agent failed")
            try:
                await self._notify_call_ended()
            except Exception:  # noqa: BLE001
                log.exception("Failed to log call after human callback")
            self._closing = True
            try:
                await self.tel_ws.close()
            except Exception:  # noqa: BLE001
                pass

        self._hangup_task = asyncio.create_task(_do_callback(), name="human-callback")

    async def _on_caller_farewell(self, text: str) -> None:
        if self._closing or self._farewell_pending:
            return
        self._farewell_pending = True
        low = text.lower()
        if any(w in low for w in ("bye", "alvida", "goodbye", "good bye")):
            self._end_reason = "goodbye"
        else:
            self._end_reason = "thanks"
        self._awaiting_ai_since = None
        self._nudge_count = 99
        log.info("Caller farewell detected — prompting end_call")
        if self.provider is not None:
            try:
                await self.provider.nudge(
                    "The caller wants to END the call now (thanks / goodbye / no more help). "
                    "Say ONE short warm farewell in their language. "
                    "Immediately call end_call with summary and caller_intent. "
                    "Do NOT ask 'anything else?' or start a new topic."
                )
            except Exception:  # noqa: BLE001
                log.exception("farewell nudge failed")
        if self._farewell_force_task and not self._farewell_force_task.done():
            self._farewell_force_task.cancel()
        self._farewell_force_task = asyncio.create_task(
            self._farewell_force_hangup(14.0), name="farewell-force"
        )

    async def _farewell_force_hangup(self, delay: float) -> None:
        await asyncio.sleep(delay)
        if self._closing:
            return
        if self._hangup_task and not self._hangup_task.done():
            return
        if not self._end_summary:
            self._end_summary = build_owner_summary(
                self._transcript,
                caller_intent=self._guess_intent(),
                follow_up=self._follow_up,
                appointment_booked=self._appointment_booked,
                lead_captured=self._lead_captured,
            )
        log.info("Farewell timeout — hanging up without end_call tool")
        await self._request_hangup()

    async def _maybe_finish_after_farewell(self) -> None:
        if not self._farewell_pending or self._closing:
            return
        if self._hangup_task and not self._hangup_task.done():
            return
        await asyncio.sleep(2.0)
        if self._closing:
            return
        if self._hangup_task and not self._hangup_task.done():
            return
        if not self._end_summary:
            self._end_summary = build_owner_summary(
                self._transcript,
                caller_intent=self._guess_intent(),
                follow_up=self._follow_up,
                appointment_booked=self._appointment_booked,
                lead_captured=self._lead_captured,
            )
        log.info("Farewell turn complete — scheduling hangup")
        await self._request_hangup()

    # ---- telephony -> AI ------------------------------------------------
    async def _telephony_to_provider(self) -> None:
        assert self.provider is not None
        try:
            while not self._closing:
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
                            rms = audio.pcm_rms(pcm8k)
                            if rms >= config.SPEECH_RMS_THRESHOLD:
                                self._touch()
                            self._note_caller_speech_energy(rms)
                            await self.provider.send_caller_audio(pcm8k)
                    continue

                if kind == "stop":
                    log.info("%s sent stop; ending call", self.telephony)
                    self._end_reason = self._end_reason or "hangup"
                    break
        except WebSocketDisconnect:
            log.info("%s WebSocket disconnected", self.telephony)
        except RuntimeError as exc:
            msg = str(exc).lower()
            if self._closing or "not connected" in msg or "disconnect" in msg or "accept" in msg:
                log.info("%s WebSocket closed during hangup/transfer", self.telephony)
            else:
                log.exception("Error in telephony->provider loop")
        except Exception:  # noqa: BLE001
            log.exception("Error in telephony->provider loop")

    def _on_start(self, event: dict) -> None:
        start = event.get("start", {}) or {}
        if self.telephony == "exotel":
            self.stream_id = (
                start.get("stream_sid") or event.get("stream_sid") or start.get("streamSid")
            )
            self.call_id = start.get("call_sid") or start.get("callSid")
            if not self.caller:
                self.caller = start.get("from") or start.get("From")
            mf = start.get("media_format") or {}
            try:
                rate = int(mf.get("sample_rate") or config.EXOTEL_SAMPLE_RATE)
            except (TypeError, ValueError):
                rate = config.EXOTEL_SAMPLE_RATE
            self._set_tel_rate(rate)
        else:
            self.stream_id = start.get("streamId") or start.get("stream_sid")
            self.call_id = start.get("callId") or start.get("call_sid")
            if not self.caller:
                self.caller = self._caller_from_plivo_start(event, start)
            self._set_tel_rate(config.PLIVO_SAMPLE_RATE)
        if self.caller:
            self.caller = self._normalize_phone(self.caller)
        if not self.caller:
            self._apply_cached_caller()
        log.info(
            "Stream start call_id=%s stream_id=%s from=%s direction=%s",
            self.call_id,
            self.stream_id,
            self.caller or "-",
            self._direction,
        )
        if not self.caller and self.telephony == "plivo":
            asyncio.create_task(self._resolve_caller_from_plivo(), name="resolve-caller")

    async def _resolve_caller_from_plivo(self) -> None:
        if self.caller:
            return
        # stream-status often lands a moment after WS start
        for delay in (0.0, 0.4, 1.0, 2.0):
            if delay:
                await asyncio.sleep(delay)
            if self._closing and self.caller:
                return
            self._apply_cached_caller()
            if self.caller:
                return
        if not self.call_id:
            return
        try:
            from plivo_client import get_call, pick_remote_number

            data = await get_call(self.call_id)
            phone = pick_remote_number(data, direction=self._direction)
            phone = self._normalize_phone(phone)
            if phone:
                self.caller = phone
                log.info("Resolved caller via Plivo API call_id=%s from=%s", self.call_id, phone)
            else:
                log.warning("No remote number yet call_id=%s (CDR may lag)", self.call_id)
        except Exception:  # noqa: BLE001
            log.exception("Failed to resolve caller via Plivo API")

    def _apply_cached_caller(self) -> None:
        """Use From saved from /plivo/answer or /plivo/stream-status."""
        if self.caller:
            return
        try:
            from call_meta import lookup, pick_caller

            row = lookup(call_uuid=self.call_id or "", stream_id=self.stream_id or "")
            phone = pick_caller(row, direction=self._direction)
            phone = self._normalize_phone(phone)
            if phone:
                self.caller = phone
                log.info(
                    "Caller from call_meta call_id=%s stream_id=%s from=%s",
                    self.call_id,
                    self.stream_id,
                    phone,
                )
        except Exception:  # noqa: BLE001
            log.exception("call_meta lookup failed")

    @staticmethod
    def _normalize_phone(raw: str | None) -> str | None:
        s = (raw or "").strip()
        if not s:
            return None
        digits = "".join(ch for ch in s if ch.isdigit())
        if not digits:
            return None
        if len(digits) == 10:
            digits = "91" + digits
        return f"+{digits}" if not s.startswith("+") else f"+{digits}"

    def _caller_from_plivo_start(self, event: dict, start: dict) -> str | None:
        """Plivo WS start often omits From — check start, event, extra_headers."""
        if self._direction == "outbound":
            keys = ("to", "To", "caller", "Caller")
        else:
            keys = ("from", "From", "caller", "Caller")
        for key in keys:
            val = start.get(key) or event.get(key)
            if val and str(val).strip():
                return str(val).strip()
        headers = event.get("extra_headers") or start.get("extra_headers") or ""
        parsed = self._parse_extra_headers(str(headers))
        if parsed.get("caller"):
            return parsed["caller"]
        if self._direction == "outbound" and parsed.get("to"):
            return parsed["to"]
        return None

    @staticmethod
    def _parse_extra_headers(raw: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for part in (raw or "").split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, _, v = part.partition("=")
            k, v = k.strip().lower(), v.strip()
            if k and v:
                out[k] = v
        return out

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
                    self._awaiting_ai_since = None
                    self._nudge_count = 0
                    self._caller_voice_active = True
                    self._last_caller_loud_at = time.monotonic()
                    await self._barge_in()
                elif isinstance(ev, TurnComplete):
                    self._ai_speaking = False
                    self._awaiting_ai_since = None
                    self._nudge_count = 0
                    self._touch()
                    if self.telephony == "exotel":
                        await self._flush_exotel()
                    if self._user_spoke_this_cycle:
                        self._caller_turns_since_reset += 1
                        self._user_spoke_this_cycle = False
                        self._sync_continuity_digest(force=True)
                    if self._farewell_pending:
                        await self._maybe_finish_after_farewell()
                    else:
                        await self._maybe_soft_reset_session()
                elif isinstance(ev, TranscriptDelta):
                    if ev.text:
                        merge_transcript_line(self._transcript, ev.role, ev.text)
                        self._sync_continuity_digest()
                        if ev.role == "user":
                            self._user_spoke_this_cycle = True
                            self._touch()
                            if user_wants_to_end(ev.text):
                                asyncio.create_task(
                                    self._on_caller_farewell(ev.text), name="farewell"
                                )
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
        payload_ctx = {
            **ctx,
            "direction": self._direction,
            "language": detect_language_hint(self._transcript),
            "tenant_id": self._tenant_id,
            "knowledge_text": self._knowledge_text,
            "notify_whatsapp": self._notify_whatsapp,
            "business_name": self._business_name,
        }
        result = await dispatch_tool(call.name, call.arguments, payload_ctx)
        await self.provider.send_tool_result(call.call_id, call.name, result)

        if call.name == "end_call":
            self._end_reason = str(call.arguments.get("reason") or "thanks")
            self._end_summary = str(call.arguments.get("summary") or "")
            self._caller_intent = str(call.arguments.get("caller_intent") or "")
            self._farewell_pending = True
            if self._farewell_force_task and not self._farewell_force_task.done():
                self._farewell_force_task.cancel()
            log.info("end_call reason=%s", self._end_reason)
            await self._request_hangup()
            return

        if call.name == "transfer_to_human":
            summary = str(call.arguments.get("summary") or "")
            reason = str(call.arguments.get("reason") or "caller request")
            self._caller_intent = reason
            self._farewell_pending = True
            log.info(
                "transfer_to_human mode=%s reason=%s",
                config.HUMAN_HANDOVER_MODE,
                reason,
            )
            await self._request_transfer(summary=summary, reason=reason)
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
        if self._closing or self._soft_reset_busy or self.provider is None or self._farewell_pending:
            return
        if not self._bridge_needs_soft_reset():
            return
        self._soft_reset_busy = True
        try:
            digest = build_call_digest(
                self._transcript,
                caller_intent=self._guess_intent(),
                max_chars=config.GEMINI_DIGEST_MAX_CHARS,
            )
            await self.provider.refresh_session(digest)
            self._soft_reset_epoch = time.monotonic()
            self._caller_turns_since_reset = 0
            log.info("Soft session reset completed call_id=%s", self.call_id)
        except Exception:  # noqa: BLE001
            log.exception("Soft session reset failed")
        finally:
            self._soft_reset_busy = False

    def _stable_call_id(self) -> str:
        if self.call_id:
            return str(self.call_id)
        return f"voice-{int(self._started_at * 1000)}"

    def _guess_intent(self) -> str:
        if self._caller_intent:
            return self._caller_intent
        return infer_topic_label(self._transcript, "")

    def _friendly_outcome(self) -> str:
        mapping = {
            "thanks": "Caller said thanks / done",
            "goodbye": "Caller said goodbye",
            "completed": "Request completed",
            "silence": "Ended after silence",
            "max_duration": "Max call time reached",
            "hangup": "Caller hung up",
            "transferred": "Transferred to human agent",
            "callback_requested": "Callback requested — agent will call back",
            "other": "Ended",
        }
        return mapping.get(self._end_reason, self._end_reason or "Ended")

    def _fallback_summary(self) -> str:
        return build_owner_summary(
            self._transcript,
            caller_intent=self._guess_intent(),
            follow_up=self._follow_up,
            appointment_booked=self._appointment_booked,
            lead_captured=self._lead_captured,
        )

    def _format_duration(self, seconds: int) -> str:
        minutes, sec = divmod(max(0, seconds), 60)
        if minutes:
            return f"{minutes} min {sec} sec"
        return f"{sec} sec"

    async def _notify_call_ended(self) -> None:
        if self._call_logged:
            return
        # Last chance — Plivo start event often has no From
        if not self.caller and self.call_id and self.telephony == "plivo":
            await self._resolve_caller_from_plivo()
        self._call_logged = True
        duration = int(time.monotonic() - self._started_at)
        intent = self._guess_intent()
        next_step = sheet_next_step_label(
            self._follow_up,
            appointment_booked=self._appointment_booked,
            lead_captured=self._lead_captured,
        )
        outcome = self._friendly_outcome()
        summary = pick_summary_for_sheet(
            self._end_summary,
            self._transcript,
            caller_intent=intent,
            follow_up=self._follow_up,
            appointment_booked=self._appointment_booked,
            lead_captured=self._lead_captured,
            outcome=outcome,
        )
        conversation_full = format_conversation_full(self._transcript)
        transcript_turns = count_transcript_turns(self._transcript)
        try:
            from zoneinfo import ZoneInfo

            now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
        except Exception:  # noqa: BLE001
            now_ist = datetime.now(timezone.utc)
        date_str = now_ist.strftime("%Y-%m-%d")
        time_str = now_ist.strftime("%I:%M %p")

        args = {
            "call_id": self._stable_call_id(),
            "date": date_str,
            "time": time_str,
            "time_ist": time_str,
            "caller": self.caller or "",
            "caller_phone": self.caller or "",
            "duration": self._format_duration(duration),
            "duration_sec": duration,
            "topic": intent,
            "summary": summary,
            "next_step": next_step,
            "outcome": outcome,
            "conversation_full": conversation_full,
            "transcript_turns": transcript_turns,
            "notify_whatsapp": self._notify_whatsapp or None,
            "direction": self._direction,
            "tenant_id": self._tenant_id or None,
            "called": self._called or None,
            "business_name": self._business_name or None,
        }
        ctx = {
            "call_id": self._stable_call_id(),
            "from": self.caller,
            "direction": self._direction,
            "tenant_id": self._tenant_id,
            "knowledge_text": self._knowledge_text,
            "notify_whatsapp": self._notify_whatsapp,
            "business_name": self._business_name,
        }
        try:
            await call_n8n("call_ended", args, ctx)
        except Exception:  # noqa: BLE001
            log.exception("Failed to post call_ended to n8n")
        try:
            from backend import post_call_ended

            await post_call_ended(args)
        except Exception:  # noqa: BLE001
            log.exception("Failed to post call_ended to Node")

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


async def run_bridge(
    ws: WebSocket,
    telephony: str | None = None,
    direction: str = "inbound",
    caller: str | None = None,
    purpose: str | None = None,
    called: str | None = None,
    tenant_id: str | None = None,
) -> None:
    tel = (telephony or config.TELEPHONY_PROVIDER).lower()
    bridge = CallBridge(
        ws,
        telephony=tel,
        direction=direction,
        caller=caller,
        called=called,
        tenant_id=tenant_id,
    )
    if purpose:
        bridge._followup_purpose = purpose.strip()
    await bridge.run()
