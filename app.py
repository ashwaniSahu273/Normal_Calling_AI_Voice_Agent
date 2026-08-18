"""FastAPI entrypoint: telephony answer / WS URL, health, and call audio WebSockets."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse

import config
from bridge import run_bridge
from plivo_xml import (
    agent_first_xml,
    answer_xml,
    dial_fallback_xml,
    missed_call_hangup_xml,
    transfer_xml,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="AI Voice Receptionist Bridge")
log = logging.getLogger("voice-agent.app")


class _StripPathWhitespaceMiddleware:
    """Plivo Answer URL pasted with trailing space → /plivo/answer%20 → 404 busy tone.

    Pure ASGI — BaseHTTPMiddleware eats POST bodies (From/To never arrive).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path") or ""
            stripped = path.rstrip()
            if stripped != path:
                log.warning("Trimmed trailing whitespace from URL path %r", path)
                scope = dict(scope)
                scope["path"] = stripped
                raw = scope.get("raw_path")
                if isinstance(raw, (bytes, bytearray)):
                    scope["raw_path"] = bytes(raw).rstrip()
        await self.app(scope, receive, send)


@app.on_event("startup")
async def _startup() -> None:
    config.validate()
    import knowledge

    knowledge.load_business_knowledge(force=True)
    config.SYSTEM_PROMPT = knowledge.build_system_prompt(force=True)
    logging.getLogger("voice-agent").info(
        "Started ai=%s telephony=%s voice=%s silence_ms=%s knowledge_chars=%s",
        config.AI_PROVIDER,
        config.TELEPHONY_PROVIDER,
        config.VOICE,
        config.GEMINI_SILENCE_MS,
        len(knowledge.load_business_knowledge()),
    )


@app.get("/health")
async def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "ai": config.AI_PROVIDER,
        "telephony": config.TELEPHONY_PROVIDER,
        "knowledge_profile": config.KNOWLEDGE_PROFILE,
        "business_name": config.BUSINESS_NAME,
        "agent_first": config.AGENT_FIRST_ENABLED and bool(config.HUMAN_AGENT_NUMBER),
        "human_handover": config.HUMAN_HANDOVER_MODE,
        "human_transfer": bool(config.HUMAN_AGENT_NUMBER),
        "backend": bool((config.BACKEND_URL or "").strip()),
    }


@app.get("/plivo/handover-mode")
async def get_handover_mode() -> JSONResponse:
    """Current human handover: callback (missed call + WhatsApp) or transfer (live pickup)."""
    return JSONResponse(
        {
            "ok": True,
            "mode": config.HUMAN_HANDOVER_MODE,
            "options": {
                "callback": "Missed call + WhatsApp. Agent calls customer back (no live Plivo minutes).",
                "transfer": "Agent phone rings live. Pick up and talk (Plivo minutes on both legs).",
            },
        }
    )


@app.post("/plivo/handover-mode")
async def set_handover_mode(request: Request) -> JSONResponse:
    """Switch handover without restart. Header x-voice-secret. Body: {\"mode\":\"callback\"|\"transfer\"}."""
    if not _check_outbound_secret(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    if not isinstance(body, dict):
        body = {}
    mode = str(body.get("mode") or request.query_params.get("mode") or "").strip().lower()
    try:
        applied = config.set_handover_mode(mode)
    except ValueError as exc:
        return JSONResponse(
            {"ok": False, "error": str(exc), "mode": config.HUMAN_HANDOVER_MODE},
            status_code=400,
        )
    import knowledge

    config.SYSTEM_PROMPT = knowledge.build_system_prompt(force=True)
    log.info("Human handover mode set to %s", applied)
    return JSONResponse({"ok": True, "mode": applied})


@app.get("/plivo/knowledge-profile")
async def get_knowledge_profile() -> JSONResponse:
    """Which knowledge base the AI uses (resiliencesoft | resiliohub | custom)."""
    return JSONResponse(
        {
            "ok": True,
            "profile": config.KNOWLEDGE_PROFILE,
            "business_name": config.BUSINESS_NAME,
            "website": config.BUSINESS_WEBSITE,
            "knowledge_file": config.BUSINESS_CONTEXT_FILE,
            "options": config.list_knowledge_profiles(),
        }
    )


@app.post("/plivo/knowledge-profile")
async def set_knowledge_profile(request: Request) -> JSONResponse:
    """Switch knowledge base without restart. Header x-voice-secret. Body: {\"profile\":\"resiliohub\"}."""
    if not _check_outbound_secret(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    if not isinstance(body, dict):
        body = {}
    profile = str(
        body.get("profile") or body.get("mode") or request.query_params.get("profile") or ""
    ).strip().lower()
    try:
        applied = config.set_knowledge_profile(profile)
    except ValueError as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": str(exc),
                "profile": config.KNOWLEDGE_PROFILE,
                "options": config.list_knowledge_profiles(),
            },
            status_code=400,
        )
    import knowledge

    knowledge.load_business_knowledge(force=True)
    config.SYSTEM_PROMPT = knowledge.build_system_prompt(force=True)
    log.info(
        "Knowledge profile set to %s (%s, file=%s)",
        applied,
        config.BUSINESS_NAME,
        config.BUSINESS_CONTEXT_FILE,
    )
    return JSONResponse(
        {
            "ok": True,
            "profile": applied,
            "business_name": config.BUSINESS_NAME,
            "website": config.BUSINESS_WEBSITE,
            "knowledge_file": config.BUSINESS_CONTEXT_FILE,
            "knowledge_chars": len(knowledge.load_business_knowledge()),
        }
    )

