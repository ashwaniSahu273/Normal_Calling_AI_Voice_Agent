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


def _shorten(text: str, limit: int = 120) -> str:
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    return t[: limit - 1].rstrip() + "…"


def merge_transcript_line(
    transcript: list[dict[str, str]], role: str, text: str
) -> None:
    """Append or extend last line (Gemini STT often sends growing partials)."""
    text = " ".join((text or "").split()).strip()
    if not text:
        return
    if transcript and transcript[-1].get("role") == role:
        prev = (transcript[-1].get("text") or "").strip()
        if prev == text:
            return
        if text.startswith(prev) or (prev and prev in text and len(text) > len(prev)):
            transcript[-1]["text"] = text
            return
        if prev.startswith(text):
            return
    transcript.append({"role": role, "text": text})


def _substantive_user_lines(transcript: list[dict[str, str]]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for entry in transcript:
        if entry.get("role") != "user":
            continue
        t = " ".join((entry.get("text") or "").split()).strip()
        if len(t) < 5 or user_wants_to_end(t):
            continue
        key = t.lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def build_call_digest(
    transcript: list[dict[str, str]],
    *,
    caller_intent: str = "",
    max_lines: int = 16,
    max_chars: int = 1200,
) -> str:
    """Short digest for session refresh — facts caller already knows (no re-ask)."""
    if not transcript:
        return "New call; no prior topics yet."

    lines: list[str] = [
        "PHONE CALL IN PROGRESS — same caller, same receptionist.",
        "Do NOT greet again. Do NOT re-ask language preference if already chosen.",
        "Do NOT repeat questions the caller already answered.",
    ]
    if caller_intent:
        lines.append(f"Main topic: {caller_intent}.")

    user_asks = _substantive_user_lines(transcript)
    if user_asks:
        lines.append("Caller already asked about:")
        for q in user_asks[-5:]:
            lines.append(f"  • {_shorten(q, 140)}")

    agent_facts: list[str] = []
    for entry in transcript:
        if entry.get("role") != "assistant":
            continue
        t = " ".join((entry.get("text") or "").split()).strip()
        if len(t) < 25 or user_wants_to_end(t):
            continue
        agent_facts.append(_shorten(t, 160))
    if agent_facts:
        lines.append("You already told them:")
        for a in agent_facts[-4:]:
            lines.append(f"  • {a}")

    lines.append("Recent lines:")
    tail = transcript[-max_lines:]
    for entry in tail:
        role = entry.get("role", "")
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        label = "Caller" if role == "user" else "Agent"
        lines.append(f"- {label}: {_shorten(text, 200)}")

    digest = "\n".join(lines)
    limit = max(max_chars, 800)
    if len(digest) > limit:
        digest = digest[: limit - 1].rsplit("\n", 1)[0] + "…"
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
    """Short owner-facing summary (no transcript dump)."""
    return compose_sheet_summary(
        transcript,
        caller_intent=caller_intent,
        follow_up=follow_up,
        appointment_booked=appointment_booked,
        lead_captured=lead_captured,
        outcome="",
    )


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


def compose_sheet_summary(
    transcript: list[dict[str, str]],
    *,
    caller_intent: str = "",
    follow_up: str = "none",
    appointment_booked: bool = False,
    lead_captured: bool = False,
    outcome: str = "",
) -> str:
    """Plain-language owner summary for sheet / WhatsApp."""
    topic = (caller_intent or "General enquiry").strip()
    asks = [_shorten(q, 110) for q in _substantive_user_lines(transcript)]
    if not asks and transcript:
        for entry in transcript:
            if entry.get("role") == "user":
                t = (entry.get("text") or "").strip()
                if t and not user_wants_to_end(t):
                    asks.append(_shorten(t, 110))
                    break

    agent_lines = [
        " ".join((entry.get("text") or "").split()).strip()
        for entry in transcript
        if entry.get("role") == "assistant"
    ]
    answers: list[str] = []
    for line in reversed(agent_lines):
        if user_wants_to_end(line) or len(line) < 20:
            continue
        answers.append(_shorten(line, 120))
        if len(answers) >= 2:
            break
    answers.reverse()

    parts: list[str] = []
    if asks:
        q_text = asks[0]
        if len(asks) > 1:
            q_text += f"; also asked: {asks[1]}"
        if len(asks) > 2:
            q_text += f" (+{len(asks) - 2} more)"
        parts.append(f"Topic: {topic}. Caller wanted: {q_text}.")
    else:
        parts.append(f"Topic: {topic}. Short call with limited detail.")

    if answers:
        parts.append(f"Agent covered: {answers[-1]}.")
        if len(answers) > 1:
            parts[-1] = f"Agent covered: {answers[0]}; later: {answers[-1]}."

    next_l = sheet_next_step_label(
        follow_up,
        appointment_booked=appointment_booked,
        lead_captured=lead_captured,
    )
    if next_l and next_l != "None":
        parts.append(f"Next step: {next_l}.")
    elif outcome and "hangup" not in outcome.lower():
        parts.append(f"Call ended: {outcome}.")

    return " ".join(parts)[:480].strip()


def pick_summary_for_sheet(
    model_summary: str,
    transcript: list[dict[str, str]],
    **kwargs: Any,
) -> str:
    composed = compose_sheet_summary(transcript, **kwargs)
    model = (model_summary or "").strip()
    if model and not is_poor_summary(model) and len(model) >= 50:
        if composed and len(composed) > len(model) + 80:
            return composed[:480]
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
