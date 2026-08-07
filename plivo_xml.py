"""Plivo Voice XML — AI stream, human dial, agent-first fallback."""
from __future__ import annotations

import html
from urllib.parse import quote

import config


def _host_url(path: str) -> str:
    host = (config.PUBLIC_HOST or "").strip().rstrip("/")
    path = path if path.startswith("/") else f"/{path}"
    return f"https://{host}{path}"


def _xml_url(url: str) -> str:
    """Escape & in URLs embedded in XML text or attributes."""
    return html.escape(url, quote=False)


def answer_xml(*, direction: str = "inbound", caller: str = "", ctx: str = "") -> str:
    """Bidirectional mu-law stream → Gemini bridge."""
    direction = (direction or "inbound").strip().lower()
    qs = f"direction={quote(direction)}"
    if caller:
        qs += f"&caller={quote(caller)}"
    if ctx:
        qs += f"&ctx={quote(ctx)}"
    ws_url = _xml_url(f"wss://{config.PUBLIC_HOST}/plivo/stream?{qs}")
    status_cb = _xml_url(_host_url("/plivo/stream-status"))
    # extraHeaders survive even if WS query params get stripped by some proxies
    header_bits = [f"direction={direction}"]
    if caller:
        header_bits.append(f"caller={caller}")
    if ctx:
        header_bits.append(f"ctx={ctx}")
    extra = html.escape(";".join(header_bits), quote=True)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        '  <Stream bidirectional="true" keepCallAlive="true" '
        f'contentType="{config.PLIVO_CONTENT_TYPE};rate={config.PLIVO_SAMPLE_RATE}" '
        f'extraHeaders="{extra}" '
        f'statusCallbackUrl="{status_cb}" statusCallbackMethod="POST">'
        f"{ws_url}</Stream>\n"
        "</Response>\n"
    )


def agent_first_xml() -> str:
    """Ring human agent first; on no-answer/busy → /plivo/dial-status → AI."""
    agent = (config.HUMAN_AGENT_NUMBER or "").strip()
    timeout = max(10, int(config.AGENT_FIRST_TIMEOUT_SEC))
    action = _xml_url(_host_url("/plivo/dial-status"))
    speak = html.escape(
        config.AGENT_FIRST_ANNOUNCEMENT
        or "Please hold while we connect you to our team."
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"  <Speak>{speak}</Speak>\n"
        f'  <Dial action="{action}" method="POST" timeout="{timeout}">\n'
        f"    <Number>{agent}</Number>\n"
        "  </Dial>\n"
        "</Response>\n"
    )


def dial_fallback_xml() -> str:
    """After agent did not answer — connect caller to AI."""
    speak = html.escape(
        config.AGENT_FALLBACK_ANNOUNCEMENT
        or "Our team is unavailable right now. Connecting you to our AI assistant."
    )
    redirect = _xml_url(_host_url("/plivo/answer?mode=ai"))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"  <Speak>{speak}</Speak>\n"
        f'  <Redirect method="GET">{redirect}</Redirect>\n'
        "</Response>\n"
    )


def transfer_xml() -> str:
    """Mid-call handover — dial human agent."""
    agent = (config.HUMAN_AGENT_NUMBER or "").strip()
    speak = html.escape(
        config.TRANSFER_ANNOUNCEMENT or "Please hold while I connect you to our team."
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        f"  <Speak>{speak}</Speak>\n"
        "  <Dial>\n"
        f"    <Number>{agent}</Number>\n"
        "  </Dial>\n"
        "</Response>\n"
    )