async def _plivo_params(request: Request) -> dict[str, str]:
    """Parse Plivo query + urlencoded/JSON body once. Stdlib only — no python-multipart."""
    cached = getattr(request.state, "plivo_params", None)
    if isinstance(cached, dict):
        return cached
    try:
        raw = await request.body()
    except Exception:  # noqa: BLE001
        raw = b""
    from plivo_form import parse_plivo_payload

    params = parse_plivo_payload(
        query=list(request.query_params.multi_items()),
        body=raw,
        content_type=request.headers.get("content-type") or "",
    )
    request.state.plivo_params = params
    return params


async def _plivo_form_value_async(request: Request, *keys: str) -> str:
    from plivo_form import pick_plivo_value

    params = await _plivo_params(request)
    return pick_plivo_value(params, *keys)


async def _plivo_caller_from_request(request: Request, *, direction: str) -> str:
    """Customer phone: inbound=From, outbound=To (callee)."""
    frm = await _plivo_form_value_async(request, "From", "from", "Caller", "caller")
    to = await _plivo_form_value_async(request, "To", "to", "Called", "called")
    direction = (direction or "inbound").strip().lower()
    if direction == "outbound":
        return to or frm
    return frm or to


def _check_outbound_secret(request: Request) -> bool:
    secret = (config.OUTBOUND_API_SECRET or "").strip()
    if not secret:
        return False
    header = (request.headers.get("x-voice-secret") or "").strip()
    if header and header == secret:
        return True
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer ") and auth[7:].strip() == secret:
        return True
    return False


# ---- Plivo (fallback once KYC / compliance is done) ---------------------

@app.api_route("/plivo/answer", methods=["GET", "POST"])
async def plivo_answer(request: Request) -> PlainTextResponse:
    """Plivo Answer URL → agent-first, AI stream, or outbound stream."""
    if not config.PUBLIC_HOST:
        return PlainTextResponse("PUBLIC_HOST is not configured", status_code=500)

    mode = (request.query_params.get("mode") or "").strip().lower()
    direction = (request.query_params.get("direction") or "inbound").strip().lower()
    ctx = (request.query_params.get("ctx") or "").strip()
    tenant_id = (request.query_params.get("tenant_id") or "").strip()
    caller_from = ""
    caller_to = ""

    try:
        call_uuid = await _plivo_form_value_async(
            request, "CallUUID", "call_uuid", "Uuid", "uuid"
        )
        caller_from = await _plivo_caller_from_request(request, direction=direction)
        caller_to = await _plivo_form_value_async(request, "To", "to")
        raw_from = await _plivo_form_value_async(request, "From", "from")
        # Outbound ctx always has callee — prefer when Answer form misses To
        if not caller_from and ctx:
            from outbound_ctx import get as get_outbound_ctx

            row = get_outbound_ctx(ctx)
            if row and row.get("to"):
                caller_from = str(row["to"]).strip()
            if not tenant_id and row and row.get("tenant_id"):
                tenant_id = str(row["tenant_id"]).strip()
        if not caller_to and direction != "outbound":
            caller_to = (config.PLIVO_FROM_NUMBER or "").strip()
        if call_uuid and (caller_from or raw_from or caller_to):
            from call_meta import remember

            remember(
                call_uuid=call_uuid,
                caller=caller_from or raw_from,
                to=caller_to,
                direction=direction,
            )
        log.info(
            "Plivo answer call_uuid=%s from=%s to=%s mode=%s direction=%s ctx=%s",
            call_uuid or "-",
            caller_from or "-",
            caller_to or "-",
            mode or "-",
            direction,
            ctx or "-",
        )
        if not caller_from:
            log.warning(
                "Plivo answer missing caller number direction=%s mode=%s",
                direction,
                mode or "-",
            )
    except Exception:  # noqa: BLE001
        log.exception("Plivo answer param parse failed")

    if mode == "ai" or direction == "outbound":
        return PlainTextResponse(
            answer_xml(
                direction=direction,
                caller=caller_from,
                ctx=ctx,
                called=caller_to,
                tenant_id=tenant_id,
            ),
            media_type="application/xml",
        )

    if (
        config.AGENT_FIRST_ENABLED
        and config.HUMAN_AGENT_NUMBER
        and direction == "inbound"
    ):
        return PlainTextResponse(agent_first_xml(), media_type="application/xml")

    return PlainTextResponse(
        answer_xml(
            direction=direction,
            caller=caller_from,
            called=caller_to,
            tenant_id=tenant_id,
        ),
        media_type="application/xml",
    )


