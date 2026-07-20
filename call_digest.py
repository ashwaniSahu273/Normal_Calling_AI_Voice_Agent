"""Compact conversation state for Gemini soft session resets."""
from __future__ import annotations

from typing import Any


def build_call_digest(
    transcript: list[dict[str, str]],
    *,
    caller_intent: str = "",
    max_lines: int = 14,
    max_chars: int = 1200,
) -> str:
    """Short bullet digest — keeps long calls accurate after session refresh."""
    if not transcript:
        return "New call; no prior topics yet."

    lines: list[str] = []
    if caller_intent:
        lines.append(f"Caller intent so far: {caller_intent}.")

    tail = transcript[-max_lines:]
    for entry in tail:
        role = entry.get("role", "")
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        label = "Caller" if role == "user" else "Agent"
        lines.append(f"- {label}: {text[:220]}")

    digest = "\n".join(lines)
    if len(digest) > max_chars:
        digest = digest[: max_chars - 1].rsplit("\n", 1)[0] + "…"
    return digest or "Ongoing call; continue helping the caller."


def format_conversation_full(transcript: list[dict[str, str]]) -> str:
    """Multi-line transcript for voice_transcripts tab (not the main log)."""
    if not transcript:
        return ""
    lines: list[str] = []
    for entry in transcript:
        role = entry.get("role", "")
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        label = "Caller" if role == "user" else "Agent"
        lines.append(f"{label}: {text}")
    return "\n".join(lines)


def count_transcript_turns(transcript: list[dict[str, str]]) -> int:
    return sum(1 for t in transcript if (t.get("text") or "").strip())


def format_conversation_preview(
    transcript: list[dict[str, str]],
    *,
    max_turns: int = 5,
    max_line_chars: int = 70,
    max_total_chars: int = 300,
) -> str:
    """
    Compact one-liner for voice_calls sheet — avoids huge wrapped cells.
    """
    total = count_transcript_turns(transcript)
    if not total:
        return "—"

    tail = [t for t in transcript if (t.get("text") or "").strip()][-max_turns:]
    parts: list[str] = []
    for entry in tail:
        role = entry.get("role", "")
        text = (entry.get("text") or "").strip().replace("\n", " ")
        if len(text) > max_line_chars:
            text = text[: max_line_chars - 1].rstrip() + "…"
        prefix = "C" if role == "user" else "A"
        parts.append(f"{prefix}: {text}")

    body = " · ".join(parts)
    head = f"[{total} turns] "
    room = max(40, max_total_chars - len(head))
    if len(body) > room:
        body = body[: room - 1].rstrip() + "…"
    return head + body


def detect_language_hint(transcript: list[dict[str, str]]) -> str:
    """Rough en / hi / mixed from recent user lines."""
    user_text = " ".join(
        t.get("text", "") for t in transcript if t.get("role") == "user"
    ).lower()
    if not user_text.strip():
        return "en"

    hindi_markers = (
        "hindi",
        "हिंदी",
        "हिन्दी",
        "namaste",
        "kya",
        "kaise",
        "chahiye",
        "dhanyavad",
        "dhanyavaad",
        "theek",
        "haan",
        "nahi",
        "aap",
        "mujhe",
        "kripya",
        "shukriya",
    )
    hits = sum(1 for m in hindi_markers if m in user_text)
    devanagari = any("\u0900" <= c <= "\u097f" for c in user_text)
    if devanagari or hits >= 2:
        if any(w in user_text for w in ("english", "inglish")):
            return "mixed"
        return "hi"
    if hits == 1:
        return "mixed"
    return "en"
