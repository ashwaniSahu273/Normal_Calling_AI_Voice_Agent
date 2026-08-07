"""Short-lived call metadata — Plivo caller number keyed by CallUUID / StreamID."""
from __future__ import annotations

import time
from typing import Any

_TTL_SEC = 7200
_by_call: dict[str, dict[str, Any]] = {}
_by_stream: dict[str, dict[str, Any]] = {}


def _purge() -> None:
    now = time.time()
    for store in (_by_call, _by_stream):
        stale = [k for k, v in store.items() if now - float(v.get("created", 0)) > _TTL_SEC]
        for key in stale:
            store.pop(key, None)


def _norm_key(value: str | None) -> str:
    return (value or "").strip()


def remember(
    *,
    call_uuid: str = "",
    stream_id: str = "",
    caller: str = "",
    to: str = "",
    direction: str = "",
) -> None:
    """Upsert caller/to for a live call (answer webhook or stream-status)."""
    _purge()
    call_uuid = _norm_key(call_uuid)
    stream_id = _norm_key(stream_id)
    caller = _norm_key(caller)
    to = _norm_key(to)
    direction = _norm_key(direction).lower()
    if not call_uuid and not stream_id:
        return
    if not caller and not to:
        return

    existing: dict[str, Any] = {}
    if call_uuid and call_uuid in _by_call:
        existing = dict(_by_call[call_uuid])
    elif stream_id and stream_id in _by_stream:
        existing = dict(_by_stream[stream_id])

    row = {
        "created": existing.get("created", time.time()),
        "updated": time.time(),
        "call_uuid": call_uuid or existing.get("call_uuid", ""),
        "stream_id": stream_id or existing.get("stream_id", ""),
        "caller": caller or existing.get("caller", ""),
        "to": to or existing.get("to", ""),
        "direction": direction or existing.get("direction", ""),
    }
    if row["call_uuid"]:
        _by_call[row["call_uuid"]] = row
    if row["stream_id"]:
        _by_stream[row["stream_id"]] = row


def lookup(*, call_uuid: str = "", stream_id: str = "") -> dict[str, Any] | None:
    _purge()
    call_uuid = _norm_key(call_uuid)
    stream_id = _norm_key(stream_id)
    if call_uuid and call_uuid in _by_call:
        return _by_call[call_uuid]
    if stream_id and stream_id in _by_stream:
        return _by_stream[stream_id]
    return None


def pick_caller(row: dict[str, Any] | None, *, direction: str = "inbound") -> str:
    if not row:
        return ""
    direction = (direction or row.get("direction") or "inbound").strip().lower()
    caller = str(row.get("caller") or "").strip()
    to = str(row.get("to") or "").strip()
    if direction == "outbound":
        return to or caller
    return caller or to
