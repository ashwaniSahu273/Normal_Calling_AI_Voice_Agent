"""Load company facts for the voice agent (env text, file, optional website)."""
from __future__ import annotations

import logging
import re
from html import unescape
from pathlib import Path

import httpx

import config

log = logging.getLogger("voice-agent.knowledge")

_TAG_RE = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>", re.I)
_SPACE_RE = re.compile(r"\s+")

_cached: str = ""


def _strip_html(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


def _read_file(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        # Allow paths relative to the voice-agent folder
        alt = Path(__file__).resolve().parent / path
        if alt.is_file():
            p = alt
        else:
            log.warning("BUSINESS_CONTEXT_FILE not found: %s", path)
            return ""
    return p.read_text(encoding="utf-8", errors="ignore").strip()


def _fetch_website(url: str, max_chars: int) -> str:
    try:
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            resp = client.get(
                url,
                headers={"User-Agent": "ResilioHub-VoiceAgent/1.0 (+company-context)"},
            )
            resp.raise_for_status()
            text = _strip_html(resp.text)
            if len(text) > max_chars:
                text = text[:max_chars].rsplit(" ", 1)[0] + "…"
            return text
    except Exception as exc:  # noqa: BLE001
        log.warning("Website fetch failed (%s): %s", url, exc)
        return ""


def load_business_knowledge(force: bool = False) -> str:
    """Build compact company context. Cached after first successful load."""
    global _cached
    if _cached and not force:
        return _cached

    parts: list[str] = []

    manual = (config.BUSINESS_CONTEXT or "").strip()
    if manual:
        parts.append(manual)

    file_path = (config.BUSINESS_CONTEXT_FILE or "").strip()
    if file_path:
        file_text = _read_file(file_path)
        if file_text:
            parts.append(file_text)

    website = (config.BUSINESS_WEBSITE or "").strip()
    # Prefer curated file; skip bulky website scrape when file already has facts
    # (huge prompts make Live sessions go quiet after a few turns).
    if website and not any(len(p) > 400 for p in parts):
        web_text = _fetch_website(website, config.BUSINESS_CONTEXT_MAX_CHARS)
        if web_text:
            parts.append(f"Website summary ({website}):\n{web_text}")
    elif website:
        log.info("Skipping website scrape — using curated BUSINESS_CONTEXT_FILE / CONTEXT")

    _cached = "\n\n".join(parts).strip()
    if _cached:
        log.info("Business knowledge loaded (%s chars)", len(_cached))
    else:
        log.info("No business knowledge configured (set BUSINESS_CONTEXT / FILE / WEBSITE)")
    return _cached


def build_system_prompt() -> str:
    """Behavior rules + bilingual policy + company facts."""
    base = (config.SYSTEM_PROMPT_BASE or "").strip()
    knowledge = load_business_knowledge()

    language_block = (
        "LANGUAGE:\n"
        "- Default: clear, simple English.\n"
        "- If the caller speaks Hindi, Hinglish, or asks for Hindi "
        "(Hindi / हिन्दी / Haan Hindi mein / Hindi me baat karein), "
        "switch immediately and continue fully in natural Hindi "
        "(Devanagari or clear Hinglish speech is fine).\n"
        "- If they ask to switch back to English, switch back.\n"
        "- Mirror the caller's language for the rest of the call.\n"
        "- Never mix long English paragraphs into a Hindi turn."
    )

    style_block = (
        "VOICE STYLE:\n"
        "- Sound like a polite human receptionist: warm, clear, unhurried but brief.\n"
        "- Every spoken reply: max 2 short sentences. One question at a time.\n"
        "- Never monologue. Never read long website text aloud.\n"
        "- Prefer short confirmations: Yes / Haan / Sure / Theek hai.\n"
        "- Use company facts below when answering about products, pricing, services, "
        "hours, location, or process. If unknown, say you will note it for the team "
        "and use tools when available — do not invent facts."
    )

    hangup_block = (
        "CALL END (strict):\n"
        "- Keep the conversation going across many questions. Do NOT end after answering 1–3 FAQs.\n"
        "- ONLY call end_call when the caller clearly wants to hang up: "
        "goodbye / bye / thanks that's all / bas itna hi / dhanyavaad alvida / call khatam.\n"
        "- After answering a question, ask if they need anything else — stay on the line.\n"
        "- NEVER call end_call just because there is a short pause.\n"
        "- When ending: one short farewell in their language, then end_call with a clear summary "
        "(who called, what they wanted, next step)."
    )

    chunks = [base, language_block, style_block, hangup_block]
    if knowledge:
        chunks.append(f"COMPANY KNOWLEDGE (use for accurate answers):\n{knowledge}")
    if config.BUSINESS_WEBSITE:
        chunks.append(f"Official website: {config.BUSINESS_WEBSITE}")

    return "\n\n".join(chunks)
