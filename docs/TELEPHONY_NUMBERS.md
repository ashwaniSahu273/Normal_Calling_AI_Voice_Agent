# Telephony numbers — quick reference (Exotel & Plivo)

Step-by-step checklist for **production numbers**, **inbound**, and **outbound**, with official doc links.  
This repo implements the **WebSocket voice bridge**; number purchase and call APIs are configured in **Exotel / Plivo** dashboards and their REST APIs.

---

## Terms (30-second read)

| Term | Meaning |
|------|---------|
| **ExoPhone** (Exotel) | Virtual business number (DID) on your Exotel account — inbound + outbound caller ID |
| **Plivo number** | Rented DID from Plivo inventory (or **ported** onto Plivo) |
| **Trial / demo number** | Account trial product (e.g. PIN prompts) — not the same as a purchased ExoPhone / rented Plivo number |
| **Your existing SIM/landline** | Customers dial it only after **porting** to the CPaaS or using provider-specific **verified caller ID** (Plivo: not for India outbound) |

---

## This project — endpoints (after number is live)

| Provider | `.env` | Inbound (caller → AI) | Outbound (not coded yet — use provider API below) |
|----------|--------|------------------------|-----------------------------------------------------|
| **Exotel** | `TELEPHONY_PROVIDER=exotel` | ExoPhone → flow **Voicebot** → `wss://<PUBLIC_HOST>/exotel/stream?sample-rate=8000` or `https://<PUBLIC_HOST>/exotel/ws-url` | Exotel **Connect** API → same flow URL (Voicebot) |
| **Plivo** | `TELEPHONY_PROVIDER=plivo` | Number → Voice app **Answer URL** → `https://<PUBLIC_HOST>/plivo/answer` → `/plivo/stream` | Plivo **Call API** → `answer_url` returns Stream XML |

**Before testing:** tunnel running, `PUBLIC_HOST` in `.env`, `python app.py`, health: `https://<PUBLIC_HOST>/health`.

---

## Exotel — production number + inbound + outbound