@app.api_route("/plivo/dial-status", methods=["GET", "POST"])
async def plivo_dial_status(request: Request) -> PlainTextResponse:
    """Agent-first: human did not answer → fall back to AI."""
    status = (
        await _plivo_form_value_async(
            request,
            "DialStatus",
            "DialActionStatus",
            "dial_status",
        )
    ).lower()
    log.info("Plivo dial-status status=%s", status or "unknown")
    if status in ("completed", "answer", "answered"):
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml",
        )
    return PlainTextResponse(dial_fallback_xml(), media_type="application/xml")


@app.api_route("/plivo/missed-call", methods=["GET", "POST"])
async def plivo_missed_call(_request: Request) -> PlainTextResponse:
    """Agent ping answer URL — hang up immediately (missed-call alert)."""
    return PlainTextResponse(missed_call_hangup_xml(), media_type="application/xml")


@app.api_route("/plivo/transfer", methods=["GET", "POST"])
async def plivo_transfer(request: Request) -> PlainTextResponse:
    """Live AI → human Dial (only when HUMAN_HANDOVER_MODE=transfer)."""
    agent = (
        await _plivo_form_value_async(request, "agent", "Agent")
        or (request.query_params.get("agent") or "").strip()
        or config.HUMAN_AGENT_NUMBER
    )
    if not agent:
        return PlainTextResponse(
            "HUMAN_AGENT_NUMBER is not configured", status_code=500
        )
    return PlainTextResponse(transfer_xml(agent=agent), media_type="application/xml")


@app.api_route("/plivo/stream-status", methods=["GET", "POST"])
async def plivo_stream_status(request: Request) -> PlainTextResponse:
    """Plivo Stream lifecycle callbacks — log DroppedStream for debugging."""
    event = await _plivo_form_value_async(request, "Event", "event")
    err = await _plivo_form_value_async(request, "Error", "error")
    call_uuid = await _plivo_form_value_async(request, "CallUUID", "call_uuid")
    stream_id = await _plivo_form_value_async(request, "StreamID", "StreamId", "stream_id")
    frm = await _plivo_form_value_async(request, "From", "from")
    to = await _plivo_form_value_async(request, "To", "to")
    direction = (
        await _plivo_form_value_async(request, "Direction", "direction") or "inbound"
    ).strip().lower()
    # Stream-status includes From/To — primary source when WS start has no caller
    if call_uuid or stream_id:
        from call_meta import remember

        remote = to if direction == "outbound" else frm
        if not remote:
            remote = frm or to
        remember(
            call_uuid=call_uuid,
            stream_id=stream_id,
            caller=remote,
            to=to,
            direction=direction,
        )
    if event:
        log.info(
            "Plivo stream-status event=%s call_uuid=%s stream_id=%s from=%s to=%s error=%s",
            event,
            call_uuid,
            stream_id,
            frm or "-",
            to or "-",
            err or "-",
        )
    return PlainTextResponse("ok")


async def _outbound_body(request: Request) -> dict:
    """Parse outbound payload from JSON, form, or query (Postman / curl friendly)."""
    import json as _json

    ctype = (request.headers.get("content-type") or "").lower()
    data: dict = {}

    # Prefer JSON when Content-Type says so (or empty / unknown).
    if "application/json" in ctype or not ctype or "text/plain" in ctype:
        try:
            raw = await request.json()
        except Exception:  # noqa: BLE001
            raw = None
        if isinstance(raw, dict):
            data = raw
        elif isinstance(raw, str):
            # Double-encoded JSON string body: "{\"to\":\"+91...\"}"
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    data = parsed
            except Exception:  # noqa: BLE001
                pass

    if not data and ("form" in ctype or "urlencoded" in ctype or "multipart" in ctype):
        try:
            form = await request.form()
            data = {k: str(v) for k, v in form.items()}
        except Exception:  # noqa: BLE001
            pass

    # Query params as last resort (easy curl tests).
    if not data.get("to"):
        q = request.query_params
        if q.get("to"):
            data = {
                "to": q.get("to") or data.get("to", ""),
                "purpose": q.get("purpose") or data.get("purpose", ""),
                "tenant_id": q.get("tenant_id") or data.get("tenant_id", ""),
            }
    return data


