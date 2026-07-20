# AI Voice Receptionist - Core Bridge

Small Python switchboard: phone call audio (Exotel or Plivo) <-> AI (Gemini Live or OpenAI Realtime) <-> n8n tools.
No database, no auth UI.

## Providers (swappable)

| Layer | Options | Default now |
|-------|---------|-------------|
| AI | `gemini` (free) / `openai` (paid) | `gemini` |
| Telephony | `exotel` / `plivo` | `exotel` |

Set in `.env`:

```
AI_PROVIDER=gemini
TELEPHONY_PROVIDER=exotel
```

When Plivo compliance is approved later, flip `TELEPHONY_PROVIDER=plivo` and point Plivo Answer URL at `/plivo/answer`. No other code change.

## Flow

```
Caller -> Exotel/Plivo -> WebSocket /exotel/stream or /plivo/stream
      <-> Gemini/OpenAI (audio)
      Tool call -> n8n webhook -> AI speaks result
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | HTTP + WebSocket routes for Exotel and Plivo |
| `bridge.py` | Dual telephony relay + barge-in + n8n tools |
| `provider_*.py` | Gemini / OpenAI backends |
| `audio.py` | PCM/mu-law, resampling, Exotel frame buffer |
| `n8n/voice_agent_actions.json` | Importable n8n stub |

See **[docs/VOICE_AND_PERSONA.md](docs/VOICE_AND_PERSONA.md)** for voice names, LLM options, and persona tuning.

## Phase 1 (stability + RAG + Sheets)

See **[docs/PHASE1_SETUP_GUIDE.md](docs/PHASE1_SETUP_GUIDE.md)** for Google Sheet tabs, n8n import, env vars, and tests.

## Setup

```bash
cd voice-agent
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
cp .env.example .env         # fill keys + PUBLIC_HOST + N8N_WEBHOOK_URL
python app.py
```

Tunnel (keep running):

```bash
cloudflared tunnel --url http://localhost:5000
```

Put tunnel host (no `https://`) into `PUBLIC_HOST`. Health check:

`https://<PUBLIC_HOST>/health` -> `{"status":"ok","ai":"gemini","telephony":"exotel"}`

---

## Exotel setup (primary)

Exotel India often still needs KYC before a live number works — check your dashboard. If you already have an Exotel account + number, use **Voicebot** (bidirectional), not Stream (one-way).

1. App Bazaar → create / edit **Custom App** call flow.
2. Drop **Voicebot** applet.
3. URL — either:
   - **Static:** `wss://<PUBLIC_HOST>/exotel/stream?sample-rate=8000`
   - **Dynamic:** `https://<PUBLIC_HOST>/exotel/ws-url` (returns `{"url":"wss://..."}`)
4. Sample rate: match `.env` `EXOTEL_SAMPLE_RATE` (default `8000`).
5. Save flow → attach to your Exotel virtual number.
6. Call the number. Logs should show `connected`, `Stream start`, then AI greeting.

### Exotel audio notes

- Wire format: **raw PCM 16-bit little-endian** (not mu-law).
- Outbound frames buffered to **~100ms (3200 bytes @ 8kHz)** per Exotel rules.
- Barge-in uses Exotel `clear` event.

---

## Plivo setup (fallback after compliance)

1. Complete Plivo **Add Compliance** (CoI/Udyam + GST/PAN).
2. Create XML Application → Answer URL:
   `https://<PUBLIC_HOST>/plivo/answer`
3. Assign number to that application.
4. Set `.env` `TELEPHONY_PROVIDER=plivo`, restart `python app.py`.

---

## n8n

Import `n8n/voice_agent_actions.json`, activate, paste production webhook URL into `N8N_WEBHOOK_URL`.

## Switch later

| Goal | Change |
|------|--------|
| Use Plivo | `TELEPHONY_PROVIDER=plivo` + Plivo Answer URL |
| Use OpenAI | `AI_PROVIDER=openai` + `OPENAI_API_KEY` |

Honest caveat: Exotel AgentStream must be enabled on your account — if Voicebot applet is missing, ask Exotel support to enable streaming / AgentStream.
