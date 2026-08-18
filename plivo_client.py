"""Plivo REST helpers — outbound calls and mid-call transfer."""
from __future__ import annotations

import logging
from typing import Any

from urllib.parse import quote

import httpx

import config

log = logging.getLogger("voice-agent.plivo")

_BASE = "https://api.plivo.com/v1"


def configured() -> bool:
    return bool(config.PLIVO_AUTH_ID and config.PLIVO_AUTH_TOKEN)


def _auth() -> tuple[str, str]:
    if not configured():
        raise RuntimeError("PLIVO_AUTH_ID and PLIVO_AUTH_TOKEN are required")
    return config.PLIVO_AUTH_ID, config.PLIVO_AUTH_TOKEN


def _public_url(path: str) -> str:
    host = (config.PUBLIC_HOST or "").strip().rstrip("/")
    if not host:
        raise RuntimeError("PUBLIC_HOST is not configured")
    path = path if path.startswith("/") else f"/{path}"
    return f"https://{host}{path}"


async def create_outbound_call(
    to: str,
    *,
    purpose: str = "",
    tenant_id: str = "",
    answer_url: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Dial `to` from PLIVO_FROM_NUMBER; answer URL connects callee to AI stream."""
    from outbound_ctx import store

    from_number = (config.PLIVO_FROM_NUMBER or "").strip()
    if not from_number:
        raise RuntimeError("PLIVO_FROM_NUMBER is not configured")

    # Always store ctx so bridge gets callee number even if Answer form parse fails.
    ctx_id = store(purpose=purpose, to=to.strip(), tenant_id=tenant_id)
    url = answer_url or _public_url("/plivo/answer?direction=outbound")
    url = f"{url}&ctx={quote(ctx_id)}"
    if tenant_id:
        url = f"{url}&tenant_id={quote(tenant_id)}"
    payload: dict[str, str] = {
        "from": from_number,
        "to": to.strip(),
        "answer_url": url,
        "answer_method": "POST",
    }
    if extra_params:
        payload.update(extra_params)

    api = f"{_BASE}/Account/{config.PLIVO_AUTH_ID}/Call/"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(api, data=payload, auth=_auth())
        resp.raise_for_status()
        data = resp.json()
    log.info("Plivo outbound to=%s request_uuid=%s", to, data.get("request_uuid"))
    return data


async def create_missed_call_ping(to: str) -> dict[str, Any]:
    """Ring `to` briefly then drop — missed-call alert. Almost no talk-time charge."""
    from_number = (config.PLIVO_FROM_NUMBER or "").strip()
    if not from_number:
        raise RuntimeError("PLIVO_FROM_NUMBER is not configured")
    ring = max(5, min(25, int(config.MISSED_CALL_RING_SEC)))
    payload: dict[str, str] = {
        "from": from_number,
        "to": to.strip(),
        "answer_url": _public_url("/plivo/missed-call"),
        "answer_method": "POST",
        "ring_timeout": str(ring),
        "time_limit": "2",
    }
    api = f"{_BASE}/Account/{config.PLIVO_AUTH_ID}/Call/"
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(api, data=payload, auth=_auth())
        resp.raise_for_status()
        data = resp.json()
    log.info("Plivo missed-call ping to=%s request_uuid=%s ring=%ss", to, data.get("request_uuid"), ring)
    return data


async def redirect_call(call_uuid: str, answer_url: str, *, method: str = "GET") -> dict[str, Any]:
    """Redirect live call (Transfer API — end AI stream → dial human agent)."""
    api = f"{_BASE}/Account/{config.PLIVO_AUTH_ID}/Call/{call_uuid}/"
    payload = {
        "legs": "aleg",
        "aleg_url": answer_url,
        "aleg_method": method.upper(),
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(api, json=payload, auth=_auth())
        if resp.status_code >= 400:
            log.error(
                "Plivo redirect failed status=%s body=%s",
                resp.status_code,
                resp.text[:500],
            )
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            data = {"status": resp.text}
    log.info("Plivo redirect call_uuid=%s -> %s", call_uuid, answer_url)
    return data


async def get_call(call_uuid: str) -> dict[str, Any] | None:
    """Fetch live/completed call details (from_number / to_number)."""
    if not call_uuid or not configured():
        return None
    api = f"{_BASE}/Account/{config.PLIVO_AUTH_ID}/Call/{call_uuid}/"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api, auth=_auth())
            if resp.status_code >= 400:
                log.warning(
                    "Plivo get_call failed status=%s uuid=%s",
                    resp.status_code,
                    call_uuid,
                )
                return None
            return resp.json()
    except Exception:  # noqa: BLE001
        log.exception("Plivo get_call error uuid=%s", call_uuid)
        return None


def pick_remote_number(call: dict[str, Any] | None, *, direction: str) -> str:
    """Customer phone from Plivo Call resource."""
    if not call:
        return ""
    direction = (direction or "inbound").strip().lower()
    frm = str(call.get("from_number") or call.get("from") or "").strip()
    to = str(call.get("to_number") or call.get("to") or "").strip()
    if direction == "outbound":
        return to or frm
    return frm or to