@app.post("/plivo/outbound")
async def plivo_outbound(request: Request) -> JSONResponse:
    """Start outbound call — AI calls the customer. Requires x-voice-secret header."""
    if not _check_outbound_secret(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await _outbound_body(request)
    to = str(body.get("to") or "").strip()
    purpose = str(body.get("purpose") or "").strip()
    tenant_id = str(body.get("tenant_id") or "").strip()
    if not to:
        return JSONResponse(
            {
                "error": "to is required (E.164)",
                "hint": 'Send JSON: {"to":"+91XXXXXXXXXX","purpose":"..."} with Content-Type: application/json',
            },
            status_code=400,
        )

    try:
        from backend import get_tenant_config
        from plivo_client import create_outbound_call

        row = await get_tenant_config(tenant_id=tenant_id) if tenant_id else None
        from_number = str((row or {}).get("phone_number") or "").strip()
        auth_id = str((row or {}).get("plivo_auth_id") or "").strip()
        auth_token = str((row or {}).get("plivo_auth_token") or "").strip()
        data = await create_outbound_call(
            to,
            purpose=purpose,
            tenant_id=tenant_id,
            from_number=from_number,
            auth_id=auth_id,
            auth_token=auth_token,
        )
        return JSONResponse(
            {
                "ok": True,
                "to": to,
                "direction": "outbound",
                "purpose": purpose or None,
                "tenant_id": tenant_id or None,
                "request_uuid": data.get("request_uuid"),
                "message_uuid": data.get("message_uuid"),
            }
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Outbound call failed")
        return JSONResponse({"error": str(exc)}, status_code=502)


@app.websocket("/plivo/stream")
@app.websocket("/stream")  # kept for older Plivo XML that still uses /stream
async def plivo_stream(ws: WebSocket) -> None:
    from outbound_ctx import get as get_outbound_ctx

    direction = (ws.query_params.get("direction") or "inbound").strip().lower()
    caller = (ws.query_params.get("caller") or "").strip() or None
    called = (ws.query_params.get("called") or "").strip() or None
    tenant_id = (ws.query_params.get("tenant_id") or "").strip() or None
    purpose = None
    ctx = (ws.query_params.get("ctx") or "").strip()
    if ctx:
        row = get_outbound_ctx(ctx)
        if row:
            purpose = row.get("purpose") or None
            if not caller and row.get("to"):
                caller = str(row["to"]).strip() or None
            if not tenant_id and row.get("tenant_id"):
                tenant_id = str(row["tenant_id"]).strip() or None
    if not called and direction != "outbound":
        called = (config.PLIVO_FROM_NUMBER or "").strip() or None
    log.info(
        "Plivo stream connect direction=%s caller=%s called=%s tenant_id=%s ctx=%s",
        direction,
        caller or "-",
        called or "-",
        tenant_id or "-",
        ctx or "-",
    )
    await run_bridge(
        ws,
        telephony="plivo",
        direction=direction,
        caller=caller,
        purpose=purpose,
        called=called,
        tenant_id=tenant_id,
    )


# ---- Exotel Voicebot (primary while Plivo compliance is pending) --------

@app.api_route("/exotel/ws-url", methods=["GET", "POST"])
async def exotel_ws_url(request: Request) -> JSONResponse:
    """Dynamic Voicebot URL: return the WSS endpoint Exotel should open.

    Paste https://PUBLIC_HOST/exotel/ws-url into the Voicebot applet URL field,
    or paste the static wss://PUBLIC_HOST/exotel/stream?... directly.
    """
    if not config.PUBLIC_HOST:
        return JSONResponse({"error": "PUBLIC_HOST is not configured"}, status_code=500)
    url = (
        f"wss://{config.PUBLIC_HOST}/exotel/stream"
        f"?sample-rate={config.EXOTEL_SAMPLE_RATE}"
    )
    return JSONResponse({"url": url})


@app.websocket("/exotel/stream")
async def exotel_stream(ws: WebSocket) -> None:
    await run_bridge(ws, telephony="exotel")


app = _StripPathWhitespaceMiddleware(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=config.PORT, reload=False)
