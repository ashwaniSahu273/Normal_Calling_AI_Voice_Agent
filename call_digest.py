"""Compact conversation state for Gemini soft session resets."""
from __future__ import annotations

import re
from typing import Any

# Caller wants to end — not "thanks, but one more question"
_CONTINUATION_MARKERS = (
    "but ",
    "also ",
    "another ",
    "one more",
    "what about",
    "how about",
    "aur ",
    "or ",
    "?",
    "can you",
    "could you",
    "please tell",
    "mujhe aur",
    "ek aur",
)

_STRONG_FAREWELL = (
    "goodbye",
    "good bye",
    "bye bye",
    "see you",
    "talk later",
    "that's all",
    "thats all",
    "that is all",
    "nothing else",
    "no more question",
    "don't want to continue",
    "dont want to continue",
    "not interested",
    "bas itna",
    "bas ho gaya",
    "band karo",
    "call band",
    "alvida",
    "disconnect",
    "hang up",
    "end the call",
    "call khatam",
    "phone rakh",
    "rakho phone",
)

_CLOSING_THANKS = (
    "thank you",
    "thanks",
    "thank u",
    "shukriya",
    "dhanyavad",
    "dhanyavaad",
    "theek hai bye",
    "ok bye",
    "okay bye",
)


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


def user_wants_to_end(text: str) -> bool:
    """True when the caller is closing the call (thanks / goodbye / stop)."""
    t = (text or "").strip().lower()
    if not t:
        return False
    if any(m in t for m in _CONTINUATION_MARKERS):
        return False
    if any(s in t for s in _STRONG_FAREWELL):
        return True
    if any(s in t for s in _CLOSING_THANKS):
        if "?" in t:
            return False
        if re.search(
            r"\b(what|how|when|where|why|price|cost|also|but|aur|tell me|batao|chahiye)\b",
            t,
        ):
            return False
        if len(t.split()) <= 8:
            return True
    # Standalone "bye" / "ok" / "theek hai" at end of short line
    if re.fullmatch(r"(ok+|okay|theek hai|bye|bye bye|haan theek|achha theek)[\s.!]*", t):
        return True
    return False


def build_owner_summary(
    transcript: list[dict[str, str]],
    *,
    caller_intent: str = "",
    follow_up: str = "none",
    appointment_booked: bool = False,
    lead_captured: bool = False,
) -> str:
    """
    Short owner-facing summary (no transcript dump).
    Used when the model skips end_call summary or for sheet/WhatsApp.
    """
    user_lines = [
        (t.get("text") or "").strip()
        for t in transcript
        if t.get("role") == "user" and (t.get("text") or "").strip()
    ]
    agent_lines = [
        (t.get("text") or "").strip()
        for t in transcript
        if t.get("role") == "assistant" and (t.get("text") or "").strip()
    ]

    topic = (caller_intent or "General enquiry").strip()
    substantive_user = [
        u for u in user_lines if not user_wants_to_end(u) and len(u) > 3
    ]
    main_ask = substantive_user[0][:160] if substantive_user else (user_lines[0][:120] if user_lines else "")
    if len(substantive_user) > 1:
        also = substantive_user[1][:100]
        ask_part = f"They asked about {topic}. Main question: {main_ask}. Also: {also}."
    elif main_ask:
        ask_part = f"They asked about {topic}. Caller said: {main_ask}."
    else:
        ask_part = f"Topic: {topic}. Very short call with little detail captured."

    last_agent = ""
    for line in reversed(agent_lines):
        if len(line) > 15:
            last_agent = line[:180]
            break
    answer_part = f" Agent explained: {last_agent}." if last_agent else ""

    if appointment_booked:
        next_step = "Appointment booked — confirm with caller if needed."
    elif lead_captured:
        next_step = "Lead captured — team should call back."
    elif follow_up == "callback":
        next_step = "Callback requested — follow up soon."
    elif follow_up == "team_notified":
        next_step = "Team notified — check internal notes."
    elif follow_up == "appointment":
        next_step = "Appointment noted — confirm slot."
    else:
        next_step = "No follow-up action unless caller expects a callback."

    return (ask_part + answer_part + " " + next_step).strip()


def sheet_next_step_label(
    follow_up: str,
    *,
    appointment_booked: bool = False,
    lead_captured: bool = False,
) -> str:
    if appointment_booked:
        return "Appointment booked"
    if lead_captured:
        return "Lead — call back"
    mapping = {
        "appointment": "Appointment noted",
        "callback": "Callback needed",
        "team_notified": "Team notified",
        "none": "None",
    }
    return mapping.get(follow_up, follow_up or "None")


def is_poor_summary(text: str) -> bool:
    """True if summary looks like a transcript dump, not an owner summary."""
    if not (text or "").strip():
        return True
    if len(text) > 420:
        return True
    low = text.lower()
    if "caller said:" in low or "agent explained:" in low or "agent covered:" in low:
        return True
    if low.count("caller:") >= 2 or low.count("agent:") >= 2:
        return True
    if text.count("|") >= 3:
        return True
    if text.count("\n") > 2:
        return True
    if text.strip().startswith("[") and "turns]" in low:
        return True
    return False


def _shorten(text: str, limit: int = 120) -> str:
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip() + "…"


def compose_sheet_summary(
    transcript: list[dict[str, str]],
    *,
    caller_intent: str = "",
    follow_up: str = "none",
    appointment_booked: bool = False,
    lead_captured: bool = False,
    outcome: str = "",
) -> str:
    """2–3 plain sentences for voice_calls.summary (no chat paste)."""
    topic = (caller_intent or "General enquiry").strip()
    user_lines = [
        (t.get("text") or "").strip()
        for t in transcript
        if t.get("role") == "user" and (t.get("text") or "").strip()
    ]
    agent_lines = [
        (t.get("text") or "").strip()
        for t in transcript
        if t.get("role") == "assistant" and (t.get("text") or "").strip()
    ]
    asks = [u for u in user_lines if not user_wants_to_end(u) and len(u) > 4]
    main_ask = _shorten(asks[0], 100) if asks else ""
    extra_ask = _shorten(asks[1], 80) if len(asks) > 1 else ""

    answer = ""
    for line in reversed(agent_lines):
        if user_wants_to_end(line):
            continue
        if len(line) > 20:
            answer = _shorten(line, 130)
            break

    parts: list[str] = [f"Caller enquired about {topic}."]
    if main_ask:
        parts.append(f"Key ask: {main_ask}" + (f"; also {extra_ask}." if extra_ask else "."))
    if answer:
        parts.append(f"Agent shared: {answer}")
    if outcome and "hangup" not in outcome.lower():
        parts.append(f"Call ended: {outcome}.")

    next_l = sheet_next_step_label(
        follow_up,
        appointment_booked=appointment_booked,
        lead_captured=lead_captured,
    )
    if next_l and next_l != "None":
        parts.append(f"Follow-up: {next_l}.")

    return " ".join(parts)[:480].strip()


def pick_summary_for_sheet(
    model_summary: str,
    transcript: list[dict[str, str]],
    **kwargs: Any,
) -> str:
    model = (model_summary or "").strip()
    composed = compose_sheet_summary(transcript, **kwargs)
    if model and not is_poor_summary(model):
        return model[:480]
    return composed


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
