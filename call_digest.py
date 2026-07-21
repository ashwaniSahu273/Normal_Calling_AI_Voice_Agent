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
        if _should_join_utterance(prev, text):
            transcript[-1]["text"] = f"{prev} {text}".strip()
            return
    transcript.append({"role": role, "text": text})


def _should_join_utterance(prev: str, new: str) -> bool:
    """Join STT word shards on the same speaker turn."""
    if not prev or not new:
        return False
    p, n = prev.strip(), new.strip()
    if p.endswith((".", "?", "!")) and len(n) > 8:
        return False
    if len(n.split()) <= 2 and len(n) < 22:
        return True
    if len(p.split()) <= 4 and len(p) < 28:
        return True
    if len(n) < 18 and not n.endswith((".", "?", "!")):
        return True
    return False


def coalesce_role_runs(transcript: list[dict[str, str]]) -> list[dict[str, str]]:
    """Merge back-to-back lines from the same speaker (summary + transcript cleanup)."""
    out: list[dict[str, str]] = []
    for entry in transcript:
        role = entry.get("role", "")
        text = " ".join((entry.get("text") or "").split()).strip()
        if not text:
            continue
        if out and out[-1]["role"] == role:
            prev = out[-1]["text"]
            if text.startswith(prev):
                out[-1]["text"] = text
            elif prev.startswith(text):
                continue
            else:
                out[-1]["text"] = f"{prev} {text}".strip()
        else:
            out.append({"role": role, "text": text})
    return out


def _is_meaningful_caller_text(text: str) -> bool:
    t = " ".join((text or "").split()).strip()
    if not t or user_wants_to_end(t):
        return False
    words = t.split()
    if len(words) >= 3:
        return True
    if len(t) >= 20:
        return True
    if "?" in t:
        return True
    if len(words) == 1 and len(words[0]) < 10:
        return False
    if len(t) < 14:
        return False
    return True


def infer_topic_label(
    transcript: list[dict[str, str]], caller_intent: str = ""
) -> str:
    if (caller_intent or "").strip() and caller_intent.strip().lower() not in (
        "general enquiry",
        "general inquiry",
    ):
        return caller_intent.strip()
    blob = " ".join(
        (e.get("text") or "")
        for e in coalesce_role_runs(transcript)
        if e.get("role") == "user"
    ).lower()
    checks = [
        (("digital marketing", "marketing", "seo", "social media"), "Digital marketing"),
        (("appointment", "book a", "booking", "schedule"), "Appointment booking"),
        (("website", "web design", "web development"), "Website / web development"),
        (("mobile app", "android", "ios app", "application"), "Mobile app"),
        (("crm", "whatsapp crm"), "CRM / WhatsApp CRM"),
        (("hosting", "domain"), "Hosting"),
        (("demo", "demonstration"), "Product demo"),
        (("price", "pricing", "cost", "quote", "package"), "Pricing enquiry"),
        (("callback", "call back", "call me back"), "Callback request"),
    ]
    for keys, label in checks:
        if any(k in blob for k in keys):
            return label
    return caller_intent.strip() or "General enquiry"


def _cleanup_stt(text: str) -> str:
    t = " ".join((text or "").split())
    fixes = (
        (r"\bappoint\s+ment\b", "appointment"),
        (r"\bdigi\s+tal\b", "digital"),
        (r"\bmark\s+eting\b", "marketing"),
        (r"\bdevel\s+opment\b", "development"),
    )
    for pat, repl in fixes:
        t = re.sub(pat, repl, t, flags=re.I)
    return t.strip()


def _natural_request(text: str) -> str:
    t = _cleanup_stt(text)
    t = re.sub(
        r"^(hi|hello|hey|yes|yeah|ok|okay|namaste|i want to|i want|i need to|i need|"
        r"please|can you|could you|tell me|mujhe|main|want to|want)\s+",
        "",
        t,
        flags=re.I,
    ).strip()
    if not t:
        t = _cleanup_stt(text)
    if len(t) > 1:
        t = t[0].lower() + t[1:]
    return _shorten(t, 160)


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
    merged = coalesce_role_runs(transcript)
    if not merged:
        return ""
    lines: list[str] = []
    for entry in merged:
        role = entry.get("role", "")
        text = (entry.get("text") or "").strip()
        if not text:
            continue
        label = "Caller" if role == "user" else "Agent"
        lines.append(f"{label}: {text}")
    return "\n".join(lines)


def count_transcript_turns(transcript: list[dict[str, str]]) -> int:
    return sum(1 for t in transcript if (t.get("text") or "").strip())


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
    if "key ask:" in low or "caller wanted:" in low or "agent shared:" in low:
        return True
    if low.count("caller:") >= 1 or low.count("agent:") >= 1:
        return True
    if low.count("caller:") >= 2 or low.count("agent:") >= 2:
        return True
    if text.count("|") >= 3:
        return True
    if text.count("\n") > 1:
        return True
    if text.strip().startswith("[") and "turns]" in low:
        return True
    if re.match(r"^c:\s", low) or " · a:" in low or " · c:" in low:
        return True
    if low.count("they also asked") >= 2:
        return True
    if re.search(r"they (also )?asked about \w+\.", low):
        return True
    return False


