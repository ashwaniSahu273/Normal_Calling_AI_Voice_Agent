# Plivo — Complete Setup Guide (AI Voice Agent)

Step-by-step guide to connect **Plivo** to this voice-agent repo after **KYC is approved**.

**You need:** Plivo account (KYC done), Gemini API key, n8n webhook (optional), a public HTTPS URL.

**How the system works (diagrams, all URLs, every file):** **[FLOW.md](FLOW.md)**  
**Official Plivo docs:** [Voice quickstart](https://www.plivo.com/docs/voice/quickstart/quickstart) · [Numbers](https://www.plivo.com/docs/numbers) · [India numbers](https://www.plivo.com/docs/numbers/rent-india-numbers)

---

## Table of contents

1. [Overview — how Plivo connects to this repo](#1-overview--how-plivo-connects-to-this-repo)
2. [Checklist (print this)](#2-checklist-print-this)
3. [Step 1 — Buy a Plivo phone number](#3-step-1--buy-a-plivo-phone-number)
4. [Step 2 — Configure this project (.env)](#4-step-2--configure-this-project-env)
5. [Step 3 — Run the voice agent locally](#5-step-3--run-the-voice-agent-locally)
6. [Step 4 — Public HTTPS URL (tunnel for testing)](#6-step-4--public-https-url-tunnel-for-testing)
7. [Step 5 — Create Plivo XML Application](#7-step-5--create-plivo-xml-application)
8. [Step 6 — Assign number to the application](#8-step-6--assign-number-to-the-application)
9. [Step 7 — Test your first call](#9-step-7--test-your-first-call)
10. [Step 8 — n8n + WhatsApp (optional)](#10-step-8--n8n--whatsapp-optional)
11. [Step 9 — Production server (VPS + nginx)](#11-step-9--production-server-vps--nginx)
12. [Troubleshooting](#12-troubleshooting)
13. [Outbound calls (later)](#13-outbound-calls-later)
14. [Quick reference](#14-quick-reference)

---

## 1. Overview — how Plivo connects to this repo

> Full diagrams + every URL/file: **[FLOW.md](FLOW.md)**

```
Caller dials your Plivo number
        ↓
Plivo → GET/POST https://YOUR_HOST/plivo/answer     ← only URL you paste in Plivo console
        ↓
Your server returns XML → Plivo opens wss://YOUR_HOST/plivo/stream  (automatic)
        ↓
bridge.py ↔ Gemini Live (AI speaks & listens)
        ↓
Call ends → n8n → Google Sheet + WhatsApp (optional)
```

| URL | Who calls it | Purpose |
|-----|--------------|---------|
| `https://<PUBLIC_HOST>/plivo/answer` | Plivo (Answer URL) | Returns Stream / Dial XML |
| `wss://<PUBLIC_HOST>/plivo/stream` | Plivo (from XML `<Stream>`) | Bidirectional audio |
| `https://<PUBLIC_HOST>/plivo/stream-status` | Plivo (from XML callback) | Stream events + caller number |
| `https://<PUBLIC_HOST>/plivo/transfer` | Plivo (after Transfer API) | Dial human agent |
| `https://<PUBLIC_HOST>/plivo/dial-status` | Plivo (agent-first Dial) | Fallback to AI |
| `https://<PUBLIC_HOST>/plivo/outbound` | You / n8n (REST) | Start outbound call |
| `https://<PUBLIC_HOST>/health` | You | Health check |

**Audio:** Plivo uses **G.711 mu-law @ 8 kHz** — handled in `bridge.py` and `audio.py`.

**Inbound needs no Plivo Auth in console wiring** — Plivo calls *your* Answer URL.  
`PLIVO_AUTH_ID` / `PLIVO_AUTH_TOKEN` are required for **outbound** and **AI→human transfer**.

---

## 2. Checklist (print this)

- [ ] Plivo KYC approved
- [ ] Plivo account has **credits** (billing)
- [ ] Phone number purchased (Voice enabled)
- [ ] `.env` → `TELEPHONY_PROVIDER=plivo`
- [ ] `.env` → `GEMINI_API_KEY` set
- [ ] `.env` → `PUBLIC_HOST` = your public domain (no `https://`)
- [ ] Voice agent running (`python app.py`)
- [ ] `/health` returns `"telephony":"plivo"`
- [ ] Plivo XML Application → Answer URL set
- [ ] Number assigned to that application
- [ ] Test call → AI greeting heard

---

## 3. Step 1 — Buy a Plivo phone number

1. Log in to [Plivo Console](https://console.plivo.com/).
2. Go to **Phone Numbers** → **Buy Numbers** (or **Rent Numbers**).
3. Select:
   - **Country:** India (or your target country)
   - **Capabilities:** **Voice** ✓ (SMS optional)
   - **Number type:** Local / Mobile / Toll-free as available
4. Complete purchase.
5. Note your number in **E.164** format, e.g. `+9198XXXXXXXX`.

**India:** After KYC, Indian DIDs should be available. If not, check **Compliance** section in console — [Rent India numbers](https://www.plivo.com/docs/numbers/rent-india-numbers).

**Credits:** Ensure wallet has balance — inbound/outbound calls consume credits.

---

## 4. Step 2 — Configure this project (.env)

Open `.env` in the project root. Minimum for Plivo:

```env
# Providers
AI_PROVIDER=gemini
TELEPHONY_PROVIDER=plivo

# Public URL — hostname ONLY (no https://, no trailing slash)
PUBLIC_HOST=your-subdomain.trycloudflare.com
PORT=5000

# Gemini
GEMINI_API_KEY=your_key_from_aistudio.google.com
GEMINI_MODEL=gemini-3.1-flash-live-preview

# Business
BUSINESS_NAME=ResilioHub
GREETING=Thank you for calling ResilioHub. I can help in English or Hindi — how may I help you?

# n8n (optional but recommended)
N8N_WEBHOOK_URL=https://your-n8n-host/webhook/voice-agent
NOTIFY_WHATSAPP=916264904864
```

**Important:**

| Variable | Value for Plivo |
|----------|-----------------|
| `TELEPHONY_PROVIDER` | **`plivo`** (required) |
| `PUBLIC_HOST` | Must match what Plivo can reach over HTTPS |
| `EXOTEL_*` | Ignored when using Plivo |

Edit **`data/business_knowledge.md`** with your company FAQ (AI answers from this file).

---

## 5. Step 3 — Run the voice agent locally

```powershell
cd C:\Users\...\voice-agent
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

You should see logs like:

```
Started ai=gemini telephony=plivo voice=Erinome ...
```

**Local check (before tunnel):**

```powershell
curl http://localhost:5000/health
```

Expected:

```json
{"status":"ok","ai":"gemini","telephony":"plivo"}
```

If `telephony` shows `exotel`, fix `.env` and restart.

---

## 6. Step 4 — Public HTTPS URL (tunnel for testing)

Plivo must reach your server from the internet. For **development**, use **cloudflared**:

**Terminal 1** — voice agent (already running):

```powershell
python app.py
```

**Terminal 2** — tunnel:

```powershell
cloudflared tunnel --url http://localhost:5000
```

Copy the hostname from output, e.g.:

```
https://random-words-here.trycloudflare.com
```

Put **only the hostname** in `.env`:

```env
PUBLIC_HOST=random-words-here.trycloudflare.com
```

**Restart `python app.py`** after changing `PUBLIC_HOST`.

**Verify from browser or curl:**

```
https://random-words-here.trycloudflare.com/health
```

→ `{"status":"ok","ai":"gemini","telephony":"plivo"}`

**Verify Answer URL returns XML:**

```
https://random-words-here.trycloudflare.com/plivo/answer
```

Expected XML (similar):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Stream bidirectional="true" keepCallAlive="true"
    contentType="audio/x-mulaw;rate=8000">wss://random-words-here.trycloudflare.com/plivo/stream</Stream>
</Response>
```

> **Note:** cloudflared URL changes each restart unless you use a named Cloudflare tunnel. Update `PUBLIC_HOST` and Plivo Answer URL when it changes.

---

## 7. Step 5 — Create Plivo XML Application

1. Plivo Console → **Voice** → **Applications** → **Create New Application**.
2. Fill in:

| Field | Value |
|-------|-------|
| **Application name** | e.g. `ResilioHub AI Voice` |
| **Application type** | **XML** |
| **Answer URL** | `https://<PUBLIC_HOST>/plivo/answer` |
| **Answer method** | `GET` or `POST` (both work — our app accepts both) |
| **Hangup URL** | Leave empty for now (optional later) |

**Example Answer URL:**

```
https://random-words-here.trycloudflare.com/plivo/answer
```

3. **Save** the application.
4. Copy the **Application ID** (you may need it for API provisioning later).

**What happens on a call:** Plivo fetches Answer URL → gets XML → opens WebSocket to `wss://.../plivo/stream` → AI conversation starts.

---

## 8. Step 6 — Assign number to the application

1. Console → **Phone Numbers** → **Your Numbers**.
2. Click your number (e.g. `+91 22 6423 3283`).
3. Configure the number form:

| Field | Select |
|-------|--------|
| **Alias** | Any label, e.g. `Ai` or `ResilioHub Voice` |
| **Application Type** | **Application** ← NOT "AI Agents", NOT "SIP Trunk" |
| **Application** | Your XML app, e.g. `ResilioHub AI Voice` |
| **Associated Call Agent Flow** | **Leave empty** (only for Plivo's built-in AI Agents product) |
| **Sub Account** | Default / none (unless you use sub-accounts) |
| **High availability backup number** | **Off** for now (optional paid feature) |

4. **Save**.

> **Important:** We use **your own Python + Gemini** bridge, not Plivo "AI Agents". Always pick **Application Type → Application** and point it to an **XML Application** whose Answer URL is `https://<PUBLIC_HOST>/plivo/answer`.

Without this step, calls will not hit your Answer URL.

---

## 9. Step 7 — Test your first call

1. Confirm voice agent + tunnel are running.
2. Confirm `PUBLIC_HOST` in `.env` matches tunnel hostname.
3. Dial your Plivo number from your mobile.

**Expected:**

| Step | What you should see/hear |
|------|---------------------------|
| Phone rings | Call connects |
| ~1–3 sec | AI greeting (from `GREETING` in `.env`) |
| You speak | AI responds |
| You say thanks/bye | Call ends gracefully |

**Expected logs (terminal running `python app.py`):**

```
Stream start call_id=... stream_id=... from=+91...
Gemini Live ready ...
```

**If call fails immediately:** see [Troubleshooting](#12-troubleshooting).

**After call ends:** If n8n is configured, check Google Sheet + WhatsApp summary.

---

## 10. Step 8 — n8n + WhatsApp (optional)

1. Import **`n8n/voice_agent_actions.json`** into n8n.
2. Activate workflow.
3. Copy production webhook URL → `.env`:

   ```env
   N8N_WEBHOOK_URL=https://agent.resiliencesoft.com/webhook/voice-agent
   ```

4. Configure Google Sheets nodes (tabs: `voice_calls`, `voice_transcripts`, `voice_actions`).
5. Set n8n env: `RESILIOHUB_API_TOKEN` for WhatsApp node.
6. Set `.env`:

   ```env
   NOTIFY_WHATSAPP=91XXXXXXXXXX
   ```

Details: [GUIDE.md § n8n](GUIDE.md#7-n8n--google-sheets)

---

## 11. Step 9 — Production server (VPS + nginx)

For **real use** (not cloudflared), deploy on a VPS with a fixed domain, e.g. `voice.resiliencesoft.com`.

### 11.1 Deploy code

```bash
cd /opt/voice-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# copy .env with production PUBLIC_HOST
```

Run with **pm2** or **systemd**:

```bash
pm2 start "python app.py" --name voice-agent --cwd /opt/voice-agent
```

### 11.2 nginx (SSL + WebSocket)

```nginx
server {
    listen 443 ssl;
    server_name voice.resiliencesoft.com;

    # ssl_certificate ... (certbot / your certs)

    location /plivo/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location /health {
        proxy_pass http://127.0.0.1:5000/health;
    }
}
```

### 11.3 Update Plivo + `.env`

```env
PUBLIC_HOST=voice.resiliencesoft.com
TELEPHONY_PROVIDER=plivo
```

Plivo Application **Answer URL:**

```
https://voice.resiliencesoft.com/plivo/answer
```

Restart voice agent after any `.env` change.

---

## 12. Troubleshooting

| Problem | Cause | Fix |
|---------|--------|-----|
| Call does not connect | Number not assigned to app | Step 6 — link number to XML Application |
| Immediate hangup | Answer URL wrong / not public | Open Answer URL in browser — must return XML |
| `PUBLIC_HOST is not configured` | Empty `PUBLIC_HOST` | Set hostname in `.env`, restart |
| Health shows `exotel` | Wrong provider in `.env` | `TELEPHONY_PROVIDER=plivo`, restart |
| No AI voice, call silent | Gemini key missing / invalid | Check `GEMINI_API_KEY`, logs for errors |
| WebSocket error | Tunnel down or nginx missing Upgrade | Restart cloudflared; fix nginx `Upgrade` headers |
| XML shows wrong WSS host | Stale `PUBLIC_HOST` | Update `.env` to match tunnel/domain, restart |
| AI speaks but very delayed | Network / Gemini | See latency vars in `.env.example` |
| n8n not triggered | Wrong webhook URL | Match `N8N_WEBHOOK_URL` to active n8n workflow |
| `POST /plivo/answer%20` 404 / busy tone | Trailing **space** in Plivo Answer URL | Remove space after `/plivo/answer` in Plivo app; restart voice agent (middleware also trims) |

**Test Answer URL manually:**

```bash
curl -i https://YOUR_PUBLIC_HOST/plivo/answer
```

Content-Type should be `application/xml`.

**Plivo call logs:** Console → **Voice** → **Logs** → inspect Answer URL fetch status and errors.

---

## 13. Outbound calls + human handover

Implemented in this repo. Demo steps + diagrams: **[FLOW.md](FLOW.md)** §12 (POC demos) and §6–7.

**Outbound** — `POST https://YOUR_HOST/plivo/outbound` with header `x-voice-secret`:

```json
{ "to": "+91XXXXXXXXXX", "purpose": "confirm demo Friday 3 PM" }
```

Plivo then hits the same Answer URL with `?direction=outbound&ctx=…`.

**Human transfer** — AI calls `transfer_to_human` tool → Plivo redirects to `/plivo/transfer` → dials `HUMAN_AGENT_NUMBER`.

**Agent-first** — set `AGENT_FIRST_ENABLED=true` in `.env`; rings human before AI.

Required `.env`: `PLIVO_AUTH_ID`, `PLIVO_AUTH_TOKEN`, `PLIVO_FROM_NUMBER`, `HUMAN_AGENT_NUMBER`, `OUTBOUND_API_SECRET`.

Docs: [Calls API](https://www.plivo.com/docs/voice/api/calls)

---

## 14. Quick reference

| Item | Value |
|------|--------|
| `.env` telephony | `TELEPHONY_PROVIDER=plivo` |
| Answer URL | `https://<PUBLIC_HOST>/plivo/answer` |
| WebSocket | `wss://<PUBLIC_HOST>/plivo/stream` |
| Health | `https://<PUBLIC_HOST>/health` |
| Audio format | mu-law 8 kHz |
| Code files | `app.py`, `plivo_xml.py`, `bridge.py` |
| Plivo console | https://console.plivo.com/ |

---

## Next steps

| Goal | Doc |
|------|-----|
| Architecture + all URLs/files | **[FLOW.md](FLOW.md)** |
| Full ops (env, voice, Sheets) | [GUIDE.md](GUIDE.md) |
| ResilioHub Node backend + multi-tenant | [INTEGRATION.md](INTEGRATION.md) |

---

*Last updated: 2026-08-07 — Post-KYC Plivo + FLOW.md*
