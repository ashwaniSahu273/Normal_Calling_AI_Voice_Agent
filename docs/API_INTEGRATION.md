# ResilioHub AI Calling — API Integration Spec

**For:** Node/Express backend + Web + Flutter  
**Answer:** Yes — implement as a ResilioHub feature. App never talks to Plivo or Gemini directly.

Related docs: [FLOW.md](FLOW.md) (call path) · [DEPLOY.md](DEPLOY.md) (nginx + Python next to Node) · [PRODUCT_MULTI_TENANT.md](PRODUCT_MULTI_TENANT.md) (KYC / reseller)

**Official Plivo APIs Node must wrap:** [Subaccount](https://www.plivo.com/docs/account/api/subaccount) · [Application](https://www.plivo.com/docs/account/api/application) · [Phone Numbers search/buy](https://www.plivo.com/docs/numbers/api/phone-number) · [Account Numbers update](https://www.plivo.com/docs/numbers/api/account-phone-number) · [Compliance (India KYC)](https://www.plivo.com/docs/numbers/compliance)

---

## Contents

1. [Who talks to whom](#1-who-talks-to-whom)
2. [Conventions](#2-conventions)
3. [App / Web APIs](#3-app--web-apis-node-must-build)
4. [Internal APIs](#4-internal-apis-voice--n8n--node)
5. [Node → Plivo REST (behind the scenes)](#5-node--plivo-rest-behind-the-scenes) ← **implement these**
6. [Voice bridge APIs](#6-voice-bridge-apis-already-live--node-calls-these)
7. [Suggested Node tables](#7-suggested-node-tables)
8. [Flutter / Web screens](#8-flutter--web-screens--apis)
9. [End-to-end sequences](#9-end-to-end-sequences)
10. [Env vars](#10-env-vars-node)
11. [Build order](#11-build-order-for-developers)
12. [Quick test](#12-quick-test-after-node-step-3)

---

## 1. Who talks to whom

```
Web / Flutter  ──JWT──►  ResilioHub Node (:3000)
                              │
                              │ wraps Plivo REST (subaccount, KYC, buy number)
                              │ stores tenant knowledge + call logs
                              │
                              ├──x-voice-secret──►  Voice Bridge Python (:5000)
                              │                      Plivo Stream + Gemini Live
                              │
                              ◄──x-voice-secret──  Voice / n8n webhooks (call ended, lead)
```

| Layer | Role | App calls it? |
|-------|------|----------------|
| **Node `/api/v1/voice/*`** | Feature APIs for web + Flutter | **Yes** |
| **Node `/api/internal/voice/*`** | Voice bridge / n8n / Plivo KYC webhook → save data | No (server only) |
| **Node → Plivo REST** | Subaccount, KYC, Application/Answer URL, buy number — **[§5](#5-node--plivo-rest-behind-the-scenes)** | No (Node only) |
| **Voice bridge `/plivo/*`** | Live calls + outbound dial | No (Node only) |

Flutter / web use **only** `/api/v1/voice/*` with the same auth as WhatsApp inbox.

---

## 2. Conventions

### Base URLs

| Env | Node | Voice bridge |
|-----|------|----------------|
| Local | `http://localhost:3000` | `http://localhost:5000` |
| Prod | `https://resiliohub.com` | same host, nginx → `:5000` for `/plivo/` |

### Auth

| Caller | Header |
|--------|--------|
| Web / Flutter | `Authorization: Bearer <jwt>` |
| Node → Voice bridge | `x-voice-secret: <VOICE_BRIDGE_SECRET>` |
| Voice / n8n → Node | `x-voice-secret: <VOICE_WEBHOOK_SECRET>` |

JWT must include `tenant_id` (or `account_id`). All `/api/v1/voice/*` filter by that tenant.

### Standard error

```json
{
  "ok": false,
  "error": "kyc_required",
  "message": "Upload GST and business registration before buying a number."
}
```

| HTTP | When |
|------|------|
| 400 | Bad body / validation |
| 401 | Missing / invalid JWT or secret |
| 403 | Feature not enabled / wallet empty |
| 404 | Call or number not found |
| 409 | Already exists (e.g. number already assigned) |
| 422 | KYC rejected / pending |
| 502 | Plivo / voice bridge downstream error |

### Phone numbers

Always **E.164**: `+919876543210`, `+912264233283`.

### Feature statuses (store on tenant)

| `status` | Meaning | App UI |
|----------|---------|--------|
| `disabled` | Feature off | Show “Enable AI Calling” |
| `kyc_draft` | Docs not submitted | Upload form |
| `kyc_pending` | Sent to Plivo | “Under review (15 min – 1 day)” |
| `kyc_rejected` | Plivo rejected | Show reason + resubmit |
| `kyc_approved` | Can buy number | Number picker |
| `active` | Number live, AI answering | Dashboard + calls |
| `suspended` | Unpaid / abuse | Contact support |

---

## 3. App / Web APIs (Node must build)

All under `/api/v1/voice`. JWT required.

### 3.1 Get feature status

**`GET /api/v1/voice/status`**

Response `200`:

```json
{
  "ok": true,
  "status": "kyc_pending",
  "enabled": true,
  "phone_number": null,
  "kyc": {
    "status": "pending",
    "rejection_reason": null,
    "submitted_at": "2026-08-10T10:12:00+05:30"
  },
  "settings": {
    "language": "en_hi",
    "greeting": null,
    "human_agent_number": null,
    "outbound_enabled": false,
    "transfer_enabled": false
  },
  "wallet": {
    "balance_inr": 0,
    "currency": "INR"
  }
}
```

When active:

```json
{
  "ok": true,
  "status": "active",
  "enabled": true,
  "phone_number": "+912264233283",
  "kyc": { "status": "approved", "rejection_reason": null, "submitted_at": "2026-08-01T09:00:00+05:30" },
  "settings": {
    "language": "en_hi",
    "greeting": "Hello, this is Priya from Acme.",
    "human_agent_number": "+919876543210",
    "outbound_enabled": true,
    "transfer_enabled": true
  },
  "wallet": { "balance_inr": 2500, "currency": "INR" }
}
```

---

### 3.2 Enable / disable feature

**`POST /api/v1/voice/enable`**

Body:

```json
{}
```

Response `200`:

```json
{
  "ok": true,
  "status": "kyc_draft",
  "message": "AI Calling enabled. Upload KYC documents next."
}
```

**Behind the scenes:** Node creates a Plivo **Subaccount** for this tenant (§5.1) if none exists yet. App does not see Plivo IDs.

**`POST /api/v1/voice/disable`**

Body:

```json
{}
```

Response `200`:

```json
{
  "ok": true,
  "status": "disabled",
  "message": "AI Calling turned off. Number stays assigned until released."
}
```

Disable = stop answering / outbound. Do **not** automatically unrent the Plivo number (avoid accidental loss).

---

### 3.3 KYC — upload business docs

**`POST /api/v1/voice/kyc`**  
`Content-Type: multipart/form-data`

| Field | Type | Required | Notes |
|-------|------|----------|--------|
| `business_name` | string | yes | Must match GST / COI exactly |
| `gstin` | string | no | If GST cert uploaded |
| `pan` | string | no | If PAN uploaded |
| `cin_or_udyam` | string | no | CIN or Udyam number |
| `registration_doc` | file | yes | COI (MCA) or Udyam PDF/JPG, max 5 MB |
| `tax_doc` | file | yes | GST or Business PAN PDF/JPG, max 5 MB |

Response `200`:

```json
{
  "ok": true,
  "status": "kyc_pending",
  "kyc": {
    "status": "pending",
    "plivo_compliance_id": "ca_xxxxxxxx",
    "submitted_at": "2026-08-10T11:00:00+05:30"
  }
}
```

Response `400` (missing file):

```json
{
  "ok": false,
  "error": "documents_required",
  "message": "Upload both registration certificate and tax document."
}
```

**`GET /api/v1/voice/kyc`**

Response `200`:

```json
{
  "ok": true,
  "status": "kyc_rejected",
  "kyc": {
    "status": "rejected",
    "rejection_reason": "Business name mismatch between GST and COI.",
    "submitted_at": "2026-08-10T11:00:00+05:30",
    "reviewed_at": "2026-08-10T11:40:00+05:30"
  }
}
```

Node should call Plivo Compliance API (Section 5.3) and/or receive Plivo `callback_url`, then update `kyc.status`. App only reads this endpoint.

---

### 3.4 Search available numbers

Only when `status` is `kyc_approved` or `active`.

**`GET /api/v1/voice/numbers/search?country=IN&type=local&region=Mumbai&limit=10`**

Query:

| Param | Example | Notes |
|-------|---------|--------|
| `country` | `IN` | ISO |
| `type` | `local` | `local` \| `mobile` \| `tollfree` |
| `region` | `Mumbai` | optional city / state |
| `limit` | `10` | max 20 |

Response `200`:

```json
{
  "ok": true,
  "numbers": [
    {
      "number": "+912264233283",
      "region": "Mumbai",
      "type": "local",
      "monthly_rental_inr": 399,
      "capabilities": ["voice"]
    }
  ]
}
```

Response `422` if KYC not approved:

```json
{
  "ok": false,
  "error": "kyc_required",
  "message": "KYC must be approved before choosing a number."
}
```

---

### 3.5 Buy / assign number

**`POST /api/v1/voice/numbers/buy`**

Body:

```json
{
  "number": "+912264233283"
}
```

Response `200`:

```json
{
  "ok": true,
  "status": "active",
  "phone_number": "+912264233283",
  "monthly_rental_inr": 399
}
```

Response `409`:

```json
{
  "ok": false,
  "error": "number_taken",
  "message": "This number is no longer available. Search again."
}
```

Node must run the **full provision chain** in [Section 5.6](#56-full-provision-chain-what-node-runs-on-numbersbuy): create/reuse XML Application (Answer URL) → Plivo buy with `app_id` + `subaccount` + `compliance_application_id` → save `phone_number` → set `status=active`.

**`DELETE /api/v1/voice/numbers`** (optional, admin / unpaid)

Response `200`: `{ "ok": true, "status": "kyc_approved", "phone_number": null }`

---

### 3.6 Voice settings (train AI per business)

This is how each business “trains” the AI: **save knowledge**, not fine-tune Gemini.

**`GET /api/v1/voice/settings`**

Response `200`:

```json
{
  "ok": true,
  "settings": {
    "business_name": "Acme Digital",
    "agent_name": "Priya",
    "language": "en_hi",
    "greeting": "Hello, this is Priya from Acme Digital. How can I help you today?",
    "outbound_greeting": "Hi, this is Priya from Acme Digital calling regarding your enquiry.",
    "human_agent_number": "+919876543210",
    "transfer_enabled": true,
    "outbound_enabled": true,
    "notify_whatsapp": "+919876543210",
    "knowledge_text": "We build websites, mobile apps, and CRM. Website starts at ₹25,000...",
    "website_url": "https://acme.example.com",
    "updated_at": "2026-08-10T12:00:00+05:30"
  }
}
```

**`PUT /api/v1/voice/settings`**

Body (all fields optional; send only what changed):

```json
{
  "business_name": "Acme Digital",
  "agent_name": "Priya",
  "language": "en_hi",
  "greeting": "Hello, this is Priya from Acme Digital. How can I help you today?",
  "outbound_greeting": "Hi, this is Priya from Acme Digital calling regarding your enquiry.",
  "human_agent_number": "+919876543210",
  "transfer_enabled": true,
  "outbound_enabled": true,
  "notify_whatsapp": "+919876543210",
  "knowledge_text": "We build websites, mobile apps, and CRM...",
  "website_url": "https://acme.example.com"
}
```

| Field | Values / rules |
|-------|----------------|
| `language` | `en` \| `hi` \| `en_hi` |
| `greeting` | inbound opening line, max 300 chars |
| `outbound_greeting` | outbound opening, max 300 chars |
| `human_agent_number` | E.164 or `null` |
| `knowledge_text` | max ~20,000 chars (FAQs, prices, services) |
| `website_url` | optional; Node may scrape later |

Response `200`: same shape as GET.

**`POST /api/v1/voice/knowledge/upload`**  
`Content-Type: multipart/form-data`

| Field | Type | Notes |
|-------|------|--------|
| `file` | pdf / txt / md | max 5 MB |

Response `200`:

```json
{
  "ok": true,
  "extracted_chars": 4200,
  "knowledge_preview": "We build websites..."
}
```

Node extracts text → appends/replaces `knowledge_text`. Voice bridge loads this per tenant on each call.

---

### 3.7 Call list

**`GET /api/v1/voice/calls?page=1&limit=20&direction=inbound`**

Query:

| Param | Default | Notes |
|-------|---------|--------|
| `page` | `1` | |
| `limit` | `20` | max 50 |
| `direction` | all | `inbound` \| `outbound` |
| `from` | — | `YYYY-MM-DD` |
| `to` | — | `YYYY-MM-DD` |

Response `200`:

```json
{
  "ok": true,
  "page": 1,
  "limit": 20,
  "total": 42,
  "calls": [
    {
      "call_id": "c4264e4a-e02c-4494-aacc-6a9ea48395da",
      "direction": "inbound",
      "caller": "+919876543210",
      "date": "2026-08-10",
      "time": "04:21 PM",
      "duration": "3 min 45 sec",
      "duration_sec": 225,
      "topic": "Website development",
      "summary": "Caller asked about website cost and timeline. Lead captured for follow-up.",
      "next_step": "Lead — call back",
      "outcome": "thanks",
      "lead_captured": true,
      "appointment_booked": false
    }
  ]
}
```

Do **not** include full transcript in the list.

---

### 3.8 Call detail

**`GET /api/v1/voice/calls/:call_id`**

Response `200`:

```json
{
  "ok": true,
  "call": {
    "call_id": "c4264e4a-e02c-4494-aacc-6a9ea48395da",
    "direction": "inbound",
    "caller": "+919876543210",
    "date": "2026-08-10",
    "time": "04:21 PM",
    "duration": "3 min 45 sec",
    "duration_sec": 225,
    "topic": "Website development",
    "summary": "Caller asked about website cost and timeline. Lead captured for follow-up.",
    "next_step": "Lead — call back",
    "outcome": "thanks",
    "lead_captured": true,
    "appointment_booked": false,
    "transcript_turns": 14,
    "transcript": "Caller: I want a website.\nAgent: Sure, what kind of website?\nCaller: Business website.\nAgent: Our packages start at ₹25,000..."
  }
}
```

Response `404`: `{ "ok": false, "error": "not_found", "message": "Call not found." }`

---

### 3.9 Start outbound call

Only if `outbound_enabled` and `status=active` and wallet > 0.

**`POST /api/v1/voice/outbound`**

Body:

```json
{
  "to": "+919876543210",
  "purpose": "Follow up on website enquiry from 8 Aug. Confirm if they want a quote."
}
```

| Field | Required | Notes |
|-------|----------|--------|
| `to` | yes | E.164 customer number |
| `purpose` | yes | what AI should discuss (follow-up only) |

Response `200`:

```json
{
  "ok": true,
  "call_id": null,
  "request_uuid": "04d5fe8b-3f5d-4e41-b49a-dd92ab673d9a",
  "to": "+919876543210",
  "direction": "outbound",
  "purpose": "Follow up on website enquiry from 8 Aug. Confirm if they want a quote."
}
```

`call_id` is filled later when Plivo starts the stream; list API will show the call after hangup (or via live webhook).

Response `403`:

```json
{
  "ok": false,
  "error": "wallet_empty",
  "message": "Add credits before making outbound calls."
}
```

**Node implementation:** validate tenant → `POST` voice bridge `/plivo/outbound` with `x-voice-secret` (see §5). Do not expose bridge URL to the app.

---

### 3.10 Mid-call actions (leads / bookings) — read only for app

AI creates these during the call. App only lists them.

**`GET /api/v1/voice/actions?page=1&limit=20`**

Response `200`:

```json
{
  "ok": true,
  "page": 1,
  "limit": 20,
  "total": 8,
  "actions": [
    {
      "id": 101,
      "call_id": "c4264e4a-e02c-4494-aacc-6a9ea48395da",
      "action": "create_lead",
      "caller": "+919876543210",
      "details": {
        "name": "Ravi",
        "interest": "Website development",
        "notes": "Budget around 30k"
      },
      "status": "captured",
      "created_at": "2026-08-10T16:22:00+05:30"
    }
  ]
}
```

`action` values: `create_lead` | `book_appointment` | `send_notification` | `human_callback` | `transfer_to_human`.

When the caller asks for a real person, the bridge does **not** live-connect (saves Plivo minutes). It: missed-call pings the agent, sends WhatsApp “CALL BACK NOW” + customer number, hangs up the AI call. Agent calls the customer back on their own phone.

---

### 3.11 Usage / wallet (minimal)

**`GET /api/v1/voice/usage?month=2026-08`**

Response `200`:

```json
{
  "ok": true,
  "month": "2026-08",
  "minutes_in": 42,
  "minutes_out": 18,
  "calls": 27,
  "estimated_cost_inr": 240,
  "wallet_balance_inr": 2260
}
```

**`POST /api/v1/voice/wallet/topup`** — only if you already have payment in ResilioHub; reuse existing payment API, then credit `voice_wallet`.

---

## 4. Internal APIs (Voice / n8n → Node)

Secret header: `x-voice-secret: <VOICE_WEBHOOK_SECRET>`  
No JWT. Never expose to Flutter.

### 4.1 Tenant config lookup (Voice → Node)

Called at **start of every call** so AI loads that business’s knowledge.

Python already calls this when `BACKEND_URL` + `BACKEND_SECRET` are set (`backend.py`).

**`GET /api/internal/voice/tenant-config?number=+912264233283`**

or

**`GET /api/internal/voice/tenant-config?tenant_id=101`**

Response `200`:

```json
{
  "ok": true,
  "tenant_id": 101,
  "status": "active",
  "phone_number": "+912264233283",
  "business_name": "Acme Digital",
  "agent_name": "Priya",
  "language": "en_hi",
  "greeting": "Hello, this is Priya from Acme Digital. How can I help you today?",
  "outbound_greeting": "Hi, this is Priya from Acme Digital calling regarding your enquiry.",
  "human_agent_number": "+919876543210",
  "transfer_enabled": true,
  "knowledge_text": "We build websites...",
  "notify_whatsapp": "+919876543210"
}
```

Response `404`: `{ "ok": false, "error": "unknown_number" }`  
Response `403`: `{ "ok": false, "error": "tenant_disabled" }`

### 4.2 Call ended (Voice / n8n → Node)

**`POST /api/internal/voice/call-ended`**

Body:

```json
{
  "tenant_id": 101,
  "call_id": "c4264e4a-e02c-4494-aacc-6a9ea48395da",
  "direction": "inbound",
  "caller": "+919876543210",
  "date": "2026-08-10",
  "time": "04:21 PM",
  "duration": "3 min 45 sec",
  "duration_sec": 225,
  "topic": "Website development",
  "summary": "Caller asked about website cost and timeline. Lead captured for follow-up.",
  "next_step": "Lead — call back",
  "outcome": "thanks",
  "lead_captured": true,
  "appointment_booked": false,
  "transcript_turns": 14,
  "transcript": "Caller: I want a website.\nAgent: Sure..."
}
```

Response `200`:

```json
{ "ok": true, "call_id": "c4264e4a-e02c-4494-aacc-6a9ea48395da" }
```

Upsert on `call_id` (idempotent). Deduct wallet minutes using `duration_sec`.

### 4.3 Mid-call action (Voice / n8n → Node)

**`POST /api/internal/voice/action`**

Body:

```json
{
  "tenant_id": 101,
  "call_id": "c4264e4a-e02c-4494-aacc-6a9ea48395da",
  "caller": "+919876543210",
  "action": "create_lead",
  "details": {
    "name": "Ravi",
    "phone": "+919876543210",
    "interest": "Website development",
    "notes": "Budget around 30k"
  }
}
```

`book_appointment` details:

```json
{
  "name": "Ravi",
  "date": "2026-08-15",
  "time": "11:00 AM",
  "service": "Website consultation"
}
```

Response `200`:

```json
{
  "ok": true,
  "action_id": 101,
  "status": "captured",
  "message": "Lead captured. The team will follow up shortly."
}
```

This JSON `message` can be spoken by the AI (keep it short).

---

## 5. Node → Plivo REST (behind the scenes)

App never calls Plivo. **Node** calls these with your **main** Plivo credentials (`PLIVO_AUTH_ID` / `PLIVO_AUTH_TOKEN`).

Base URL: `https://api.plivo.com/v1/Account/{MA_AUTH_ID}/`  
Auth: HTTP Basic — username = Auth ID, password = Auth Token  
SDK (optional): `npm i plivo`

### 5.0 Provisioning map (client enable → live number)

```
POST /api/v1/voice/enable
  └─ Plivo: Create Subaccount                          §5.1

POST /api/v1/voice/kyc  (multipart docs)
  ├─ Plivo: GET  Compliance Requirements               §5.3.1
  └─ Plivo: POST Compliance (submit KYC)               §5.3.2
       └─ Plivo callback → Node updates kyc_status     §5.3.4

GET  /api/v1/voice/numbers/search
  └─ Plivo: GET  PhoneNumber/?country_iso=…            §5.4

POST /api/v1/voice/numbers/buy
  ├─ Plivo: POST Application/  (Answer URL)            §5.2   ← once per tenant
  ├─ Plivo: POST PhoneNumber/{number}/  (buy)          §5.5.1
  └─ (optional) POST Number/{number}/  (re-attach app) §5.5.2
```

| ResilioHub app API | Plivo API Node must call | Purpose |
|--------------------|--------------------------|---------|
| `POST /enable` | Create Subaccount | Isolate client (`SA…`) |
| `POST /kyc` | Requirements + Create Compliance | India KYC per client |
| `GET /kyc` | Get Compliance (poll) | Sync accepted/rejected |
| `GET /numbers/search` | Search PhoneNumber | List buyable DIDs |
| `POST /numbers/buy` | Create Application + Buy Number | Answer URL + rent number |
| `DELETE /numbers` | Unrent Number (optional) | Release DID |

---

### 5.1 Create / manage Subaccount (per client)

Docs: [Subaccount API](https://www.plivo.com/docs/account/api/subaccount)

**When:** `POST /api/v1/voice/enable` (first time only).

#### Create

```http
POST https://api.plivo.com/v1/Account/{MA_AUTH_ID}/Subaccount/
Authorization: Basic {base64(MA_AUTH_ID:MA_AUTH_TOKEN)}
Content-Type: application/json

{
  "name": "tenant-101-acme-digital",
  "enabled": true
}
```

Response `201`:

```json
{
  "api_id": "...",
  "auth_id": "SAXXXXXXXXXXXXXXXXX",
  "auth_token": "xxxxxxxxxxxxxxxx",
  "message": "created"
}
```

**Node must store** on `voice_tenants`:

| Column | Value |
|--------|--------|
| `plivo_subaccount_id` | `auth_id` (`SA…`) |
| `plivo_auth_token_enc` | encrypt `auth_token` (never send to app) |

#### Retrieve / list / disable

```http
GET    /v1/Account/{MA}/Subaccount/{SA}/
GET    /v1/Account/{MA}/Subaccount/
POST   /v1/Account/{MA}/Subaccount/{SA}/   {"name":"...","enabled":false}
DELETE /v1/Account/{MA}/Subaccount/{SA}/?cascade=true
```

Use `enabled:false` when client disables feature (keep number unless unpaid).

---

### 5.2 Create XML Application + Answer URL (per client)

Docs: [Application API](https://www.plivo.com/docs/account/api/application)

This is how **each separate account** gets wired to your voice bridge. Plivo does **not** invent the Answer URL — Node creates an Application that points at your public bridge.

#### Recommended pattern (per-tenant Application)

One Application **per subaccount**, Answer URL includes `tenant_id` so bridge/Node can resolve config fast:

```text
https://VOICE_PUBLIC_HOST/plivo/answer?tenant_id=101
```

Still resolve primarily by dialed number (`To`) via `GET /api/internal/voice/tenant-config?number=…` — `tenant_id` query is a backup / faster path.

**Alternative (simpler, shared app):** one Application on main account:

```text
https://VOICE_PUBLIC_HOST/plivo/answer
```

Then every number uses the same `app_id`; Node maps `To` → tenant. Fine for early SaaS; per-tenant app is better for isolation + hangup logs.

#### Create Application

```http
POST https://api.plivo.com/v1/Account/{MA_AUTH_ID}/Application/
Content-Type: application/json

{
  "app_name": "resiliohub-tenant-101",
  "answer_url": "https://resiliohub.com/plivo/answer?tenant_id=101",
  "answer_method": "POST",
  "hangup_url": "https://resiliohub.com/plivo/hangup?tenant_id=101",
  "hangup_method": "POST",
  "fallback_answer_url": "https://resiliohub.com/plivo/answer?tenant_id=101",
  "fallback_method": "POST",
  "subaccount": "SAXXXXXXXXXXXXXXXXX"
}
```

| Field | Value for ResilioHub |
|-------|----------------------|
| `app_name` | Unique, e.g. `resiliohub-tenant-{id}` (alphanumeric, `-`, `_`) |
| `answer_url` | `https://{VOICE_PUBLIC_HOST}/plivo/answer?tenant_id={id}` |
| `answer_method` | `POST` (matches bridge) |
| `subaccount` | Client’s `SA…` from §5.1 |
| `hangup_url` | Optional; can omit (defaults to answer_url) |

Response:

```json
{
  "message": "created",
  "app_id": "15784735442685051",
  "api_id": "..."
}
```

**Store** `plivo_app_id` on `voice_tenants`.

#### Update Answer URL (host / tunnel change)

```http
POST https://api.plivo.com/v1/Account/{MA}/Application/{app_id}/

{
  "answer_url": "https://NEW_HOST/plivo/answer?tenant_id=101",
  "answer_method": "POST"
}
```

#### Node helper (create once per tenant)

```javascript
async function ensurePlivoApplication(tenant) {
  if (tenant.plivo_app_id) return tenant.plivo_app_id;

  const answerUrl =
    `${process.env.VOICE_PUBLIC_HOST}/plivo/answer?tenant_id=${tenant.tenant_id}`;

  const res = await plivoFetch('POST', `/Application/`, {
    app_name: `resiliohub-tenant-${tenant.tenant_id}`,
    answer_url: answerUrl,
    answer_method: 'POST',
    subaccount: tenant.plivo_subaccount_id,
  });

  await db.voice_tenants.update(tenant.tenant_id, {
    plivo_app_id: res.app_id,
    plivo_answer_url: answerUrl,
  });
  return res.app_id;
}
```

`VOICE_PUBLIC_HOST` must be HTTPS reachable by Plivo (same host as voice bridge nginx `/plivo/`).

---

### 5.3 India KYC — Compliance API

Docs: [Compliance API](https://www.plivo.com/docs/numbers/compliance) · [India number KYC](https://www.plivo.com/docs/numbers/rent-india-numbers)

**Supported today:** India only. Account must be India data region. Reseller = **one compliance application per client business**.

Auth: **main account** credentials.

#### 5.3.1 Get document requirements (always first)

```http
GET https://api.plivo.com/v1/Account/{MA}/PhoneNumber/Compliance/Requirements?country_iso=IN&number_type=local&user_type=business
```

Response includes `requirement_id` and `document_types[]` with `document_type_id` + `required_fields`. Use those IDs when submitting — **do not hardcode** UUIDs from examples.

Typical India business docs: Registration Certificate (COI/Udyam) + GST or Business PAN.

#### 5.3.2 Create + submit compliance (from `POST /api/v1/voice/kyc`)

```http
POST https://api.plivo.com/v1/Account/{MA}/PhoneNumber/Compliance/
Content-Type: multipart/form-data
```

Parts:

1. `data` — JSON string  
2. `documents[0].file`, `documents[1].file` — PDF/JPEG/PNG, max 5 MB each  

Example `data` JSON:

```json
{
  "country_iso": "IN",
  "number_type": "local",
  "alias": "tenant-101-acme-compliance",
  "end_user": {
    "type": "business",
    "name": "ACME TECHNOLOGIES PRIVATE LIMITED",
    "email": "owner@acme.in",
    "address_line1": "123 MG Road",
    "city": "Mumbai",
    "state": "Maharashtra",
    "postal_code": "400001",
    "country": "IN",
    "registration_number": "U72200MH2020PTC123456"
  },
  "documents": [
    {
      "document_type_id": "<from Requirements — Registration Certificate>",
      "data_fields": {
        "business_name": "ACME TECHNOLOGIES PRIVATE LIMITED"
      }
    },
    {
      "document_type_id": "<from Requirements — GST Certificate>"
    }
  ],
  "callback_url": "https://resiliohub.com/api/internal/voice/plivo-compliance",
  "callback_method": "POST"
}
```

Response `201`:

```json
{
  "api_id": "...",
  "compliance_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Compliance application created and submitted for review."
}
```

**Node store:** `compliance_id`, `kyc_status=pending`, feature `status=kyc_pending`.

Confirm with Plivo sales that your master account is flagged **Reseller** so per-customer compliance is allowed.

#### 5.3.3 Poll status

```http
GET https://api.plivo.com/v1/Account/{MA}/PhoneNumber/Compliance/{compliance_id}?expand=end_user,documents
```

| Plivo `status` | Node `kyc_status` | Feature `status` |
|----------------|-------------------|------------------|
| `submitted` / `draft` | `pending` | `kyc_pending` |
| `accepted` | `approved` | `kyc_approved` |
| `rejected` | `rejected` (+ `rejection_reason`) | `kyc_rejected` |
| `suspended` / `expired` | map to suspended / re-KYC | `suspended` |

Cron: poll every 5–15 min while `kyc_pending`. Prefer webhook (§5.3.4).

#### 5.3.4 Compliance webhook (Node must expose)

Plivo POSTs to `callback_url` when status changes. Verify [Plivo signature v3](https://www.plivo.com/docs/voice/concepts/signature-validation).

**`POST /api/internal/voice/plivo-compliance`**

```javascript
// pseudo
router.post('/plivo-compliance', verifyPlivoSignature, async (req, res) => {
  const { compliance_id, status, rejection_reason } = req.body; // shape may vary — log raw once
  const tenant = await db.findByComplianceId(compliance_id);
  if (!tenant) return res.sendStatus(404);

  if (status === 'accepted') {
    await db.update(tenant.id, { kyc_status: 'approved', status: 'kyc_approved' });
  } else if (status === 'rejected') {
    await db.update(tenant.id, {
      kyc_status: 'rejected',
      status: 'kyc_rejected',
      kyc_rejection: rejection_reason || null,
    });
  }
  res.sendStatus(200);
});
```

---

### 5.4 Search available numbers

Docs: [Phone Numbers API](https://www.plivo.com/docs/numbers/api/phone-number)

**When:** `GET /api/v1/voice/numbers/search` (only if `kyc_approved` or `active`).

```http
GET https://api.plivo.com/v1/Account/{MA}/PhoneNumber/?country_iso=IN&type=local&services=voice&city=Mumbai&limit=10
```

| Query | Notes |
|-------|--------|
| `country_iso` | required (`IN`) |
| `type` | `local` \| `mobile` \| `tollfree` \| `national` \| `fixed` |
| `city` / `region` / `pattern` | optional filters |
| `services` | use `voice` |
| `limit` | max 20 |

Response `objects[]` → map to app:

```json
{
  "number": "+912264233283",
  "region": "Mumbai",
  "type": "local",
  "monthly_rental_inr": 399,
  "capabilities": ["voice"]
}
```

Convert Plivo `number` (digits) → E.164 for the app. Convert USD `monthly_rental_rate` to INR using your price list / markup (do not expose raw Plivo cost if you bill differently).

---

### 5.5 Buy number + attach Application (Answer URL)

#### 5.5.1 Buy

```http
POST https://api.plivo.com/v1/Account/{MA_AUTH_ID}/PhoneNumber/{number}/
Content-Type: application/json

{
  "app_id": "15784735442685051",
  "subaccount": "SAXXXXXXXXXXXXXXXXX",
  "compliance_application_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

| Param | Required | Notes |
|-------|----------|--------|
| `app_id` | yes (for AI) | From §5.2 — wires Answer URL |
| `subaccount` | yes | Client `SA…` |
| `compliance_application_id` | yes (India) | Must be status `accepted`; country/type must match number |

**Critical:** call with **main** account auth. Buying with **subaccount** credentials often returns **404**.

`{number}` in path = digits without `+` (e.g. `912264233283`).

Response:

```json
{
  "api_id": "...",
  "message": "created",
  "numbers": [{ "number": "912264233283", "status": "Success" }],
  "status": "fulfilled"
}
```

If verification still pending, number status may be `pending` until compliance link completes.

#### 5.5.2 Update number (re-attach app / move subaccount)

Docs: [Account Phone Numbers](https://www.plivo.com/docs/numbers/api/account-phone-number)

```http
POST https://api.plivo.com/v1/Account/{MA}/Number/{number}/

{
  "app_id": "15784735442685051",
  "subaccount": "SAXXXXXXXXXXXXXXXXX",
  "alias": "Acme Digital AI"
}
```

Use if buy succeeded but app not linked, or Answer URL app changed.

#### 5.5.3 Unrent

```http
DELETE https://api.plivo.com/v1/Account/{MA}/Number/{number}/
```

→ `204`. Irreversible. Map to `DELETE /api/v1/voice/numbers`.

---

### 5.6 Full provision chain (what Node runs on `numbers/buy`)

```javascript
async function buyNumberForTenant(tenant, e164Number) {
  if (tenant.kyc_status !== 'approved') {
    throw Object.assign(new Error('kyc_required'), { status: 422 });
  }

  // 1) Ensure XML Application exists (Answer URL → voice bridge)
  const appId = await ensurePlivoApplication(tenant);

  // 2) Buy with main credentials
  const digits = e164Number.replace(/\D/g, '');
  const buy = await plivoFetch('POST', `/PhoneNumber/${digits}/`, {
    app_id: appId,
    subaccount: tenant.plivo_subaccount_id,
    compliance_application_id: tenant.compliance_id,
  });

  // 3) Persist
  await db.voice_tenants.update(tenant.tenant_id, {
    phone_number: e164Number,
    status: 'active',
    plivo_app_id: appId,
  });

  return { phone_number: e164Number, plivo: buy };
}
```

After this, inbound call flow:

```
Caller → Plivo number
  → Plivo fetches Application.answer_url
  → GET/POST https://VOICE_HOST/plivo/answer?tenant_id=101
  → Voice bridge returns Stream XML
  → Bridge asks Node GET /api/internal/voice/tenant-config?number=+91…
  → Gemini uses that tenant’s knowledge
```

---

### 5.7 Shared Answer URL design (important)

| Approach | Answer URL | Pros | Cons |
|----------|------------|------|------|
| **A. Per-tenant Application** (recommended) | `/plivo/answer?tenant_id=N` under each `SA` | Clear isolation; easy debug | One Plivo app per client |
| **B. One shared Application** | `/plivo/answer` on main | Fewer Plivo objects | Must always map `To` → tenant |

Voice bridge already accepts Plivo’s `To` / `From` on answer — Node `tenant-config?number=` works for **both**. Prefer A for product; B is OK for first 1–2 pilot clients.

Do **not** create a separate cloudflared URL per client. One public voice host; many Applications can point at the same host with different query strings.

---

### 5.8 Minimal `plivoFetch` helper (Node)

```javascript
const PLIVO_BASE = () =>
  `https://api.plivo.com/v1/Account/${process.env.PLIVO_AUTH_ID}`;

async function plivoFetch(method, path, body) {
  const auth = Buffer.from(
    `${process.env.PLIVO_AUTH_ID}:${process.env.PLIVO_AUTH_TOKEN}`
  ).toString('base64');

  const res = await fetch(`${PLIVO_BASE()}${path}`, {
    method,
    headers: {
      Authorization: `Basic ${auth}`,
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || data.message || `plivo_${res.status}`);
    err.status = 502;
    err.plivo = data;
    throw err;
  }
  return data;
}
```

For Compliance create, use `multipart/form-data` (`form-data` / `undici` FormData), not JSON.

---

### 5.9 Official Plivo doc links (bookmark for Node)

| Topic | URL |
|-------|-----|
| Subaccount | https://www.plivo.com/docs/account/api/subaccount |
| Application (Answer URL) | https://www.plivo.com/docs/account/api/application |
| Search / buy numbers | https://www.plivo.com/docs/numbers/api/phone-number |
| Update / unrent numbers | https://www.plivo.com/docs/numbers/api/account-phone-number |
| Compliance (KYC) | https://www.plivo.com/docs/numbers/compliance |
| India KYC rules | https://www.plivo.com/docs/numbers/rent-india-numbers |
| Signature validation | https://www.plivo.com/docs/voice/concepts/signature-validation |

---

## 6. Voice bridge APIs (already live — Node calls these)

Base: `http://127.0.0.1:5000` (prod via nginx `/plivo/` or internal host).  
App **must not** call these.

### 6.1 Health

**`GET /health`**

Response:

```json
{
  "status": "ok",
  "ai": "gemini",
  "telephony": "plivo",
  "agent_first": false,
  "human_transfer": true
}
```

### 6.2 Start outbound call

**`POST /plivo/outbound`**  
Headers: `Content-Type: application/json`, `x-voice-secret: <OUTBOUND_API_SECRET>`

Body:

```json
{
  "to": "+919876543210",
  "purpose": "Follow up on website enquiry. Confirm if they want a quote."
}
```

Response `200`:

```json
{
  "ok": true,
  "to": "+919876543210",
  "direction": "outbound",
  "purpose": "Follow up on website enquiry. Confirm if they want a quote.",
  "request_uuid": "04d5fe8b-3f5d-4e41-b49a-dd92ab673d9a",
  "message_uuid": null
}
```

Response `401`: `{ "error": "Unauthorized" }`  
Response `400`: `{ "error": "to is required (E.164)", "hint": "..." }`

Node Express example:

```javascript
router.post('/voice/outbound', authTenant, async (req, res) => {
  const { to, purpose } = req.body;
  if (!to || !purpose) {
    return res.status(400).json({ ok: false, error: 'to_and_purpose_required' });
  }
  const r = await fetch(`${process.env.VOICE_BRIDGE_URL}/plivo/outbound`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-voice-secret': process.env.VOICE_BRIDGE_SECRET,
    },
    body: JSON.stringify({ to, purpose }),
  });
  const data = await r.json();
  if (!r.ok) return res.status(r.status).json({ ok: false, error: data.error || 'bridge_error' });
  res.json({ ok: true, request_uuid: data.request_uuid, to: data.to, direction: 'outbound', purpose });
});
```

### 6.3 Plivo-only (do not call from Node or app)

These are hit by **Plivo**, not by ResilioHub:

| Method | Path | Who |
|--------|------|-----|
| GET/POST | `/plivo/answer` | Plivo inbound / outbound answer URL |
| WS | `/plivo/stream` | Plivo audio stream |
| POST | `/plivo/stream-status` | Plivo stream events |
| GET/POST | `/plivo/transfer` | Mid-call human transfer XML |
| GET/POST | `/plivo/dial-status` | Agent-first fallback |

---

## 7. Suggested Node tables

```sql
CREATE TABLE voice_tenants (
  tenant_id            BIGINT PRIMARY KEY,
  status               VARCHAR(32) NOT NULL DEFAULT 'disabled',
  enabled              BOOLEAN NOT NULL DEFAULT FALSE,
  plivo_subaccount_id  VARCHAR(64),
  plivo_auth_token_enc TEXT,
  plivo_app_id         VARCHAR(64),
  plivo_answer_url     TEXT,
  compliance_id        VARCHAR(128),
  kyc_status           VARCHAR(32),
  kyc_rejection        TEXT,
  phone_number         VARCHAR(20),
  business_name        VARCHAR(255),
  agent_name           VARCHAR(64),
  language             VARCHAR(16) DEFAULT 'en_hi',
  greeting             TEXT,
  outbound_greeting    TEXT,
  human_agent_number   VARCHAR(20),
  transfer_enabled     BOOLEAN DEFAULT FALSE,
  outbound_enabled     BOOLEAN DEFAULT FALSE,
  notify_whatsapp      VARCHAR(20),
  knowledge_text       TEXT,
  website_url          TEXT,
  wallet_balance_inr   INTEGER NOT NULL DEFAULT 0,
  created_at           TIMESTAMPTZ DEFAULT NOW(),
  updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE voice_calls (
  id                 BIGSERIAL PRIMARY KEY,
  tenant_id          BIGINT NOT NULL,
  call_id            VARCHAR(64) NOT NULL UNIQUE,
  direction          VARCHAR(16) DEFAULT 'inbound',
  caller             VARCHAR(20),
  date               DATE,
  time               VARCHAR(16),
  duration           VARCHAR(32),
  duration_sec       INTEGER NOT NULL DEFAULT 0,
  topic              VARCHAR(128),
  summary            TEXT,
  next_step          VARCHAR(64),
  outcome            VARCHAR(128),
  transcript         TEXT,
  transcript_turns   INTEGER DEFAULT 0,
  appointment_booked BOOLEAN DEFAULT FALSE,
  lead_captured      BOOLEAN DEFAULT FALSE,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE voice_actions (
  id          BIGSERIAL PRIMARY KEY,
  tenant_id   BIGINT NOT NULL,
  call_id     VARCHAR(64),
  caller      VARCHAR(20),
  action      VARCHAR(64) NOT NULL,
  details     JSONB,
  status      VARCHAR(32) DEFAULT 'captured',
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_voice_calls_tenant ON voice_calls (tenant_id, created_at DESC);
CREATE INDEX idx_voice_actions_tenant ON voice_actions (tenant_id, created_at DESC);
```

Encrypt `plivo_auth_token_enc`. Never send it to the app.  
`plivo_app_id` + `plivo_answer_url` come from Section 5.2 (XML Application).

---

## 8. Flutter / Web screens → APIs

| Screen | APIs |
|--------|------|
| AI Calling home | `GET /status` |
| Enable toggle | `POST /enable` · `POST /disable` |
| KYC upload | `POST /kyc` · `GET /kyc` |
| Pick number | `GET /numbers/search` · `POST /numbers/buy` |
| Agent settings | `GET /settings` · `PUT /settings` · `POST /knowledge/upload` |
| Call inbox | `GET /calls` |
| Call detail | `GET /calls/:call_id` |
| Leads / bookings | `GET /actions` |
| Click-to-call (outbound) | `POST /outbound` |
| Usage | `GET /usage` |

No telephony SDK in Flutter for inbound AI. Customer dials the **assigned Plivo number**.

---

## 9. End-to-end sequences

### Enable → first live number

```
App  POST /api/v1/voice/enable
Node → Plivo POST /Subaccount/                         (§5.1)
     store SA… + encrypted token

App  POST /api/v1/voice/kyc  (GST + COI files)
Node → Plivo GET  /PhoneNumber/Compliance/Requirements (§5.3.1)
Node → Plivo POST /PhoneNumber/Compliance/ multipart   (§5.3.2)
     store compliance_id, status=kyc_pending

Plivo review → POST /api/internal/voice/plivo-compliance  (§5.3.4)
     or Node polls GET /Compliance/{id}
     status=kyc_approved

App  GET  /api/v1/voice/numbers/search
Node → Plivo GET  /PhoneNumber/?country_iso=IN…        (§5.4)

App  POST /api/v1/voice/numbers/buy  { "number": "+91…" }
Node → Plivo POST /Application/  (Answer URL)          (§5.2)
Node → Plivo POST /PhoneNumber/{digits}/               (§5.5)
       body: app_id + subaccount + compliance_application_id
     status=active, phone_number saved

Inbound call → Plivo → Answer URL → Voice bridge
Voice → GET /api/internal/voice/tenant-config?number=+91…
Call ends → POST /api/internal/voice/call-ended → App GET /calls
```

### Outbound from CRM lead

```
App  POST /outbound  { to, purpose }
Node checks wallet + outbound_enabled
Node POST voice-bridge /plivo/outbound
Phone rings → AI speaks outbound greeting + purpose
Hangup → POST /internal/call-ended
```

---

## 10. Env vars (Node)

```env
VOICE_BRIDGE_URL=http://127.0.0.1:5000
VOICE_BRIDGE_SECRET=<same as voice-agent OUTBOUND_API_SECRET>
VOICE_WEBHOOK_SECRET=<new random hex>
VOICE_PUBLIC_HOST=https://resiliohub.com

# Plivo master account (Node only — never in Flutter)
PLIVO_AUTH_ID=MA...
PLIVO_AUTH_TOKEN=...
```

| Var | Used for |
|-----|----------|
| `VOICE_PUBLIC_HOST` | Building per-tenant `answer_url` in §5.2 |
| `PLIVO_AUTH_ID` / `TOKEN` | All §5 Plivo REST calls |
| `VOICE_BRIDGE_*` | Outbound dial via Python bridge |
| `VOICE_WEBHOOK_SECRET` | Must match Python `BACKEND_SECRET` |

Voice bridge: `OUTBOUND_API_SECRET` = Node `VOICE_BRIDGE_SECRET`.  
Voice bridge: `BACKEND_SECRET` = Node `VOICE_WEBHOOK_SECRET`.

---

## 11. Build order for developers

| Step | Owner | What |
|------|--------|------|
| 1 | Node | tables + JWT scope `tenant_id` (+ `plivo_app_id`, `compliance_id`) |
| 2 | Node | `GET /status`, `POST /enable` → **Plivo Subaccount** (§5.1) |
| 3 | Node | `POST /internal/call-ended`, `GET /calls`, `GET /calls/:id` |
| 4 | Web/Flutter | Call inbox + settings screens |
| 5 | Node | `POST /kyc` → **Compliance Requirements + submit** (§5.3) + webhook |
| 6 | Node | `numbers/search` → **Plivo PhoneNumber search** (§5.4) |
| 7 | Node | `numbers/buy` → **Application + Buy** (§5.2 + §5.5) |
| 8 | Voice bridge | load `tenant-config` per called number (multi-tenant) |
| 9 | Node + App | `POST /outbound` + wallet |
| 10 | Node | `POST /internal/action` + `GET /actions` |

Steps 1–4 work **today** with the existing single Plivo number (your business). Steps 5–7 = real multi-tenant Plivo wiring.

---

## 12. Quick test (after Node Step 3)

```bash
# health
curl https://resiliohub.com/health

# save a fake call
curl -X POST https://resiliohub.com/api/internal/voice/call-ended \
  -H "Content-Type: application/json" \
  -H "x-voice-secret: $VOICE_WEBHOOK_SECRET" \
  -d '{"tenant_id":1,"call_id":"test-1","caller":"+919876543210","direction":"inbound","date":"2026-08-10","time":"04:21 PM","duration":"1 min","duration_sec":60,"topic":"Test","summary":"Test call.","next_step":"None","outcome":"thanks","transcript_turns":2,"transcript":"Caller: hi\nAgent: hello"}'

# list as logged-in user
curl https://resiliohub.com/api/v1/voice/calls \
  -H "Authorization: Bearer $JWT"
```

### Plivo smoke tests (Node Step 5–7)

```bash
# search IN local voice numbers (main auth)
curl -u "$PLIVO_AUTH_ID:$PLIVO_AUTH_TOKEN" \
  "https://api.plivo.com/v1/Account/$PLIVO_AUTH_ID/PhoneNumber/?country_iso=IN&type=local&services=voice&limit=5"

# list applications
curl -u "$PLIVO_AUTH_ID:$PLIVO_AUTH_TOKEN" \
  "https://api.plivo.com/v1/Account/$PLIVO_AUTH_ID/Application/"
```

---

**Summary for the team:** App uses only `/api/v1/voice/*`. Node owns tenants + **wraps Plivo** (Subaccount, Compliance/KYC, Application/Answer URL, search/buy number). Python voice bridge owns live audio. Same JWT as the rest of ResilioHub. Per-business “training” = `knowledge_text` + settings, loaded on each call via `/api/internal/voice/tenant-config`. Full Plivo request bodies: **Section 5**.
