"""FastAPI entrypoint: telephony answer / WS URL, health, and call audio WebSockets."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, PlainTextResponse

import config
from bridge import run_bridge
from plivo_xml import answer_xml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title="AI Voice Receptionist Bridge")


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
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "ai": config.AI_PROVIDER,
        "telephony": config.TELEPHONY_PROVIDER,
    }


# ---- Plivo (fallback once KYC / compliance is done) ---------------------

@app.api_route("/plivo/answer", methods=["GET", "POST"])
async def plivo_answer(request: Request) -> PlainTextResponse:
    """Plivo Answer URL -> Stream XML pointing at /plivo/stream."""
    if not config.PUBLIC_HOST:
        return PlainTextResponse("PUBLIC_HOST is not configured", status_code=500)
    return PlainTextResponse(answer_xml(), media_type="application/xml")


@app.websocket("/plivo/stream")
@app.websocket("/stream")  # kept for older Plivo XML that still uses /stream
async def plivo_stream(ws: WebSocket) -> None:
    await run_bridge(ws, telephony="plivo")


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
