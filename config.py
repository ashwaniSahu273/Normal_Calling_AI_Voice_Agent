"""Environment-backed configuration for the voice bridge."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parent

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", "plivo").strip().lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-live-preview").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime").strip()

# Female clear voices (Gemini): Erinome (Clear), Kore (Firm), Aoede (Breezy), Achernar (Soft)
VOICE = os.getenv("VOICE", "Erinome").strip()

# Persona (spoken style — see docs/GUIDE.md)
AGENT_NAME = os.getenv("AGENT_NAME", "").strip()
VOICE_PERSONA = os.getenv("VOICE_PERSONA", "").strip()

PUBLIC_HOST = os.getenv("PUBLIC_HOST", "").strip()
PORT = int(os.getenv("PORT", "5000"))

N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "").strip()

# ResilioHub Node (optional). Empty = Sheets/n8n + local .env knowledge only.
BACKEND_URL = os.getenv("BACKEND_URL", "").strip().rstrip("/")
BACKEND_SECRET = os.getenv("BACKEND_SECRET", "").strip()

# WhatsApp notify number for call summaries (digits, with country code e.g. 91XXXXXXXXXX)
NOTIFY_WHATSAPP = os.getenv("NOTIFY_WHATSAPP", "").strip()

# --- Knowledge profiles (switch which business the AI answers as) ---
# resiliencesoft = agency / custom software (data/business_knowledge.md)
# resiliohub     = WhatsApp CRM product (data/resiliohub_knowledge.md)
# custom         = use BUSINESS_* / GREETING from .env only
_KNOWLEDGE_PROFILES: dict[str, dict[str, str]] = {
    "resiliencesoft": {
        "business_name": "ResilienceSoft",
        "website": "https://www.resiliencesoft.com/",
        "file": "data/business_knowledge.md",
        "greeting": (
            "Thank you for calling ResilienceSoft. "
            "I can help in English or Hindi — how may I help you?"
        ),
        "outbound_greeting": (
            "Hi, this is calling from ResilienceSoft. "
            "We are following up on your inquiry about our services. "
            "Is this a good time to talk for a minute?"
        ),
        "system_prompt": (
            "You are a warm, accurate phone receptionist for ResilienceSoft. "
            "Answer only from company knowledge and tool results. "
            "Keep every spoken reply under 2 short sentences. Ask one question at a time. "
            "Never monologue. Use tools when needed."
        ),
    },
    "resiliohub": {
        "business_name": "ResilioHub",
        "website": "https://resiliohub.com/",
        "file": "data/resiliohub_knowledge.md",
        "greeting": (
            "Thank you for calling ResilioHub. "
            "I can help in English or Hindi with our WhatsApp CRM — how may I help you?"
        ),
        "outbound_greeting": (
            "Hi, this is calling from ResilioHub. "
            "We are following up on your WhatsApp CRM enquiry. "
            "Is this a good time to talk for a minute?"
        ),
        "system_prompt": (
            "You are a warm, accurate phone receptionist for ResilioHub, "
            "the WhatsApp Business API CRM by ResilienceSoft. "
            "Answer only from company knowledge and tool results. "
            "Keep every spoken reply under 2 short sentences. Ask one question at a time. "
            "Never monologue. Use tools when needed."
        ),
    },
}

KNOWLEDGE_PROFILE = (os.getenv("KNOWLEDGE_PROFILE", "resiliencesoft") or "resiliencesoft").strip().lower()

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "our business").strip()
BUSINESS_WEBSITE = os.getenv("BUSINESS_WEBSITE", "").strip()
# Curated facts (best accuracy). Prefer this over raw website scrape.
BUSINESS_CONTEXT = os.getenv("BUSINESS_CONTEXT", "").strip()
# Optional markdown/text file with company FAQ, services, pricing notes
_default_knowledge = _ROOT / "data" / "business_knowledge.md"
BUSINESS_CONTEXT_FILE = os.getenv(
    "BUSINESS_CONTEXT_FILE",
    str(_default_knowledge) if _default_knowledge.is_file() else "",
).strip()
BUSINESS_CONTEXT_MAX_CHARS = int(os.getenv("BUSINESS_CONTEXT_MAX_CHARS", "3500"))

GREETING = os.getenv(
    "GREETING",
    (
        f"Thank you for calling {BUSINESS_NAME}. "
        "I can help in English or Hindi — how may I help you today?"
    ),
).strip()

# Outbound follow-up calls — YOU called THEM (not inbound receptionist)
OUTBOUND_GREETING = os.getenv(
    "OUTBOUND_GREETING",
    (
        f"Hi, this is calling from {BUSINESS_NAME}. "
        "We are following up on your recent inquiry. "
        "Is this a good time to talk for a minute?"
    ),
).strip()

# Optional override for outbound AI rules (see knowledge.build_outbound_system_prompt)
OUTBOUND_FOLLOWUP_PROMPT = os.getenv("OUTBOUND_FOLLOWUP_PROMPT", "").strip()

# Base personality — language + company facts are appended in knowledge.build_system_prompt()
SYSTEM_PROMPT_BASE = os.getenv(
    "SYSTEM_PROMPT",
    (
        f"You are a warm, accurate phone receptionist for {BUSINESS_NAME}. "
        "Answer only from company knowledge and tool results. "
        "Keep every spoken reply under 2 short sentences. Ask one question at a time. "
        "Never monologue. Use tools to book appointments, capture leads, and notify the team."
    ),
).strip()

# Filled on startup / connect via knowledge.build_system_prompt()
SYSTEM_PROMPT = SYSTEM_PROMPT_BASE


def list_knowledge_profiles() -> dict[str, str]:
    return {
        "resiliencesoft": "Agency / custom software — data/business_knowledge.md",
        "resiliohub": "WhatsApp CRM product — data/resiliohub_knowledge.md",
        "custom": "Use BUSINESS_NAME / WEBSITE / CONTEXT_FILE / GREETING from .env as-is",
    }


def apply_knowledge_profile(profile: str | None = None) -> str:
    """Apply a named knowledge profile (updates BUSINESS_* + greetings). Returns profile id."""
    global KNOWLEDGE_PROFILE, BUSINESS_NAME, BUSINESS_WEBSITE, BUSINESS_CONTEXT_FILE
    global GREETING, OUTBOUND_GREETING, SYSTEM_PROMPT_BASE, SYSTEM_PROMPT

    name = (profile if profile is not None else KNOWLEDGE_PROFILE).strip().lower()
    if name in ("", "custom"):
        KNOWLEDGE_PROFILE = "custom"
        return KNOWLEDGE_PROFILE
    if name not in _KNOWLEDGE_PROFILES:
        raise ValueError(
            f"profile must be one of: {', '.join(list_knowledge_profiles())}"
        )

    p = _KNOWLEDGE_PROFILES[name]
    KNOWLEDGE_PROFILE = name
    BUSINESS_NAME = p["business_name"]
    BUSINESS_WEBSITE = p["website"]
    BUSINESS_CONTEXT_FILE = p["file"]
    GREETING = p["greeting"]
    OUTBOUND_GREETING = p["outbound_greeting"]
    SYSTEM_PROMPT_BASE = p["system_prompt"]
    SYSTEM_PROMPT = SYSTEM_PROMPT_BASE
    return KNOWLEDGE_PROFILE


def set_knowledge_profile(profile: str) -> str:
    """Switch knowledge base without restart. Returns normalized profile id."""
    return apply_knowledge_profile(profile)


# Apply profile from .env at import (named profiles override BUSINESS_* for that mode)
if KNOWLEDGE_PROFILE in _KNOWLEDGE_PROFILES:
    apply_knowledge_profile(KNOWLEDGE_PROFILE)

# Hang-up rules
SILENCE_TIMEOUT_SEC = float(os.getenv("SILENCE_TIMEOUT_SEC", "45"))
MAX_CALL_DURATION_SEC = float(os.getenv("MAX_CALL_DURATION_SEC", "600"))
END_CALL_GRACE_SEC = float(os.getenv("END_CALL_GRACE_SEC", "2.5"))
# RMS threshold on PCM16 to count inbound as speech (ignore line noise)
SPEECH_RMS_THRESHOLD = int(os.getenv("SPEECH_RMS_THRESHOLD", "400"))
# Nudge only if AI stays silent this long AFTER caller clearly finished (seconds)
AI_RESPONSE_NUDGE_SEC = float(os.getenv("AI_RESPONSE_NUDGE_SEC", "4.5"))

# Gemini VAD — silence after caller stops before model replies (ms). Higher = more patient listening.
GEMINI_SILENCE_MS = int(os.getenv("GEMINI_SILENCE_MS", "580"))
GEMINI_PREFIX_PADDING_MS = int(os.getenv("GEMINI_PREFIX_PADDING_MS", "24"))
# high = ends caller turn quickly (can interrupt). low = wait through natural pauses.
GEMINI_END_SPEECH_SENSITIVITY = os.getenv("GEMINI_END_SPEECH_SENSITIVITY", "low").strip().lower()
# 2.5 Live: thinking_budget=0. 3.1 Live: use thinking_level (minimal = fastest)
GEMINI_THINKING_BUDGET = int(os.getenv("GEMINI_THINKING_BUDGET", "0"))
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "minimal").strip().lower()
# Context compression keeps long calls from slowing down (Live API)
GEMINI_CONTEXT_COMPRESSION = os.getenv("GEMINI_CONTEXT_COMPRESSION", "true").lower() in (
    "1",
    "true",
    "yes",
)

# Soft session reset — keeps long calls responsive (new Live session + digest)
# Turn-based reset uses real caller Q&A turns in bridge (not STT fragments). 0 = time-only.
GEMINI_SOFT_RESET_EVERY_TURNS = int(os.getenv("GEMINI_SOFT_RESET_EVERY_TURNS", "22"))
GEMINI_SOFT_RESET_EVERY_SEC = float(os.getenv("GEMINI_SOFT_RESET_EVERY_SEC", "480"))
GEMINI_DIGEST_MAX_CHARS = int(os.getenv("GEMINI_DIGEST_MAX_CHARS", "1800"))

# lookup_knowledge: search local file first, then n8n action lookup_knowledge
KNOWLEDGE_SEARCH_LOCAL_FIRST = os.getenv("KNOWLEDGE_SEARCH_LOCAL_FIRST", "true").lower() in (
    "1",
    "true",
    "yes",
)
KNOWLEDGE_SEARCH_MAX_CHARS = int(os.getenv("KNOWLEDGE_SEARCH_MAX_CHARS", "3200"))

# Plivo REST (outbound + mid-call transfer) — Console → Account → Auth ID / Auth Token
PLIVO_AUTH_ID = os.getenv("PLIVO_AUTH_ID", "").strip()
PLIVO_AUTH_TOKEN = os.getenv("PLIVO_AUTH_TOKEN", "").strip()
# E.164 caller ID for outbound, e.g. +912264233283
PLIVO_FROM_NUMBER = os.getenv("PLIVO_FROM_NUMBER", "").strip()

# Human agent mobile/landline (E.164) for callback ping / live transfer / agent-first
HUMAN_AGENT_NUMBER = os.getenv("HUMAN_AGENT_NUMBER", "").strip()
# callback = missed-call ping + WhatsApp, agent calls customer back (no live Plivo minutes)
# transfer = old live Dial connect (billed per minute on both legs)
HUMAN_HANDOVER_MODE = (os.getenv("HUMAN_HANDOVER_MODE", "callback") or "callback").strip().lower()
_HANDOVER_MODES = ("callback", "transfer")


def set_handover_mode(mode: str) -> str:
    """Switch human handover without restart. Returns normalized mode."""
    global HUMAN_HANDOVER_MODE
    mode = (mode or "").strip().lower()
    if mode not in _HANDOVER_MODES:
        raise ValueError("mode must be 'callback' or 'transfer'")
    HUMAN_HANDOVER_MODE = mode
    return HUMAN_HANDOVER_MODE
# How long Plivo rings the agent for the missed-call ping before giving up
MISSED_CALL_RING_SEC = int(os.getenv("MISSED_CALL_RING_SEC", "12"))
# Ring human before AI on inbound (requires HUMAN_AGENT_NUMBER + Plivo creds)
AGENT_FIRST_ENABLED = os.getenv("AGENT_FIRST_ENABLED", "false").lower() in ("1", "true", "yes")
AGENT_FIRST_TIMEOUT_SEC = int(os.getenv("AGENT_FIRST_TIMEOUT_SEC", "25"))
AGENT_FIRST_ANNOUNCEMENT = os.getenv("AGENT_FIRST_ANNOUNCEMENT", "").strip()
AGENT_FALLBACK_ANNOUNCEMENT = os.getenv("AGENT_FALLBACK_ANNOUNCEMENT", "").strip()
TRANSFER_ANNOUNCEMENT = os.getenv("TRANSFER_ANNOUNCEMENT", "").strip()
# Seconds to let AI finish spoken line before hangup / redirect
TRANSFER_GRACE_SEC = float(os.getenv("TRANSFER_GRACE_SEC", "3.0"))

# Protect POST /plivo/outbound (header x-voice-secret or Bearer token)
OUTBOUND_API_SECRET = os.getenv("OUTBOUND_API_SECRET", "").strip()

TELEPHONY_SAMPLE_RATE = 8000
PLIVO_CONTENT_TYPE = "audio/x-mulaw"
PLIVO_SAMPLE_RATE = 8000
EXOTEL_SAMPLE_RATE = int(os.getenv("EXOTEL_SAMPLE_RATE", "8000"))
OPENAI_AUDIO_FORMAT = "g711_ulaw"
GEMINI_INPUT_RATE = 16000
GEMINI_OUTPUT_RATE = 24000
# Exotel ~100ms PCM16 @ 8kHz = 1600 bytes (320-byte aligned). 3200 = ~200ms delay.
EXOTEL_FRAME_BYTES = int(os.getenv("EXOTEL_FRAME_BYTES", "1600"))
# Local audio: caller must be quiet this long before we treat their turn as finished
SPEECH_END_GAP_SEC = float(os.getenv("SPEECH_END_GAP_SEC", "0.9"))
# Do not nudge while caller spoke within this window (seconds)
CALLER_LISTEN_GRACE_SEC = float(os.getenv("CALLER_LISTEN_GRACE_SEC", "1.4"))


def validate() -> None:
    if AI_PROVIDER == "gemini" and not GEMINI_API_KEY:
        raise RuntimeError("AI_PROVIDER=gemini but GEMINI_API_KEY is not set")
    if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        raise RuntimeError("AI_PROVIDER=openai but OPENAI_API_KEY is not set")
    if AI_PROVIDER not in ("gemini", "openai"):
        raise RuntimeError(f"Unknown AI_PROVIDER: {AI_PROVIDER!r}")
    if TELEPHONY_PROVIDER not in ("exotel", "plivo"):
        raise RuntimeError(f"Unknown TELEPHONY_PROVIDER: {TELEPHONY_PROVIDER!r}")
    if EXOTEL_SAMPLE_RATE not in (8000, 16000, 24000):
        raise RuntimeError("EXOTEL_SAMPLE_RATE must be 8000, 16000, or 24000")