def _embed_answer(text: str) -> str:
    t = _shorten(text, 130).strip().rstrip(".")
    if not t:
        return "responded briefly"
    low = t[0].lower() + t[1:] if len(t) > 1 else t.lower()
    starters = ("we ", "our ", "yes", "no", "the ", "i ", "haan", "ji ", "sure")
    if low.startswith(starters):
        return f"explained that {low}"
    return f"responded: {low}"


def _collect_exchanges(
    transcript: list[dict[str, str]],
) -> list[tuple[str, str]]:
    """Ordered (caller turn, agent reply) after coalescing STT shards."""
    entries = coalesce_role_runs(transcript)
    pairs: list[tuple[str, str]] = []
    i = 0
    while i < len(entries):
        if entries[i].get("role") != "user":
            i += 1
            continue
        chunk_parts: list[str] = []
        while i < len(entries) and entries[i].get("role") == "user":
            part = " ".join((entries[i].get("text") or "").split()).strip()
            if part and not user_wants_to_end(part):
                chunk_parts.append(part)
            i += 1
        u = " ".join(chunk_parts).strip()
        if not u or not _is_meaningful_caller_text(u):
            continue
        agent_reply = ""
        if i < len(entries) and entries[i].get("role") == "assistant":
            agent_reply = " ".join((entries[i].get("text") or "").split()).strip()
            i += 1
        pairs.append((u, agent_reply))
    return pairs


def narrate_call_in_english(
    transcript: list[dict[str, str]],
    *,
    caller_intent: str = "",
    follow_up: str = "none",
    appointment_booked: bool = False,
    lead_captured: bool = False,
    outcome: str = "",
) -> str:
    """Short third-person story of the call — no STT word shards."""
    topic = infer_topic_label(transcript, caller_intent)
    topic_phrase = topic.lower() if topic != "General enquiry" else "their enquiry"
    exchanges = _collect_exchanges(transcript)
    coalesced = coalesce_role_runs(transcript)

    user_blocks = [
        e["text"]
        for e in coalesced
        if e.get("role") == "user" and _is_meaningful_caller_text(e["text"])
    ]
    agent_blocks = [
        e["text"]
        for e in coalesced
        if e.get("role") == "assistant"
        and len((e.get("text") or "").strip()) > 18
        and not user_wants_to_end(e.get("text") or "")
    ]

    sentences: list[str] = [
        f"The caller contacted the company regarding {topic_phrase}."
    ]

    if user_blocks:
        main = _natural_request(user_blocks[0])
        if len(user_blocks) > 1:
            extra = _natural_request(" ".join(user_blocks[1:3]))
            if extra and extra not in main:
                sentences.append(
                    f"They said they wanted {main}, and also mentioned {extra}."
                )
            else:
                sentences.append(f"They said they wanted {main}.")
        else:
            if main.endswith("?"):
                sentences.append(f"They asked {main}")
            else:
                sentences.append(f"They said they wanted {main}.")
    elif exchanges:
        q = _natural_request(exchanges[0][0])
        sentences.append(
            f"They asked {q}." if q.endswith("?") else f"They said they wanted {q}."
        )
    else:
        sentences.append("The conversation was very short and few details were captured.")

    if agent_blocks:
        best = agent_blocks[-1]
        for line in reversed(agent_blocks):
            if len(line) > len(best):
                best = line
                break
        sentences.append(f"The receptionist {_embed_answer(best)}.")
    elif exchanges and exchanges[-1][1]:
        sentences.append(f"The receptionist {_embed_answer(exchanges[-1][1])}.")

    next_l = sheet_next_step_label(
        follow_up,
        appointment_booked=appointment_booked,
        lead_captured=lead_captured,
    )
    if appointment_booked:
        sentences.append("An appointment was booked during the call.")
    elif lead_captured:
        sentences.append("The agent captured the caller's details for a follow-up call.")
    elif next_l and next_l not in ("None", ""):
        sentences.append(f"Next step for the team: {next_l.lower()}.")

    oc = (outcome or "").strip()
    if oc and "hangup" not in oc.lower():
        if "thanks" in oc.lower() or "goodbye" in oc.lower():
            sentences.append("The caller ended the conversation politely.")
        elif "silence" in oc.lower():
            sentences.append("The call ended after a period of silence.")
        elif "max" in oc.lower():
            sentences.append("The call ended when the maximum call duration was reached.")
        elif "hung up" in oc.lower():
            sentences.append("The caller hung up before finishing the discussion.")
        else:
            sentences.append(f"The call ended ({oc.lower()}).")

    return " ".join(sentences)[:480].strip()


def compose_sheet_summary(
    transcript: list[dict[str, str]],
    *,
    caller_intent: str = "",
    follow_up: str = "none",
    appointment_booked: bool = False,
    lead_captured: bool = False,
    outcome: str = "",
) -> str:
    return narrate_call_in_english(
        transcript,
        caller_intent=caller_intent,
        follow_up=follow_up,
        appointment_booked=appointment_booked,
        lead_captured=lead_captured,
        outcome=outcome,
    )

def pick_summary_for_sheet(
    model_summary: str,
    transcript: list[dict[str, str]],
    **kwargs: Any,
) -> str:
    """Sheet/WhatsApp always get third-person narrative from transcript."""
    narrative = narrate_call_in_english(transcript, **kwargs)
    if narrative and len(narrative) > 40:
        return narrative[:480]
    model = (model_summary or "").strip()
    if model and not is_poor_summary(model):
        return model[:480]
    return narrative[:480] if narrative else (model[:480] if model else "Call completed.")


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
