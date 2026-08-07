# ResilioHub — Product Integration & Multi-Tenant Guide

For **running the voice bridge** (env, Plivo, n8n, Sheets) see **[GUIDE.md](GUIDE.md)**.  
For **architecture diagrams** (URLs, files, inbound/outbound/transfer) see **[FLOW.md](FLOW.md)**.

This document covers:

1. **Multi-tenant** — offering AI phone to every ResilioHub client (simple language)
2. **Node backend** — how developers connect web, Flutter, and database
3. **Rollout plan** — what to build in what order

**Telephony choice for SaaS:** **Plivo** (global). Exotel remains supported for India-only fallback.

---

# Part 1 — Multi-tenant (simple language)

## What is multi-tenant?

**Single-tenant (today):** One company, one phone number, one AI config, one `.env`.

**Multi-tenant (product goal):** One ResilioHub platform, **many clients**. Each client gets:

- Their own phone number  
- Their own AI greeting and company knowledge  
- Their own call history  

Clients **never see each other’s data**.

**Analogy:** Like WhatsApp inbox today — many shops in one building, each with a private inbox. Multi-tenant voice adds **each shop gets its own phone line and AI receptionist**.

---

## How it works (step by step)

### 1. Every client has a tenant ID

In your database, each customer has `tenant_id` (or `account_id`).

```
Client A (101) → number +91-98xxx + knowledge + calls
Client B (102) → number +1-555xxx + knowledge + calls
```

### 2. Each client gets a Plivo number

When they enable **AI Phone**:

1. You buy/rent a number from Plivo (for their country)  
2. Link it to your voice server  
3. Save: `this number belongs to tenant 101`

### 3. When someone calls

```
Customer dials Client A's number
    → Plivo receives call
    → Your server: "This number = Client A"
    → Load Client A's greeting, FAQ, voice settings
    → AI talks (Gemini)
    → Call ends → save log under Client A only
    → Optional WhatsApp summary to Client A's owner
```

Same voice software for everyone — **config changes per client** on each call.

### 4. Where each part lives

| Part | Role |
|------|------|
| **Web / Flutter** | Client enables Voice, edits settings, views calls |
| **Node backend** | Tenants, settings, call logs, auth, billing |
| **Python voice service** | Live call audio (WebSocket + AI) |
| **Plivo** | Real phone network |
| **Gemini** | AI speech |

Node = **memory & control**. Python = **live phone call**. Plivo = **phone line**.

### 5. How the system knows which client

**Recommended:** lookup by **called number**.

Plivo sends “call to +91-98xxx” → database → Client A.

Alternative: tenant in Answer URL query string (more moving parts at scale).

### 6. What the client sees

- Voice settings (greeting, language, business info)  
- Call history (like WhatsApp inbox)  
- Full transcript per call  
- Their AI phone number for website / Google  

All filtered by login → only their `tenant_id`.

---

## Visual overview

```
Many ResilioHub clients
    ├── Client 1 → Number 1 → Config 1 → Calls (tenant 1)
    ├── Client 2 → Number 2 → Config 2 → Calls (tenant 2)
    └── Client 3 → Number 3 → Config 3 → Calls (tenant 3)
              │
    Shared: Plivo + Voice server + Gemini
    Separated: number, knowledge, logs, billing
```

---

## Challenges (simple language)

### 1. Legal & paperwork (Plivo)

- KYC / compliance before real numbers (India: CoI/Udyam + GST/PAN).  
- **Different countries = different rules.**  
- Outbound / marketing often needs customer consent.  
- One abusive client can hurt **your whole Plivo account**.

### 2. Wrong client answers (critical bug)

If mapping fails, Client B’s caller might hear **Client A’s** company info.

**Need:** strong tests, always load config by phone number / tenant, no global business `.env` in production multi-tenant.

### 3. Giving each client a phone number

You must build: search/buy number (Plivo API), attach Voice Application, save to tenant, handle “no numbers in this region”.

Harder than “connect WhatsApp.”

### 4. Money & billing

You pay Plivo (minutes), Gemini (AI), servers (load).  
Clients should pay via add-on plan or per-minute.  
Track **`duration_sec` per `tenant_id`** or you lose money.

### 5. Server load & uptime

Live calls = many open WebSockets. Server down = **missed calls** (worse than slow chat).  
Need production hosting, monitoring, maybe multiple voice workers.

### 6. AI quality & support

Speech recognition errors, accents, Hindi/English mix. Clients blame you for wrong prices. Each client needs a **good knowledge base**. Support: “AI didn’t understand”, “bad summary.”

