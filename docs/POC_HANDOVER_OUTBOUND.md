# POC Guide — Human Handover + Outbound Calls

Use this doc to demo **two features** to your manager:

1. **Human handover** — caller asks for a person → AI transfers to your mobile  
2. **Outbound calls** — system calls a customer → AI starts conversation  

**Stack:** Plivo + Gemini Live + this Python bridge (no Retell/Vapi needed).

---

## Before the demo (15 min setup)

### 1. Add to `.env`

```env
# Plivo console → Account → Auth ID / Auth Token
PLIVO_AUTH_ID=MAxxxxxxxxxx
PLIVO_AUTH_TOKEN=your_auth_token

# Your Plivo number
PLIVO_FROM_NUMBER=+912264233283

# Your mobile — receives transferred calls
HUMAN_AGENT_NUMBER=+9198XXXXXXXX

# Protect outbound API
OUTBOUND_API_SECRET=pick-a-long-random-string

# Optional: ring YOU first; if busy/no answer → AI
AGENT_FIRST_ENABLED=false
AGENT_FIRST_TIMEOUT_SEC=25
```

Restart voice agent after saving:

```powershell
python app.py
```

### 2. Verify health

```bash
curl https://YOUR_PUBLIC_HOST/health
```

Expected:

```json
{
  "status": "ok",
  "telephony": "plivo",
  "human_transfer": true,
  "agent_first": false
}
```

---

## Demo 1 — AI → Human transfer (inbound)

**Story for manager:** *"Customer calls our business number. AI handles FAQ. When they ask for a human, call goes to our sales/support mobile."*

### Steps

1. Call your Plivo number: `+91 22 6423 3283` (or your number).
2. Ask AI a question (e.g. "What services do you offer?").
3. Say: **"I want to talk to a real person"** or **"Connect me to your team"**.
4. AI says: *"I'll connect you to our team now."*
5. Your `HUMAN_AGENT_NUMBER` rings — answer and talk to the caller.

### What happens technically

```
Caller → Plivo → AI stream → transfer_to_human tool
       → Plivo redirects call → /plivo/transfer → Dial your mobile
```

Call log still goes to n8n (Sheet + WhatsApp) with outcome **"Transferred to human agent"**.

---

## Demo 2 — Agent-first (optional)

**Story:** *"We ring the human first. If nobody picks up in 25 seconds, AI takes over."*

Set in `.env`:

```env
AGENT_FIRST_ENABLED=true
```

Restart app. Call inbound number:

1. Your mobile rings first.
2. **Don't answer** → after ~25s caller hears fallback message → AI answers.
3. **Do answer** → you talk directly (no AI).

Turn off after demo: `AGENT_FIRST_ENABLED=false`.

---

## Demo 3 — Outbound call

**Story:** *"System can call a lead back — same AI receptionist, outbound direction logged in sheets."*

### Trigger outbound call

```powershell
curl -X POST "https://YOUR_PUBLIC_HOST/plivo/outbound" `
  -H "Content-Type: application/json" `
  -H "x-voice-secret: YOUR_OUTBOUND_API_SECRET" `
  -d '{"to": "+9198XXXXXXXX"}'
```

Replace `to` with the phone to dial (E.164, include `+91`).

### Expected

- Customer phone rings.
- They answer → AI greeting (same as inbound).
- Conversation works; call ends → Sheet row with `direction: outbound`.

### From n8n or Node later

Same HTTP POST from your backend when a lead is created — no code change needed in bridge.

---

## Manager talking points

| Feature | Business value |
|---------|----------------|
| AI inbound 24/7 | Never miss calls; FAQ + lead capture |
| Human handover | Complex deals / angry customers → real person |
| Agent-first | Small team answers first; AI backup when busy |
| Outbound | Follow up website leads automatically |
| Cost | Plivo per-minute + Gemini free tier; no SaaS platform fee |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Transfer says ok but phone doesn't ring | Check `HUMAN_AGENT_NUMBER` is E.164 (`+91...`) |
| Outbound 401 | Wrong `x-voice-secret` header |
| Outbound 503 | Set `PLIVO_AUTH_ID` + `PLIVO_AUTH_TOKEN` |
| Agent-first always AI | Set `AGENT_FIRST_ENABLED=true` and restart |
| Transfer fails silently | Plivo creds missing in `.env` |

---

## API reference

| Method | URL | Purpose |
|--------|-----|---------|
| GET/POST | `/plivo/answer` | Inbound / outbound answer XML |
| GET/POST | `/plivo/transfer` | Human dial XML (used by redirect) |
| POST | `/plivo/dial-status` | Agent-first fallback |
| POST | `/plivo/outbound` | Start outbound call |
| WS | `/plivo/stream` | Live audio bridge |

---

## Next after POC

1. Move from cloudflared → VPS fixed URL  
2. Node backend: `POST /voice/outbound` wrapper + call inbox UI  
3. Multi-tenant: per-client agent number + Plivo number  

See [INTEGRATION.md](INTEGRATION.md).
