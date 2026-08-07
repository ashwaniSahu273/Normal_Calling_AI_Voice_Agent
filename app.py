"""FastAPI entrypoint: telephony answer / WS URL, health, and call audio WebSockets."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

import config
from bridge import run_bridge
from plivo_xml import agent_first_xml, answer_xml, dial_fallback_xml, transfer_xml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="AI Voice Receptionist Bridge")
log = logging.getLogger("voice-agent.app")


class _StripPathWhitespaceMiddleware(BaseHTTPMiddleware):
    """Plivo Answer URL pasted with trailing space → /plivo/answer%20 → 404 busy tone."""

    async def dispatch(self, request: Request, call_next):
        path = request.scope.get("path", "")
        stripped = path.rstrip()
        if stripped != path:
            log.warning("Trimmed trailing whitespace from URL path %r", path)
            request.scope["path"] = stripped
        return await call_next(request)


app.add_middleware(_StripPathWhitespaceMiddleware)


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
        "agent_first": config.AGENT_FIRST_ENABLED and bool(config.HUMAN_AGENT_NUMBER),
        "human_transfer": bool(config.HUMAN_AGENT_NUMBER),
    }


async def _plivo_form_value_async(request: Request, *keys: str) -> str:
    for key in keys:
        val = request.query_params.get(key)
        if val:
            return str(val).strip()
    try:
        form = await request.form()
        for key in keys:
            val = form.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


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
    caller_from = ""

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
        if call_uuid and (caller_from or raw_from or caller_to):
            from call_meta import remember

            remember(
                call_uuid=call_uuid,
                caller=caller_from or raw_from,
                to=caller_to,
                direction=direction,
            )
        if call_uuid or caller_from:
            log.info(
                "Plivo answer call_uuid=%s from=%s to=%s mode=%s direction=%s ctx=%s",
                call_uuid,
                caller_from or "-",
                caller_to or "-",
                mode or "-",
                direction,
                ctx or "-",
            )
        elif not caller_from:
            log.warning(
                "Plivo answer missing caller number direction=%s mode=%s",
                direction,
                mode or "-",
            )
    except Exception:  # noqa: BLE001
        log.exception("Plivo answer param parse failed")

    if mode == "ai" or direction == "outbound":
        return PlainTextResponse(
            answer_xml(direction=direction, caller=caller_from, ctx=ctx),
            media_type="application/xml",
        )

    if (
        config.AGENT_FIRST_ENABLED
        and config.HUMAN_AGENT_NUMBER
        and direction == "inbound"
    ):
        return PlainTextResponse(agent_first_xml(), media_type="application/xml")

    return PlainTextResponse(
        answer_xml(direction=direction, caller=caller_from),
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


@app.api_route("/plivo/transfer", methods=["GET", "POST"])
async def plivo_transfer(_request: Request) -> PlainTextResponse:
    """Mid-call AI → human handover XML."""
    if not config.HUMAN_AGENT_NUMBER:
        return PlainTextResponse(
            "HUMAN_AGENT_NUMBER is not configured", status_code=500
        )
    return PlainTextResponse(transfer_xml(), media_type="application/xml")


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


@app.post("/plivo/outbound")
async def plivo_outbound(request: Request) -> JSONResponse:
    """Start outbound call — AI calls the customer. Requires x-voice-secret header."""
    if not _check_outbound_secret(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    to = str(body.get("to") or "").strip()
    purpose = str(body.get("purpose") or "").strip()
    if not to:
        return JSONResponse({"error": "to is required (E.164)"}, status_code=400)

    try:
        from plivo_client import configured, create_outbound_call

        if not configured():
            return JSONResponse(
                {"error": "PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN not configured"},
                status_code=503,
            )
        data = await create_outbound_call(to, purpose=purpose)
        return JSONResponse(
            {
                "ok": True,
                "to": to,
                "direction": "outbound",
                "purpose": purpose or None,
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
    purpose = None
    ctx = (ws.query_params.get("ctx") or "").strip()
    if ctx:
        row = get_outbound_ctx(ctx)
        if row:
            purpose = row.get("purpose") or None
            if not caller and row.get("to"):
                caller = str(row["to"]).strip() or None
    log.info(
        "Plivo stream connect direction=%s caller=%s ctx=%s",
        direction,
        caller or "-",
        ctx or "-",
    )
    await run_bridge(ws, telephony="plivo", direction=direction, caller=caller, purpose=purpose)


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=config.PORT, reload=False)