### 7. Client expectations

Human transfer, outbound calling, using their landline as caller ID — mostly **Phase 2+**. Set expectations early.

### 8. Data privacy

Calls contain phone numbers and personal details. Need privacy policy, retention, deletion (GDPR / DPDP).

### 9. Product UI

Not just backend — clients need enable/disable, edit knowledge, call inbox in **web + Flutter**.

### 10. Global pricing

Plivo cost varies by country — hard to advertise one flat rate worldwide without country logic.

---

## Single vs multi — comparison

| | Single (now) | Multi-tenant (goal) |
|---|-------------|---------------------|
| Clients | Only you | Every ResilioHub customer |
| Numbers | One | One+ per client |
| Knowledge | One file | Per client |
| Config | `.env` | Database + dashboard |
| Billing | N/A | Plan + usage |
| Risk | You only | Many businesses |

---

## Smart rollout

| Stage | What |
|-------|------|
| **1** | One business on Plivo + Node call inbox (you only) |
| **2** | Multi-tenant DB; manual numbers for 2–3 pilot clients |
| **3** | Self-serve “Enable AI Phone” + auto provisioning + billing |

Don’t skip straight to self-serve worldwide.

---

## Plivo multi-tenant routing (technical)

**One Answer URL, lookup by `To` number:**

```
https://voice.resiliohub.com/plivo/answer
```

Plivo POSTs call metadata → lookup `tenant_id` by dialed number → return Stream XML:

```
wss://voice.resiliohub.com/plivo/stream?tenant=abc&sig=...
```

Bridge loads tenant config from Node API before AI session starts.

Extend `plivo_xml.py` for dynamic XML per tenant (small code change when you reach Stage 2).

---

# Part 2 — Node backend integration

For **ResilioHub backend developers** (Node.js). Do **not** rewrite audio/WebSocket/Gemini in Node — use Python as a **sidecar** on the same server.

## Architecture

```
Caller → Plivo → Python voice-agent (:5000) → Gemini
                    ├── tools → n8n
                    └── call_ended → n8n → POST Node → PostgreSQL
                                              └── WhatsApp (optional)

Web / Flutter → Node API (:3000) → PostgreSQL
```

## What exists vs what you build

| Component | Owner | Status |
|-----------|-------|--------|
| Plivo number + Voice app | DevOps | See [GUIDE.md § Plivo](GUIDE.md#3-telephony--plivo-recommended) |
| Python voice bridge | This repo | Done |
| n8n + Sheets | This repo | Done |
| `voice_calls` table | **Node** | Build |
| `POST /api/internal/voice/call-ended` | **Node** | Build |
| `GET /api/v1/voice/calls` | **Node** | Build |
| Web / Flutter Voice UI | **Frontend** | Build |

## Production deployment (same VPS)

| Process | Port |
|---------|------|
| ResilioHub Node API | 3000 |
| Python voice-agent | 5000 |

**nginx** (one domain, e.g. `resiliohub.com`):

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:3000;
}

