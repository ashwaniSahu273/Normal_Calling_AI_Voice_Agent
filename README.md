# AI Voice Receptionist — Core Bridge

Phone audio (Plivo or Exotel) ↔ Gemini Live (or OpenAI Realtime) ↔ n8n business actions.

```
Caller → Plivo/Exotel → WebSocket → AI → tools → n8n → Sheets / WhatsApp
```

## Documentation

| Doc | For |
|-----|-----|
| **[docs/FLOW.md](docs/FLOW.md)** | **How it works** — diagrams, why only `/plivo/answer` in console, all URLs + files |
| **[docs/PRODUCT_MULTI_TENANT.md](docs/PRODUCT_MULTI_TENANT.md)** | **WhatsAppCRM feature** — Plivo reseller, KYC, numbers, is it possible? |
| **[docs/PLIVO_SETUP.md](docs/PLIVO_SETUP.md)** | Plivo step-by-step (KYC → number → first call) |
| **[docs/GUIDE.md](docs/GUIDE.md)** | Setup, env, voice, n8n, Sheets, troubleshooting |
| **[docs/INTEGRATION.md](docs/INTEGRATION.md)** | ResilioHub Node backend, multi-tenant, product rollout |

## Quick start

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Dev tunnel: `cloudflared tunnel --url http://localhost:5000` → set `PUBLIC_HOST` in `.env`.

**Understand the system:** open **[docs/FLOW.md](docs/FLOW.md)** first.

## Providers (`.env`)

| Layer | Options | SaaS default |
|-------|---------|--------------|
| AI | `gemini` / `openai` | `gemini` |
| Telephony | `plivo` / `exotel` | `plivo` (global) |

Flip `TELEPHONY_PROVIDER` and restart — no code change.

## Project layout

```
app.py              # HTTP + WebSocket routes
bridge.py           # Call switchboard
plivo_xml.py        # Plivo XML (Stream / Dial / transfer)
plivo_client.py     # Outbound + transfer REST
call_meta.py        # Caller phone cache
outbound_ctx.py     # Outbound purpose cache
provider_gemini.py  # Gemini Live
knowledge.py        # Prompts + RAG
tools.py            # n8n tools
call_digest.py      # Summaries
audio.py            # Codecs

data/business_knowledge.md
n8n/voice_agent_actions.json
docs/FLOW.md                 # Architecture (start here)
docs/PRODUCT_MULTI_TENANT.md # Sell as WhatsAppCRM feature
docs/PLIVO_SETUP.md
docs/GUIDE.md
docs/INTEGRATION.md
```

## n8n

Import `n8n/voice_agent_actions.json`, activate, set `N8N_WEBHOOK_URL` in `.env`.

Sheet headers: `n8n/*_headers.csv`.
