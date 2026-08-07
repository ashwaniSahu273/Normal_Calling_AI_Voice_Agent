# AI Voice as a WhatsAppCRM Product Feature

**Audience:** Product owners, founders, backend developers  
**Goal:** Decide if (and how) AI phone receptionist can ship as a **client-facing feature** inside WhatsAppCRM / ResilioHub — especially the hard parts: accounts, KYC, and phone numbers.

**Short answer:** Yes, it is realistically implementable. Plivo already documents a **reseller / multi-tenant SaaS** model. The main constraint is **India regulation**: each client business needs its own KYC before they get an Indian number. That cannot be skipped or fully “instant.”

---

## Table of contents

1. [Verdict](#1-verdict)
2. [What clients expect vs what is legal](#2-what-clients-expect-vs-what-is-legal)
3. [How Plivo supports this (official)](#3-how-plivo-supports-this-official)
4. [Architecture inside WhatsAppCRM](#4-architecture-inside-whatsappcrm)
5. [Client onboarding flow](#5-client-onboarding-flow)
6. [What is automated vs what needs humans](#6-what-is-automated-vs-what-needs-humans)
7. [Do you need Plivo support?](#7-do-you-need-plivo-support)
8. [Hard challenges](#8-hard-challenges)
9. [Rollout plan (recommended)](#9-rollout-plan-recommended)
10. [Cost & billing model](#10-cost--billing-model)
11. [Official Plivo links](#11-official-plivo-links)
12. [Email draft to Plivo sales](#12-email-draft-to-plivo-sales)

---

## 1. Verdict

| Question | Answer |
|----------|--------|
| Can AI calling be a feature for every WhatsAppCRM client? | **Yes** |
| Does each client need their own Plivo console signup? | **No** — you create a **subaccount** under your master account |
| Does each client need KYC? | **Yes (India)** — Plivo **Reseller** mode requires a **separate compliance application per customer** |
| Can numbers be bought by API? | **Yes** — after that client’s KYC is approved |
| Is this invented / undocumented? | **No** — Plivo documents Multi-tenant SaaS, Reseller, Subaccounts, Buy Number API, India KYC, and Compliance API |
| Fully one-click with zero waiting? | **No** — Plivo still reviews KYC (often minutes to ~1 business day) |

**Bottom line:** Product feature = real. Blocker = regulation + ops (docs, consent, prepaid billing), not missing Plivo APIs.

---

## 2. What clients expect vs what is legal

### What clients often imagine

> “I click Enable AI Calling → I get a number in 10 seconds → calls start.”

### What India + Plivo actually require

1. Client is (or represents) an **India-registered business**.
2. Client uploads **business registration** (COI or Udyam) **and** **tax proof** (Business PAN or GST).
3. You submit a **Compliance Application** as **Reseller** for that customer.
4. Plivo **approves** the application.
5. Then you **rent** an Indian number and attach it to that client’s subaccount / your XML app.
6. Outbound commercial calls need **consent** (cold calling → UCC risk).

So the product UI must be a **status machine** (Draft → Pending → Approved → Number Active), not a fake instant switch.

---

## 3. How Plivo supports this (official)

### 3.1 Subaccounts = one tenant per client

Plivo subaccounts are isolated environments under **your** main account (`MA…`).

Each subaccount gets:

- Own Auth ID (`SA…`) and Auth Token  
- Separate call / message logs  
- Independent webhooks  

Billing:

- All charges deduct from **your parent balance**  
- Subaccounts have **no separate payment method**  
- You track usage per subaccount and invoice clients yourself  

Plivo lists these use cases explicitly:

- Multi-tenant SaaS  
- Reseller / white-label  
- Environment separation (dev / staging / prod)

Docs: [Subaccounts concept](https://www.plivo.com/docs/account/concepts/subaccounts) · [Subaccount API](https://www.plivo.com/docs/account/api/subaccount)

**Important for ISVs:** Plivo’s ISV guidelines say you must segregate traffic **per end brand using sub-accounts**, and complete compliance **separately per brand**.  
Doc: [A2P Guidelines for ISVs](https://www.plivo.com/docs/faq/messaging/isv-guidelines)

### 3.2 Buy numbers by API and assign to a subaccount

Flow:

1. Search available numbers (API).  
2. Buy with **main account** credentials.  
3. Pass `subaccount=SA…` so the number belongs to that client’s isolation.  
4. Attach your Voice XML Application (Answer URL → your bridge).

Docs: [Phone Numbers API](https://www.plivo.com/docs/numbers/phone-numbers) · [Account Phone Numbers API](https://www.plivo.com/docs/numbers/account-phone-numbers)

Note from Plivo: buying with **subaccount** credentials can return **404**. Buy with **main** auth + `subaccount` parameter.

### 3.3 India KYC (core constraint)

Requirements (official):

- Organization must be in **India data region** (cannot change later).  
- Documents (both mandatory):

| Document type | Accepted options |
|---------------|------------------|
| Business registration | COI from MCA **or** Udyam from MSME |
| Tax registration | Business PAN **or** GST certificate |

Business names must match across documents.

**Business types:**

| Type | Meaning | Compliance |
|------|---------|------------|
| Direct Brand | Calls for your own business only | One application |
| **Reseller** | You offer communication services to others | **Separate application per customer** |

Your WhatsAppCRM model = **Reseller**.

Typical review for 080/022 style numbers: often ~15 minutes, up to ~1 business day.

Docs: [India Number KYC](https://www.plivo.com/docs/numbers/rent-india-numbers) · [India calling regulations](https://plivo.com/docs/voice/concepts/india-calling)

### 3.4 Compliance API (so CRM can automate uploads)

Plivo provides a **Compliance API** currently focused on **India**: create end user, upload documents, submit application in one flow.

Docs: [Compliance API](https://plivo.com/docs/numbers/compliance)

This means WhatsAppCRM can:

1. Collect PDF/JPG from the client in your UI.  
2. POST to Plivo Compliance API.  
3. Poll status until Approved / Rejected.  
4. On Approved → buy number → map to tenant.

You automate **your** UX. You do **not** replace Plivo’s compliance review.

---

## 4. Architecture inside WhatsAppCRM

```text
┌─────────────────────────────────────────────────────────────┐
│                     WhatsAppCRM / ResilioHub                 │
│  Web app + Flutter + Node backend                            │
│                                                             │
│  Tenant A          Tenant B          Tenant C               │
│  ├ knowledge       ├ knowledge       ├ knowledge            │
│  ├ greeting        ├ greeting        ├ greeting             │
│  ├ SA… + token     ├ SA… + token     ├ SA… + token          │
│  ├ compliance_id   ├ compliance_id   ├ compliance_id        │
│  ├ +91 number      ├ +91 number      ├ +91 number           │
│  └ usage wallet    └ usage wallet    └ usage wallet         │
└───────────────────────────┬─────────────────────────────────┘
                            │ tenant config + webhooks
                            ▼
┌─────────────────────────────────────────────────────────────┐
│              Voice Bridge (this repo, shared)                │
│  Plivo Stream → Gemini → tools → n8n / your Node APIs        │
│  Route by called number / CallUUID → correct tenant          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     Plivo (your master MA…)                  │
│  Subaccount SA-A   Subaccount SA-B   Subaccount SA-C         │
│  Number A          Number B          Number C                │
│  Compliance A      Compliance B      Compliance C            │
│  All money from YOUR prepaid balance                         │
└─────────────────────────────────────────────────────────────┘
```

### What you store per tenant (suggested)

| Field | Purpose |
|-------|---------|
| `tenant_id` | Your CRM client id |
| `plivo_subaccount_id` | `SA…` |
| `plivo_auth_token_enc` | Encrypted; returned only at create time |
| `compliance_application_id` | KYC tracking |
| `compliance_status` | draft / pending / approved / rejected |
| `phone_number` | E.164 DID |
| `plivo_app_id` | XML application linked to number |
| `voice_enabled` | Feature flag |
| `greeting`, `knowledge_ref`, `human_agent_number` | Per-client agent config |
| `wallet_balance` / prepaid | Protect your Plivo float |

Clients **do not** need Plivo logins. Isolation is API-level via subaccounts.

---

## 5. Client onboarding flow

```text
Client opens WhatsAppCRM
        │
        ▼
Enable “AI Phone Receptionist”
        │
        ▼
Upload COI/Udyam + GST/PAN
        │
        ▼
Your backend → Plivo Compliance API (Reseller / per customer)
        │
        ▼
Status: Pending Approval  ──(Plivo review)──► Approved / Rejected
        │                                              │
        │ Rejected: show reason, allow resubmit         │
        ▼                                              ▼
Choose city / number type                    Buy number via API
        │                                    assign to subaccount
        ▼                                              │
Number Active ◄────────────────────────────────────────┘
        │
        ▼
Inbound / outbound / human transfer / CRM logs work
```

### UX copy that sets correct expectations

- “Approval usually takes 15 minutes to 1 business day.”  
- “Indian business documents are required by telecom regulation.”  
- “Outbound calls only to contacts who opted in.”

---

## 6. What is automated vs what needs humans

| Step | Automated in your product? | Human / external? |
|------|----------------------------|-------------------|
| Create Plivo subaccount | Yes (API) | — |
| Upload KYC docs from CRM | Yes (Compliance API / console) | Client uploads docs |
| Approve KYC | No | **Plivo compliance team** |
| Buy + assign number | Yes (API) after approval | — |
| Point number to bridge | Yes (Application / Number APIs) | — |
| AI conversation + n8n | Yes (your bridge) | — |
| Bill the end client | Yes (your CRM billing) | — |
| Pay Plivo | You fund parent account | Finance ops |
| Handle UCC / abuse | Kill switch + policy | Support + Plivo if suspended |

---

## 7. Do you need Plivo support?

### Covered well by public docs (~80%)

- Subaccounts for multi-tenant SaaS / reseller  
- Buy / assign numbers  
- India KYC document rules  
- Reseller = compliance per customer  
- Compliance API (India)  
- ISV traffic segregation rules  

### Contact Plivo sales / support once (~20%)

Use sales when you want confirmation and commercial terms — **not** because the architecture is secret.

Ask them to confirm:

1. Your India org can operate as **Reseller / ISV**.  
2. **Compliance API** is enabled for your account.  
3. Volume / committed pricing for many client numbers + minutes.  
4. Any extra steps for **140-series** (promotional) if clients need marketing dials.  
5. Shared public bridge URL / webhook domain is acceptable for all subaccounts.  
6. Recommended practices for UCC / consent as a reseller.

Sales: [https://www.plivo.com/contact/sales/](https://www.plivo.com/contact/sales/)

See [email draft](#12-email-draft-to-plivo-sales) below.

---

## 8. Hard challenges

| Challenge | Why it matters | Mitigation |
|-----------|----------------|------------|
| Per-client KYC | No Indian DID without it | Build status UI; Compliance API |
| Clients without GST/COI | Cannot enable full Indian number | Block feature or offer “bring your own number” later |
| You pay Plivo first | Unpaid clients drain your wallet | Prepaid credits; auto-disable number |
| Consent / UCC | Outbound without consent → suspensions | Only call opted-in CRM leads; store consent proof |
| Bad actor tenant | Can risk parent account | Subaccount isolation, rate limits, kill switch |
| Number pending state | Buy may wait on compliance | Show clear status; don’t promise instant |
| Non-India clients | No domestic Indian routes | Separate international Plivo org / numbers later |
| Support load | KYC rejections, wrong docs | Templates + checklist in UI |

These are **product and ops** challenges. The voice bridge you already built is the easy part relative to this.

---

## 9. Rollout plan (recommended)

### Phase 0 — Done / almost done

- Single-business voice bridge (your ResilienceSoft number)  
- Inbound, outbound POC, human handover, n8n logging  

### Phase 1 — Soft multi-tenant (2–4 weeks)

- Feature flag in WhatsAppCRM: “AI Calling (beta)”  
- **Manual** ops: you create subaccount + KYC in Plivo console for 2–3 pilot clients  
- Bridge routes by **called number → tenant config** in your DB  
- Learn rejection reasons and support load  

### Phase 2 — Self-serve onboarding (1–3 months)

- Subaccount API + Compliance API + Buy Number API from Node backend  
- Wallet / prepaid minutes  
- Admin dashboard: tenants, KYC status, usage, kill switch  
- Docs + in-app checklist for GST/COI  

### Phase 3 — Scale

- Plivo volume contract  
- Optional BYON (bring your own number / SIP) for advanced clients  
- Multi-country (second Plivo region) if you expand globally  

Do **not** jump to Phase 2 before 2–3 paid pilots succeed in Phase 1.

---

## 10. Cost & billing model

### What you pay Plivo

- Monthly rental per number  
- Per-minute inbound / outbound (India list pricing is published on Plivo pricing pages; negotiate volume)  
- Your AI (Gemini / OpenAI) token cost separate  

### What you charge the client (examples)

| Model | Example |
|-------|---------|
| Setup | One-time number + KYC onboarding fee |
| Subscription | ₹X / month includes Y minutes |
| Usage | ₹Z / minute markup over Plivo |
| Hybrid | Base plan + overage |

**Rule:** Client prepaid wallet must stay ≥ estimated weekly usage, or disable outbound / whole feature.

---

## 11. Official Plivo links

| Topic | URL |
|-------|-----|
| Subaccounts (concept) | https://www.plivo.com/docs/account/concepts/subaccounts |
| Subaccount API | https://www.plivo.com/docs/account/api/subaccount |
| Buy phone numbers API | https://www.plivo.com/docs/numbers/phone-numbers |
| Manage rented numbers | https://www.plivo.com/docs/numbers/account-phone-numbers |
| India Number KYC | https://www.plivo.com/docs/numbers/rent-india-numbers |
| Compliance API (India) | https://plivo.com/docs/numbers/compliance |
| India calling regulations | https://plivo.com/docs/voice/concepts/india-calling |
| ISV / reseller guidelines | https://www.plivo.com/docs/faq/messaging/isv-guidelines |
| Contact sales | https://www.plivo.com/contact/sales/ |

Related project docs:

- Architecture & URL flow: [FLOW.md](FLOW.md)  
- Backend integration notes: [INTEGRATION.md](INTEGRATION.md)  
- Plivo console setup (single business): [PLIVO_SETUP.md](PLIVO_SETUP.md)

---

## 12. Email draft to Plivo sales

Use this when you are ready:

```text
Subject: Reseller / multi-tenant SaaS — India voice + Compliance API

Hi Plivo team,

We are building an AI phone receptionist feature inside our WhatsApp CRM
(ResilioHub / WhatsAppCRM) for Indian SMBs.

Model:
- We are the platform (ISV / Reseller)
- Each end customer is a Direct Brand under us
- We plan to use Subaccounts (one SA per customer)
- India domestic numbers after per-customer KYC
- Shared Voice Stream / XML Application pointing to our bridge

Please confirm / advise:
1) Our India-region account can operate as Reseller (compliance per customer)
2) Compliance API access for automated KYC document submission from our product
3) Recommended number types for service/transactional inbound+outbound AI receptionists
4) Volume pricing for many numbers + concurrent minutes
5) Any extra requirements for promotional (140-series) if customers need outbound campaigns

We already have a working single-tenant Plivo + Gemini Live bridge and want to
productize it for multiple CRM tenants.

Thank you,
[Name]
[Company]
[Auth ID if useful: MAMZYXY2MXZDETNJA2OC]
[Phone / email]
```

---

## Final takeaway

**Yes — implement as a WhatsAppCRM feature.**  
Use **one Plivo master account + subaccounts + per-client India KYC + number APIs**.  
Public docs cover the design. Contact Plivo to confirm **Reseller** status, **Compliance API**, and pricing.

The feature is not blocked by missing technology. It is gated by **compliance UX, prepaid billing, and careful rollout** — start with manual pilots, then automate.
