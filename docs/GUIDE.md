# Voice Agent — Setup & Operations Guide

Everything you need to **run**, **configure**, and **troubleshoot** the Python voice bridge (Gemini + Plivo/Exotel + n8n).

For **ResilioHub product integration** (Node backend, multi-tenant, clients) see **[INTEGRATION.md](INTEGRATION.md)**.

For a visual architecture PDF: `docs/Voice_Agent_Complete_Flow_Guide.pdf` (regenerate with `python scripts/generate_flow_pdf.py`).

---

## Table of contents

1. [Quick start](#1-quick-start)
2. [Environment variables](#2-environment-variables)
3. [Telephony — Plivo (recommended)](#3-telephony--plivo-recommended)
4. [Telephony — Exotel (alternative)](#4-telephony--exotel-alternative)
5. [Voice & persona](#5-voice--persona)
6. [Business knowledge & RAG](#6-business-knowledge--rag)
7. [n8n & Google Sheets](#7-n8n--google-sheets)
8. [Features (stability, summaries)](#8-features-stability-summaries)
9. [Troubleshooting](#9-troubleshooting)
10. [Scripts](#10-scripts)

---

## 1. Quick start

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows
pip install -r requirements.txt
cp .env.example .env                # fill keys + PUBLIC_HOST + N8N_WEBHOOK_URL
python app.py
```

**Tunnel (dev only):**

```bash
cloudflared tunnel --url http://localhost:5000
```

Put tunnel host (no `https://`) in `.env` → `PUBLIC_HOST`.

**Health check:** `https://<PUBLIC_HOST>/health` → `{"status":"ok","ai":"gemini","telephony":"plivo"}`

**Flow:**

```
Caller → Plivo/Exotel → WebSocket → Gemini Live → tools → n8n
Call end → n8n → Google Sheets + WhatsApp summary
```

---

## 2. Environment variables

Copy structure from `.env.example`. Key groups:

| Group | Important vars |
|-------|----------------|
| Providers | `AI_PROVIDER=gemini`, `TELEPHONY_PROVIDER=plivo` |
| Public URL | `PUBLIC_HOST`, `PORT` |
| Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_SILENCE_MS`, soft-reset vars |
| Plivo | `TELEPHONY_PROVIDER=plivo` (no extra sample-rate vars — mu-law 8kHz) |
| Exotel | `EXOTEL_SAMPLE_RATE=8000`, `EXOTEL_FRAME_BYTES=1600` |
| Business | `BUSINESS_NAME`, `GREETING`, `data/business_knowledge.md` |
| n8n | `N8N_WEBHOOK_URL`, `NOTIFY_WHATSAPP` |
| Lifecycle | `SILENCE_TIMEOUT_SEC`, `MAX_CALL_DURATION_SEC`, `AI_RESPONSE_NUDGE_SEC` |

Restart `python app.py` after any `.env` change.

---

## 3. Telephony — Plivo (recommended)

**Full step-by-step (KYC → number → first call):** **[PLIVO_SETUP.md](PLIVO_SETUP.md)**

Best for **global** numbers and ResilioHub SaaS. Docs: [Plivo Voice](https://www.plivo.com/docs/voice/quickstart/quickstart).

### Production checklist

| Step | Action |
|------|--------|
| 1 | Complete Plivo **compliance** (India: CoI/Udyam + GST/PAN) — [India numbers](https://www.plivo.com/docs/numbers/rent-india-numbers) |
| 2 | Buy number → **Phone Numbers → Buy Numbers** |
| 3 | **Voice Applications** → Answer URL = `https://<PUBLIC_HOST>/plivo/answer` |
| 4 | Assign application to your Plivo number |
| 5 | `.env` → `TELEPHONY_PROVIDER=plivo`, restart voice agent |
| 6 | Call the number — logs should show stream connect + AI greeting |

### Inbound (customer → AI)

- Answer URL returns Stream XML → WebSocket `wss://<PUBLIC_HOST>/plivo/stream`
- Audio: mu-law 8 kHz (handled in `bridge.py` / `audio.py`)

### Outbound (future — you dial customer)

- `POST https://api.plivo.com/v1/Account/{auth_id}/Call/`
- `from` = your Plivo number, `to` = customer, `answer_url` = same stream pattern
- [Calls API](https://www.plivo.com/docs/voice/api/calls)
- **India:** outbound caller ID must be a **rented Indian Plivo number**

### Plivo doc links

| Topic | URL |
|-------|-----|
| Numbers | https://www.plivo.com/docs/numbers |
| India KYC | https://www.plivo.com/docs/numbers/rent-india-numbers |
| Voice quickstart | https://www.plivo.com/docs/voice/quickstart/quickstart |
| Calls API | https://www.plivo.com/docs/voice/api/calls |
| Number porting | https://www.plivo.com/docs/numbers/number-porting |

---

## 4. Telephony — Exotel (alternative)

India-focused. Use if Plivo compliance is pending.

| Step | Action |
|------|--------|
| 1 | Buy **ExoPhone** (not trial — trial may ask for PIN) |
| 2 | App Bazaar → **Voicebot** applet (bidirectional) |
| 3 | URL: `wss://<PUBLIC_HOST>/exotel/stream?sample-rate=8000` or `https://<PUBLIC_HOST>/exotel/ws-url` |
| 4 | Match `EXOTEL_SAMPLE_RATE=8000` in `.env` |
| 5 | Assign flow to ExoPhone |

Docs: [Exotel Developer](https://developer.exotel.com/) · [ExoPhone setup](https://developer.exotel.com/docs/getting-started/exophone-setup)

Switch provider: change `TELEPHONY_PROVIDER` in `.env` only — no code change.

---

## 5. Voice & persona

### Gemini voices (`.env` → `VOICE`)

| Name | Character |
|------|-----------|
| **Erinome** | Clear, professional |
| **Kore** | Firm, confident |
| **Aoede** | Breezy, friendly |
| **Achernar** | Soft, calm |

### Persona vars

| Var | Purpose |
|-----|---------|
| `AGENT_NAME` | Optional spoken name |
| `VOICE_PERSONA` | Tone line (warm, short sentences) |
| `GREETING` | First-turn hint; offer English/Hindi if needed |
| `SYSTEM_PROMPT` | Core rules — built with `knowledge.py` at startup |

### AI provider swap

| Provider | Env |
|----------|-----|
| Gemini Live (default) | `AI_PROVIDER=gemini`, `GEMINI_API_KEY` |
| OpenAI Realtime | `AI_PROVIDER=openai`, `OPENAI_API_KEY` |

---

## 6. Business knowledge & RAG

| Source | Config |
|--------|--------|
| Curated FAQ | Edit **`data/business_knowledge.md`** (best accuracy) |
| Website scrape | `BUSINESS_WEBSITE` in `.env` |
| Extra line | `BUSINESS_CONTEXT` |

**`lookup_knowledge` tool:** searches local file first (`KNOWLEDGE_SEARCH_LOCAL_FIRST=true`), then n8n/backend if empty.

For large FAQ: add Google Sheet tab or your API — see optional RAG section in n8n workflow.

---

## 7. n8n & Google Sheets

### Import workflow

1. n8n → Import **`n8n/voice_agent_actions.json`** → Activate
2. Set `N8N_WEBHOOK_URL` in `.env` to production webhook URL
3. n8n env: `RESILIOHUB_API_TOKEN` (WhatsApp node)

### Google Sheets — three tabs

Row 1 headers from CSV files in `n8n/`:

| Tab | Headers file |
|-----|----------------|
| `voice_calls` | `voice_calls_headers.csv` |
| `voice_transcripts` | `voice_transcripts_headers.csv` |
| `voice_actions` | `voice_actions_headers.csv` |

Sheet nodes use **auto-map input data** — column names must match exactly.

### Maintain Build Call Log JS

Edit **`n8n/build_call_log.js`**, then:

```bash
python scripts/sync_n8n_workflow.py
```

Re-import or deploy updated `voice_agent_actions.json` in n8n.

### n8n flow (simplified)

```
Webhook ← voice-agent
  → call_ended → Build Call Log → Sheets + WhatsApp
  → book_appointment / create_lead / … → voice_actions tab
```

---

## 8. Features (stability, summaries)

### Long-call stability

| Feature | Env | Purpose |
|---------|-----|---------|
| Soft session reset | `GEMINI_SOFT_RESET_EVERY_TURNS`, `GEMINI_SOFT_RESET_EVERY_SEC` | New Gemini session + digest — less latency/memory loss |
| Context compression | `GEMINI_CONTEXT_COMPRESSION=true` | Gemini compresses long audio context |
| Listening tuning | `GEMINI_SILENCE_MS`, `CALLER_LISTEN_GRACE_SEC` | AI waits for caller — less interrupting |

### Call summaries

- Generated in **`call_digest.py`** (Python) and **`n8n/build_call_log.js`** (Sheets/WhatsApp)
- Filters STT noise (wrong language, junk fragments)
- English narrative for owners — full transcript in `voice_transcripts` tab

### Mid-call tools

| Tool | Purpose |
|------|---------|
| `book_appointment` | Capture booking |
| `create_lead` | Sales lead |
| `lookup_knowledge` | RAG search |
| `send_notification` | Alert team |
| `end_call` | Hang up after farewell |

---

## 9. Troubleshooting

| Issue | Fix |
|-------|-----|
| Plivo inbound 404 | Answer URL public; Voice app assigned to number |
| Exotel PIN prompt | Use purchased ExoPhone, not trial |
| No AI voice | Check `PUBLIC_HOST`, Gemini key, pm2/logs |
| WebSocket 502 | nginx Upgrade headers for `/plivo/` or `/exotel/` |
| AI stops after few questions | Soft reset env vars; check Gemini logs |
| AI interrupts caller | Raise `GEMINI_SILENCE_MS`, `AI_RESPONSE_NUDGE_SEC` |
| Bad summary in sheet | Restart bridge; re-sync n8n `build_call_log.js` |
| Duplicate sheet rows | Upsert on `call_id`; headers must match CSV |
| `lookup_knowledge` empty | Expand `business_knowledge.md` with clear headings |

**Logs:** `pm2 logs voice-agent` or console where `python app.py` runs.

---

## 10. Scripts

| Script | Purpose |
|--------|---------|
| `scripts/sync_n8n_workflow.py` | Copy `build_call_log.js` → workflow JSON |
| `scripts/generate_flow_pdf.py` | Regenerate architecture PDF (`pip install reportlab`) |

Neither script runs at call time — dev/ops only.

---

## Roadmap (not in this repo yet)

| Phase | Feature |
|-------|---------|
| Now | Single business, Plivo/Exotel, n8n, Sheets |
| Next | Node backend call inbox — see [INTEGRATION.md](INTEGRATION.md) |
| Later | Multi-tenant per client, outbound, human transfer |