location /plivo/ {
    proxy_pass http://127.0.0.1:5000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}

location /health {
    proxy_pass http://127.0.0.1:5000/health;
}
```

**Plivo Answer URL:** `https://resiliohub.com/plivo/answer`

**Production `.env` (voice server):**

```env
PUBLIC_HOST=resiliohub.com
TELEPHONY_PROVIDER=plivo
AI_PROVIDER=gemini
GEMINI_API_KEY=<secret>
N8N_WEBHOOK_URL=https://your-n8n/webhook/voice-agent
```

Never expose `GEMINI_API_KEY` to Node or clients.

---

## Database schema

### `voice_calls`

```sql
CREATE TABLE voice_calls (
  id              BIGSERIAL PRIMARY KEY,
  tenant_id       BIGINT,                    -- add for multi-tenant
  call_id         VARCHAR(64) NOT NULL UNIQUE,
  caller          VARCHAR(20),
  date            DATE,
  time            VARCHAR(16),
  duration        VARCHAR(32),
  duration_sec    INTEGER NOT NULL DEFAULT 0,
  topic           VARCHAR(128),
  summary         TEXT,
  next_step       VARCHAR(64),
  outcome         VARCHAR(128),
  transcript      TEXT,
  transcript_turns INTEGER DEFAULT 0,
  appointment_booked BOOLEAN DEFAULT FALSE,
  lead_captured   BOOLEAN DEFAULT FALSE,
  direction       VARCHAR(16) DEFAULT 'inbound',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_voice_calls_tenant ON voice_calls (tenant_id, created_at DESC);
```

### `voice_settings` (multi-tenant — Stage 2)

```sql
CREATE TABLE voice_settings (
  tenant_id       BIGINT PRIMARY KEY,
  enabled         BOOLEAN DEFAULT FALSE,
  plivo_number    VARCHAR(20),
  greeting        TEXT,
  voice_name      VARCHAR(32),
  knowledge_md    TEXT,
  notify_whatsapp VARCHAR(20),
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Internal webhook

```
POST /api/internal/voice/call-ended
Header: x-voice-secret: <VOICE_WEBHOOK_SECRET>
```

**Body** (from n8n Build Call Log — see `n8n/build_call_log.js`):

```json
{
  "call_id": "voice-1721820123456",
  "date": "2026-07-24",
  "time": "04:21 PM",
  "caller": "919876543210",
  "duration": "3 min 45 sec",
  "duration_sec": 225,
  "topic": "Mobile app development",
  "summary": "Ashwani Sahu called regarding mobile app development…",
  "next_step": "Lead — call back",
  "outcome": "Caller said thanks / done",
  "turns": 14,
  "transcript": "Caller: …\nAgent: …"
}
```

**Response:** `{ "ok": true, "call_id": "…" }`  
Upsert on `call_id` for idempotency.

**Express sketch:**

```javascript
router.post('/voice/call-ended', verifyVoiceSecret, async (req, res) => {
  const { call_id, caller, date, time, duration, duration_sec, topic,
          summary, next_step, outcome, turns, transcript } = req.body;
  if (!call_id) return res.status(400).json({ error: 'call_id is required' });
  await db.voiceCalls.upsert({ where: { callId: call_id }, create: { /* … */ }, update: { /* … */ } });
  res.json({ ok: true, call_id });
});
```

---

## Public APIs (web & Flutter)

Same JWT as WhatsApp inbox. Scope by `tenant_id` from session.

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/v1/voice/calls?page=1&limit=20` | List (no full transcript) |
| GET | `/api/v1/voice/calls/:call_id` | Detail + transcript |

List response fields: `call_id`, `caller`, `date`, `time`, `duration`, `topic`, `summary`, `next_step`, `outcome`.

---

## n8n → Node

After **Build Call Log**, add HTTP Request:

| Field | Value |
|-------|-------|
| POST | `https://resiliohub.com/api/internal/voice/call-ended` |
| Header | `x-voice-secret: {{ $env.VOICE_WEBHOOK_SECRET }}` |
| Body | Map `call_id`, `summary`, `transcript`, etc. from Build Call Log |

Keep existing Sheet + WhatsApp nodes.

---

## Security

| Rule | Detail |
|------|--------|
| Internal routes | `/api/internal/*` + secret header only |
| Public routes | JWT / session + `tenant_id` filter |
| Gemini key | Python server only |
| Idempotency | Upsert on `call_id` |

Generate secret: `openssl rand -hex 32`

---

## Web & Flutter UI (minimal)

**Voice → Calls:** list (date, caller, topic, summary, next step) → detail (transcript, WhatsApp link).

**Settings (Stage 2):** greeting, knowledge upload, enable toggle.

No telephony SDK in Flutter for inbound AI — Plivo handles PSTN.

---

## Testing checklist

- [ ] `curl https://resiliohub.com/health` → ok + `telephony: plivo`
- [ ] Internal webhook curl with secret → row in DB
- [ ] Real call → Sheet + WhatsApp + Node row
- [ ] `GET /voice/calls` without token → 401
- [ ] Pilot client: only their calls visible

---

# Part 3 — Rollout timeline (estimate)

| Phase | Scope | Time |
|-------|--------|------|
| **A** | Plivo production + voice on VPS + Node `voice_calls` + APIs | 2–3 weeks |
| **B** | Multi-tenant config loader + `tenant_id` + pilot clients (manual numbers) | 4–6 weeks |
| **C** | Self-serve Plivo buy + dashboard + billing | 3–4 weeks |
| **D** | Outbound, human transfer, usage metering | Ongoing |

---

## One-line summary

**Multi-tenant = one platform, many private AI phone lines (number + config + logs per client), shared Plivo/voice/Gemini backend — hardest parts are telecom compliance, tenant isolation, provisioning, billing, and uptime — not the demo AI itself.**

---

*Last updated: 2026-07-30*
