# AI Voice Receptionist — Core Bridge

Phone audio (Plivo or Exotel) ↔ Gemini Live (or OpenAI Realtime) ↔ n8n business actions.

```
Caller → Plivo/Exotel → WebSocket → AI → tools → n8n → Sheets / WhatsApp
```

## Documentation

| Doc | For |
|-----|-----|
| **[docs/GUIDE.md](docs/GUIDE.md)** | Setup, env, Plivo/Exotel, voice, n8n, Sheets, troubleshooting |
| **[docs/INTEGRATION.md](docs/INTEGRATION.md)** | ResilioHub Node backend, multi-tenant, product rollout |
| `docs/Voice_Agent_Complete_Flow_Guide.pdf` | Visual architecture (regenerate: `python scripts/generate_flow_pdf.py`) |

## Quick start

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Dev tunnel: `cloudflared tunnel --url http://localhost:5000` → set `PUBLIC_HOST` in `.env`.

## Providers (`.env`)

| Layer | Options | SaaS default |
|-------|---------|--------------|
| AI | `gemini` / `openai` | `gemini` |
| Telephony | `plivo` / `exotel` | `plivo` (global) |

Flip `TELEPHONY_PROVIDER` and restart — no code change.

## Project layout

```
app.py, bridge.py, config.py, audio.py
knowledge.py, call_digest.py, tools.py
provider_gemini.py, provider_openai.py, plivo_xml.py

data/business_knowledge.md    # Company FAQ
n8n/voice_agent_actions.json  # Import into n8n
n8n/build_call_log.js         # Summary logic (sync via scripts/sync_n8n_workflow.py)
docs/GUIDE.md                 # Operations
docs/INTEGRATION.md           # Product / backend
scripts/                      # n8n sync, PDF generator
```

## n8n

Import `n8n/voice_agent_actions.json`, activate, set `N8N_WEBHOOK_URL` in `.env`.

Sheet headers: `n8n/*_headers.csv`.
