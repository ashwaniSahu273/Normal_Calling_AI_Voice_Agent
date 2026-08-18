"""ResilioHub Node client — optional. Empty BACKEND_URL = n8n/.env only."""
from __future__ import annotations

import logging
from typing import Any

import httpx

import config

log = logging.getLogger("voice-agent.backend")


def configured() -> bool:
    return bool((config.BACKEND_URL or "").strip() and (config.BACKEND_SECRET or "").strip())


def _headers() -> dict[str, str]:
    return {"x-voice-secret": config.BACKEND_SECRET}


def _base() -> str:
    return (config.BACKEND_URL or "").rstrip("/")


async def get_tenant_config(
    *,
    number: str = "",
    tenant_id: str = "",
) -> dict[str, Any] | None:
    """Load per-business settings before Gemini connects. None = use .env."""
    if not configured():
        return None
    params: dict[str, str] = {}
    if tenant_id:
        params["tenant_id"] = str(tenant_id)
    if number:
        params["number"] = number
    if not params:
        return None
        url = f"{_base()}/api/internal/ai-calling/tenant-config"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(url, params=params, headers=_headers())
            if resp.status_code == 404:
                log.info("Node tenant-config miss number=%s tenant_id=%s", number or "-", tenant_id or "-")
                return None
            resp.raise_for_status()
            data = resp.json()
    except Exception:  # noqa: BLE001
        log.exception("Node tenant-config failed — falling back to .env")
        return None
    if not isinstance(data, dict) or data.get("ok") is False:
        return None
    status = str(data.get("status") or "").lower()
    if status in ("disabled", "suspended"):
        log.warning("Tenant %s status=%s — using .env", data.get("tenant_id"), status)
        return None
    log.info(
        "Tenant config tenant_id=%s number=%s business=%s",
        data.get("tenant_id"),
        data.get("phone_number") or number or "-",
        data.get("business_name") or "-",
    )
    return data


async def post_call_ended(payload: dict[str, Any]) -> None:
    if not configured():
        return
    url = f"{_base()}/api/internal/ai-calling/call-ended"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(url, json=payload, headers=_headers())
            resp.raise_for_status()
        log.info("Node call-ended ok call_id=%s", payload.get("call_id"))
    except Exception:  # noqa: BLE001
        log.exception("Node call-ended failed")


async def post_action(action: str, payload: dict[str, Any]) -> None:
    if not configured() or not action:
        return
    url = f"{_base()}/api/internal/ai-calling/action"
    body = {"action": action, **payload}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(url, json=body, headers=_headers())
            resp.raise_for_status()
    except Exception:  # noqa: BLE001
        log.exception("Node action=%s failed", action)
