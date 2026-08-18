"""Short-lived outbound call context — avoid long purpose strings in Plivo XML URLs."""
from __future__ import annotations

import secrets
import time
from typing import Any

_TTL_SEC = 3600
_store: dict[str, dict[str, Any]] = {}


def _purge() -> None:
    now = time.time()
    stale = [k for k, v in _store.items() if now - float(v.get("created", 0)) > _TTL_SEC]
    for key in stale:
        _store.pop(key, None)


def store(*, purpose: str = "", to: str = "", tenant_id: str = "") -> str:
    """Save outbound metadata; return short ctx id for answer/stream URLs."""
    _purge()
    ctx_id = secrets.token_urlsafe(8)
    _store[ctx_id] = {
        "purpose": (purpose or "").strip(),
        "to": (to or "").strip(),
        "tenant_id": (tenant_id or "").strip(),
        "created": time.time(),
    }
    return ctx_id


def get(ctx_id: str) -> dict[str, Any] | None:
    _purge()
    if not ctx_id:
        return None
    row = _store.get(ctx_id.strip())
    if not row:
        return None
    if time.time() - float(row.get("created", 0)) > _TTL_SEC:
        _store.pop(ctx_id.strip(), None)
        return None
    return row