Official hub: [Exotel Developer Docs](https://developer.exotel.com/)

### A. Get a real ExoPhone (not trial)

| Step | Action | Doc |
|------|--------|-----|
| 1 | Log in → **ExoPhones** → **Buy New Number** (region, local/toll-free/mobile) | [ExoPhone setup](https://developer.exotel.com/docs/getting-started/exophone-setup) |
| 2 | Complete account **KYC / credits** if dashboard requires it | Dashboard + Exotel support |
| 3 | *(Optional)* Purchase via API | [Purchase ExoPhone](https://developer.exotel.com/docs/exophones/api-reference/purchase-number) |

**What Exotel states:** ExoPhone **receives inbound**, **shows as caller ID on outbound**, routes through your **call flow**.  
Source: [ExoPhone setup](https://developer.exotel.com/docs/getting-started/exophone-setup).

### B. Inbound → AI voice agent (this repo)

| Step | Action |
|------|--------|
| 1 | **App Bazaar** → create **Custom App** / flow |
| 2 | Add **Voicebot** applet (bidirectional stream — not one-way Stream-only) |
| 3 | Voicebot URL: `wss://<PUBLIC_HOST>/exotel/stream?sample-rate=8000` **or** dynamic `https://<PUBLIC_HOST>/exotel/ws-url` |
| 4 | Match sample rate with `.env` → `EXOTEL_SAMPLE_RATE=8000` |
| 5 | **Assign flow to ExoPhone** (dashboard or API) | [Assign to flow](https://developer.exotel.com/docs/exophones/api-reference/assign-to-flow) |
| 6 | Call the ExoPhone; server logs: connected → stream start → greeting |

Overview: [How to make or receive calls](https://developer.exotel.com/docs/call-support/call-features/make-receive-calls).

### C. Outbound → connect customer to same AI flow

Use when **you dial the customer**; after they answer, they enter your applet (Voicebot → your bridge).

| Step | Action | Doc |
|------|--------|-----|
| 1 | `POST …/v1/Accounts/<sid>/Calls/connect` | [Outgoing call to call flow](https://developer.exotel.com/docs/voice-v1/api-reference/outgoing-call-to-flow) |
| 2 | `From` = customer number (E.164 or India format per doc) | |
| 3 | `CallerId` = **your ExoPhone** | |
| 4 | `Url` = `http://my.exotel.com/<sid>/exoml/start_voice/<app_id>` (flow with Voicebot) | [Connect to flow](https://developer.exotel.com/docs/voice-v1/api-reference/connect-to-flow) |
| 5 | *(Optional)* `StatusCallback` for completed / failed | [Support: outbound to app](https://support.exotel.com/support/solutions/articles/48278-outbound-call-to-connect-a-customer-to-an-app) |

### D. Outbound — human agent calls customer (not AI bridge)

| Step | Action | Doc |
|------|--------|-----|
| 1 | Agent configured in Exotel dashboard | |
| 2 | `POST /v2/accounts/<sid>/calls` with `virtual_number` = ExoPhone | [Make a call (agent → customer)](https://developer.exotel.com/docs/voice-api/api-reference/make-a-call) |

### E. Exotel doc index (bookmark)

| Topic | URL |
|-------|-----|
| ExoPhone setup | https://developer.exotel.com/docs/getting-started/exophone-setup |
| Purchase number API | https://developer.exotel.com/docs/exophones/api-reference/purchase-number |
| Assign flow | https://developer.exotel.com/docs/exophones/api-reference/assign-to-flow |
| Make / receive calls | https://developer.exotel.com/docs/call-support/call-features/make-receive-calls |
| Outbound → flow (AI/IVR) | https://developer.exotel.com/docs/voice-v1/api-reference/outgoing-call-to-flow |
| Voice v3 overview (reporting + connect) | https://developer.exotel.com/docs/voice-v3/overview |

---

## Plivo — production number + inbound + outbound

Official hub: [Plivo Docs](https://www.plivo.com/docs/)

### A. Get a real Plivo number

| Step | Action | Doc |
|------|--------|-----|
| 1 | Console → **Phone Numbers** → **Buy Numbers** (country, voice capability) | [Numbers overview](https://www.plivo.com/docs/numbers) |
| 2 | **India:** complete KYC before Indian DIDs work | [Rent India numbers](https://www.plivo.com/docs/numbers/rent-india-numbers) |
| 3 | **Compliance** for other countries if prompted | [Regulatory compliance](https://www.plivo.com/docs/numbers/regulatory-compliance) |
| 4 | *(Optional)* Search/buy via API | [Phone Numbers API](https://www.plivo.com/docs/numbers/phone-numbers) |
| 5 | *(Optional)* **Port** existing number to Plivo | [Number porting](https://www.plivo.com/docs/numbers/number-porting) |

**India outbound rule (Plivo docs):** outbound caller ID must be a **Plivo-rented Indian number** — Verified Caller ID is **not** supported for India.  
Source: [Numbers overview — Verified Caller ID](https://www.plivo.com/docs/numbers).

### B. Inbound → AI voice agent (this repo)

| Step | Action | Doc |
|------|--------|-----|
| 1 | Complete Plivo **compliance** (India: CoI/Udyam + GST/PAN as required) | [Rent India numbers](https://www.plivo.com/docs/numbers/rent-india-numbers) |
| 2 | **Voice Applications** → new app → **Answer URL** = `https://<PUBLIC_HOST>/plivo/answer` | [Voice quickstart](https://www.plivo.com/docs/voice/quickstart/quickstart) |
| 3 | **Active Numbers** → assign that application to your Plivo number | |
| 4 | `.env` → `TELEPHONY_PROVIDER=plivo`, restart `python app.py` |
| 5 | Call the Plivo number; Answer URL returns Stream XML → `/plivo/stream` |

### C. Outbound → AI answers when callee picks up

| Step | Action | Doc |
|------|--------|-----|
| 1 | `POST https://api.plivo.com/v1/Account/{auth_id}/Call/` | [Calls API](https://www.plivo.com/docs/voice/api/calls) |
| 2 | `from` = **your Plivo number** (E.164) | |
| 3 | `to` = destination number | |
| 4 | `answer_url` = URL that returns **Stream XML** (same pattern as inbound — your server bridges to Gemini) | [Voice quickstart](https://www.plivo.com/docs/voice/quickstart/quickstart) |

### D. Use your own non-Plivo number as outbound caller ID only

| Step | Action | Doc |
|------|--------|-----|
| 1 | Console → **Verified Caller IDs** → verify via SMS/voice | [Numbers overview](https://www.plivo.com/docs/numbers) |
| 2 | Use verified number as `from` in Call API | |
| 3 | **Not for India outbound** — use rented Indian Plivo number | Same page |

### E. Plivo doc index (bookmark)

| Topic | URL |
|-------|-----|
| Numbers overview | https://www.plivo.com/docs/numbers |
| Phone Numbers API | https://www.plivo.com/docs/numbers/phone-numbers |
| India KYC | https://www.plivo.com/docs/numbers/rent-india-numbers |
| Number porting | https://www.plivo.com/docs/numbers/number-porting |
| Voice quickstart | https://www.plivo.com/docs/voice/quickstart/quickstart |
| Calls API (inbound/outbound) | https://www.plivo.com/docs/voice/api/calls |
| Voice agents + SIP | https://www.plivo.com/docs/voice-agents/sip-trunking/overview |

---

## Side-by-side — what “inbound” and “outbound” mean

| | **Inbound** | **Outbound** |
|---|-------------|--------------|
| **Who dials first** | Customer dials your ExoPhone / Plivo number | Your app/API initiates call to customer |
| **Exotel** | ExoPhone → flow (Voicebot → WSS) | `Calls/connect` + `CallerId` + flow `Url` |
| **Plivo** | PSTN → Plivo number → Answer URL → stream | `Call/` API + `answer_url` when callee answers |
| **Caller ID customer sees** | Your virtual number | Your ExoPhone / Plivo `from` number |

---

## Global product note

- **Exotel** is **India-first**; international coverage is limited vs global CPaaS. See Exotel docs and your account manager for regions.
- **Plivo** targets **100+ / 190+ countries** for numbers and termination — better default for multi-country SaaS.
- **Phase 2/3 in this project:** paid ExoPhone, agent-first failover, then outbound + transfer — see [PHASE1_SETUP_GUIDE.md](PHASE1_SETUP_GUIDE.md) (Phase 2 preview).

---

## Troubleshooting (quick)

| Symptom | Likely fix |
|---------|------------|
| Exotel asks for **PIN** on trial number | Buy **ExoPhone** or exit trial; assign production flow |
| No audio / no stream | Voicebot enabled on account; `PUBLIC_HOST` + tunnel; sample rate match |
| Plivo inbound 404 | Answer URL reachable; app assigned to number |
| India Plivo outbound fails caller ID | Use **rented** Indian Plivo number as `from`, not verified external ID |
