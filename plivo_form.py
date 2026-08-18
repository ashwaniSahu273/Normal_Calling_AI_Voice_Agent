"""Parse Plivo Answer / stream-status payloads. Stdlib only (no python-multipart)."""
from __future__ import annotations

import json
from urllib.parse import parse_qs


def parse_plivo_payload(
    *,
    query: list[tuple[str, str]] | None = None,
    body: bytes = b"",
    content_type: str = "",
) -> dict[str, str]:
    params: dict[str, str] = {}
    for key, val in query or []:
        if val and str(val).strip() and key not in params:
            params[key] = str(val).strip()
    if not body:
        return params
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return params
    ctype = (content_type or "").lower()
    parsed_json = False
    if "json" in ctype or text[:1] in "{[":
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                parsed_json = True
                for key, val in data.items():
                    if val is not None and str(val).strip() and key not in params:
                        params[key] = str(val).strip()
        except Exception:  # noqa: BLE001
            parsed_json = False
    if not parsed_json:
        for key, vals in parse_qs(text, keep_blank_values=True).items():
            if vals and str(vals[0]).strip() and key not in params:
                params[key] = str(vals[0]).strip()
    return params


def pick_plivo_value(params: dict[str, str], *keys: str) -> str:
    for key in keys:
        val = params.get(key)
        if val:
            return val
    lower = {k.lower(): v for k, v in params.items()}
    for key in keys:
        val = lower.get(key.lower())
        if val:
            return val
    return ""
