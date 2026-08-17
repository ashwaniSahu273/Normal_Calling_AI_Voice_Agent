# India calling buzzwords + Plivo support ticket

**Use:** Learn TRAI/DLT terms, then send the ticket to Plivo before selling outbound / collections / multi-tenant voice.

**Send ticket:** [support.plivo.com/hc/en-us/requests/new](https://support.plivo.com/hc/en-us/requests/new) · **support@plivo.com** · Console **Buddy** · Sales: [plivo.com/contact/sales](https://www.plivo.com/contact/sales/)

**Related:** [PRODUCT_MULTI_TENANT.md](PRODUCT_MULTI_TENANT.md) · [PLIVO_SETUP.md](PLIVO_SETUP.md) · [API_INTEGRATION.md](API_INTEGRATION.md)

**Not legal advice.** Buddy answers below (14 Aug 2026) are from Plivo Console docs-bot — still keep a PDF. For capacity/discount, use human Sales.

---

## 1. Picture

```
Customer phone
     ↑  CLI shows 1600-xxxx  or  022-xxxx  or  140-xxxx
     ↑
  Plivo (aggregator + TM)
     ↑
  Your Python voice AI + ResilioHub
     ↑
  Client company = PE (their KYC, their number, their DLT)
```

ResilioHub = platform. Each **client business** should be **PE**. You/Plivo = TM/aggregator. Do **not** call from *your* DID pretending to be *their* company.

---

## 2. Buzzwords

### Who is who

| Term | Meaning |
|---|---|
| **TRAI** | Telecom regulator. Rules for calls/SMS. |
| **DoT** | Gives number series (140, 1600, landline). |
| **RBI** | Bank/NBFC regulator. Recovery: typically **8:00–19:00**, no harassment, log/record calls. |
| **BFSI** | Banks, NBFCs, insurance, brokers, pension. |
| **PE (Principal Entity)** | Brand whose name is on the call. Example: your tenant “ABC Finance”. |
| **TM (Telemarketer)** | Who places the call. PE itself, a BPO, or Plivo as TM. |
| **Aggregator / TSP** | Pipe to the phone network. Plivo sits here. |
| **PE–TM–Aggregator chain** | TRAI wants: *client (PE) → telemarketer → Plivo*. Break it = illegal commercial call. |

### Number types (what flashes on the phone)

| Series | Looks like | Allowed use | Who |
|---|---|---|---|
| **Landline / DID** | `022-…`, `080-…` | **Service / transactional only** (support, appointment, order). **No sales pitch.** | Non-BFSI India companies |
| **140-series** | `140-…` | **Promo / sales / marketing** only | Any business after DLT + consent + DND |
| **160-series / 1600 / 1601** | `1600-…` / `1601-…` | **BFSI service + transactional only** (EMI, OTP, loan update, collections reminder). **No promo.** | Only RBI/SEBI/IRDAI/PFRDA entities |

**DID** = rented virtual number (not a personal SIM).  
**CLI / Caller ID** = number shown to the customer. India: must be a **Plivo-rented Indian number**.

Wrong series → TRAI can treat the call as **UCC** even with “consent”.

### DLT / consent / spam

| Term | Meaning |
|---|---|
| **DLT** | TRAI blockchain registry for PE, headers, templates, consent. Plivo **160-series = Tata DLT only** (not Airtel/Vi/BSNL DLT). |
| **Header** | Sender identity. SMS = `HDFCBK`. Voice = registered 1600/140 number. |
| **Voice Header** | That number registered on DLT as voice sender ID. |
| **Content Template / Template ID** | Pre-approved script type (EMI reminder, OTP…). |
| **Consent** | Customer explicitly allowed you to call for that purpose. Cold call = banned. |
| **NCPR / DND** | National Do Not Disturb list. Promo cannot hit DND without valid consent. |
| **Scrubbing** | Before dial: check list vs DND + consent. Fail = skip. |
| **UCC** | Unsolicited Commercial Communication (spam). Complaints → warning → usage cap → disconnect + blacklist (~2 years). |
| **UTM** | Unregistered Telemarketer. Commercial calls from random 10-digit SIMs. |

### KYC / account / calling tech

| Term | Meaning |
|---|---|
| **KYC** | Company docs to Plivo before India numbers. Usually **COI or Udyam** + **PAN or GST**. Names must match. |
| **India data region account** | Plivo India account. Cannot switch later. INR + GST. |
| **Subaccount** | Child Plivo account under you. One per tenant = isolated numbers, keys, usage. |
| **E.164** | `+912264233283`. |
| **CPS** | Calls per second. India default **2/sec**. |
| **Concurrency** | Calls at the same time. India default **50**. Over → `5030`, no queue. |
| **Media anchoring** | Both call legs stay **inside India**. Else hangup `violates_media_anchoring`. |
| **AMD** | Answering Machine Detection. Voicemail answer = still billed unless `machine_detection=hangup`. |
| **60/60 billing** | Round up to full minute. 10s = 1 min. Starts when **answered**, not ringing. |
| **A-leg / B-leg** | Customer↔Plivo and Plivo↔agent. Each answered leg billed. Live transfer = 2× telephony. |
| **NOC** | Plivo letter linking 160 numbers to PE ID. |
| **TM ID** | Plivo telemarketer ID you attach on Tata DLT for Voice Header. |

### Recovery (loan / udhar)

| Term | Meaning |
|---|---|
| **Collections / recovery** | Calling to collect overdue EMI / loan / udhar. |
| **Fair Practices** | RBI recovery conduct: hours, no threat, no family/friends, no excessive calling. |
| **PTP** | Promise To Pay — log date, remind later. |

### Plivo published timelines (confirm in ticket)

| Type | Typical time |
|---|---|
| Landline 022/080 KYC | ~15 min to **1 business day**, then rent |
| **160-series** | DLT 2–3d + alloc 1–2d + header 3–5d + template 1–2d ≈ **7–14 business days** |
| **140-series** | Extra DLT/promo setup (separate SLA) |

Official: [India KYC](https://www.plivo.com/docs/numbers/rent-india-numbers) · [India calling](https://www.plivo.com/docs/voice/concepts/india-calling) · [160-series](https://www.plivo.com/docs/voice/concepts/160-series-provisioning) · [Account limits](https://www.plivo.com/docs/voice/concepts/account-limits) · [India concurrency](https://www.plivo.com/docs/voice/concepts/india-concurrency) · [India pricing](https://www.plivo.com/voice/pricing/in/)

---

## 3. Product rules (our stance)

| Idea | Do it? |
|---|---|
| AI outbound reminder to **existing customers** (appointment, order, EMI if NBFC) | Yes, correct series + consent + hours |
| Feature for **every tenant** | Yes **only if** each tenant = own KYC + own number (+ **160** if BFSI) |
| One shared 022 DID for all clients | No |
| Informal udhar shop, unregistered lender, recovery dialer | **Do not sell.** Buddy: not 160; promo/no-consent not allowed |
| Customer **blocks** number → call from **another** number | **No.** Buddy: not a compliant pattern |
| Multiple numbers for capacity / spam-flag retirement | OK for scale / isolate after review — not to evade block |

---

## 4. How to send

1. Console → **Buddy** — use [short text below](#4b-buddy-chat--1000-words) (~570 words)
2. Full ticket (email): https://support.plivo.com/hc/en-us/requests/new · **support@plivo.com**
3. Sales: https://www.plivo.com/contact/sales/

India office: 1st Floor, No. 386, 4th D Main, 12th Cross, West of Chord Road, Mahalakshmipuram, Bengaluru 560086.

Fill `[BRACKETS]` before send.

---

## 4b. Buddy chat (< 1000 words)

Paste this in **Plivo Console → Buddy**. ~570 words.

```
Hi Buddy. We are ResilioHub / WhatsApp CRM (India SaaS). We already have a working POC: Plivo Voice API + bidirectional WebSocket stream + Gemini Live AI.

We want AI calling as a FEATURE for many clients on our website: inbound receptionist + outbound reminders. Please answer point by point.

1) Can we serve many separate businesses from ONE parent Plivo account using Subaccounts (one per client, own KYC + own number)? Is that the right model?

2) Can WE collect each client’s KYC and buy/assign numbers for them, or must each client open their own Plivo account?

3) Must each client use their OWN Plivo number as caller ID? Can we share one number across many clients?

4) If a client is not India-registered, can they get an Indian DID and cheap India outbound? If no, what is the only option?

5) Our AI/WebSocket bridge may run outside India. Will India calls fail due to media anchoring? Must the bridge be hosted in India?

6) What KYC documents are required for (a) 022/080 landline (b) 140-series promo (c) 160-series BFSI? Common rejection reasons?

7) After KYC submit, typical time until the number can make/receive calls for 022/080, 140, and 160 — best and worst case?

8) Can we do KYC + buy number + set Answer URL fully by API per Subaccount?

9) Can a client use their own mobile/landline as outbound caller ID in India? We think no. Confirm.

10) Which number series is allowed vs not allowed for:
a) inbound AI receptionist
b) outbound reminder to existing customer (appointment/order/support)
c) outbound sales/promo
d) registered NBFC/bank: EMI/loan overdue AI reminder
e) shop / informal lender NOT RBI-registered: “please pay udhar/loan” AI calls
f) missed-call + WhatsApp only, no live AI
Please be explicit on (d) and (e). If (e) is not allowed, say so clearly.

11) For banks/NBFCs, is 160-series mandatory now for EMI/collections? Can they still use 022/080? Until when?

12) 160-series simple steps: does client need Tata DLT PE? What does Plivo do vs client? How many days? Must caller ID always be THAT client’s 1600 number, not our number used for many NBFCs?

13) India limits today and how to raise: concurrent calls, outbound CPS, max call duration. If we exceed concurrency, is the extra call rejected immediately?

14) Confirm India Voice INR pricing: outbound/min, inbound/min, DID rent/month, streaming extra? Billing starts on ANSWER not ring? Unanswered/busy/failed = Rs 0? Voicemail answer billed? Human transfer = both legs billed? 10-second call = 1 full minute?

15) Do you auto-skip DND numbers on outbound, or must WE scrub? Any API?

16) Who enforces calling hours (e.g. 8am–7pm for recovery) — Plivo or our software?

17) Client wants 2–3 numbers. If customer BLOCKS number A, can AI immediately call again from number B? Allowed or UCC/TRAI violation? When IS extra numbers OK (more volume, or one DID marked Spam by Jio/Airtel)?

18) If one client gets a UCC/spam complaint: suspend only that Subaccount or whole parent? Can other clients keep calling? What proof do you need (consent, recordings)?

19) Can we record outbound reminder/collections calls? Extra cost? Must we say “this is an automated/AI call” at the start?

20) Please share: current India rate card; how to raise concurrency above 50 and volume discount; India TAM/email/phone for SaaS onboarding; can we demo with a trial number before each client finishes KYC?

Auth ID: [PASTE AUTH ID]. Company: [NAME]. Contact: [PHONE] [EMAIL].
```

---

## 5. Ticket to copy (20 questions)

**Subject:** India AI voice for our SaaS — many clients, KYC time, outbound limits

```
Hello Plivo Support / India Sales,

Account Auth ID: [PASTE AUTH ID]
Company: [YOUR COMPANY LEGAL NAME]
Product: ResilioHub / WhatsApp CRM (SaaS)
Website: [URL]
Contact: [NAME, MOBILE, EMAIL]
India GST: [YES/NO — GSTIN]

We run a WhatsApp CRM. We want to add AI phone calling as a feature for our clients:
- inbound: customer calls the business, AI answers
- outbound: AI calls the customer (reminders / follow-up)

We already have a working POC: Plivo Voice + WebSocket audio stream + Gemini Live.

Please reply in writing, question by question (1–20).

--------------------------------
A. Feature for every client on our website
--------------------------------

1. Can we sell AI calling to many separate businesses from ONE Plivo parent account?
   Plan: one Subaccount per client, each with their own KYC and phone number.
   Is this the correct model? If not, what should we use?

2. Can WE collect each client’s KYC docs and buy/assign numbers for them (API or console),
   or must each client open their own Plivo account?

3. Must each client use their OWN Plivo number as caller ID?
   Can we share one number across many clients? (We think no — please confirm.)

4. If a client is not an India-registered company, can they get an Indian number
   and make cheap India outbound calls? If no, what is the only option?

5. Our AI server (Gemini / WebSocket bridge) may run outside India.
   Will India calls fail because of media anchoring?
   Do we need to host the voice bridge inside India?

--------------------------------
B. KYC + renting numbers + how long
--------------------------------

6. What documents are required for:
   a) normal landline numbers (022 / 080)
   b) 140-series (promo)
   c) 160-series (banks / NBFCs)
   What usually causes rejection?

7. After we submit KYC, how long until the number can actually make/receive calls?
   Please give typical time for 022/080, 140-series, and 160-series
   (best case and worst case).

8. Can we do this fully by API for each Subaccount: submit KYC → buy number →
   point it to our Answer URL? Or is some console/manual work required?

9. Can a client use their own existing mobile/landline as outbound caller ID?
   We believe India does not allow this — please confirm.

--------------------------------
C. Which number type for which call
--------------------------------

10. Which number series should we use for each case? (allowed / not allowed)

    a) Customer calls IN to our AI receptionist
    b) We call OUT to remind an existing customer (appointment / order / support)
    c) We call OUT for sales / promotions
    d) A registered NBFC/bank client: EMI / loan overdue reminder (AI)
    e) A shop / informal lender (NOT registered with RBI): “please pay udhar/loan” AI calls
    f) Only missed-call + WhatsApp, no live AI talk

    Please be especially clear on (d) and (e). If (e) is not allowed, say so clearly.
    We will not sell that use case.

11. For banks/NBFCs, is 160-series mandatory now for EMI/collections?
    Can they still use a normal 022/080 number? Until when?

12. 160-series on Plivo — in simple steps:
    - Does the client need Tata DLT (Principal Entity)?
    - What do you do vs what does the client do?
    - How many days?
    - Must the caller ID always be THAT client’s 1600 number
      (not our company number used for many NBFCs)?

--------------------------------
D. Outbound limits + cost
--------------------------------

13. What are our India limits today, and how do we increase them?
    - how many calls at the same time (concurrency)
    - how many new outbound calls per second
    - max call length
    If we go over concurrency, is the extra call rejected immediately?

14. India Voice API pricing (INR), please confirm:
    - outbound ₹ per minute
    - inbound ₹ per minute
    - number rental ₹ per month
    - is audio streaming extra?
    - billing starts when the person ANSWERS (not when it rings)?
    - unanswered / busy / failed = ₹0?
    - if voicemail answers, do we still pay?
    - if we transfer to a human agent, do we pay for BOTH call legs?
    - is a 10-second call billed as 1 full minute?

15. Do you automatically skip DND / Do-Not-Disturb numbers on outbound,
    or must WE check DND ourselves? Any Plivo API for this?

16. Who must block calls outside allowed hours (example: 8 AM–7 PM for recovery)?
    You, or our software?

--------------------------------
E. Multiple numbers + “customer blocked us”
--------------------------------

17. A client wants 2–3 Plivo numbers.
    If a customer BLOCKS number A, can the AI immediately call again from number B?
    Is that allowed or against TRAI/UCC rules?
    If not allowed, when IS it OK to use extra numbers
    (example: more call volume, or one number marked Spam by Jio/Airtel)?

--------------------------------
F. If one client gets a spam complaint
--------------------------------

18. If one client gets a UCC / spam complaint:
    - do you suspend only that Subaccount, or our whole parent account?
    - can our other clients keep calling?
    - what proof do you need from us (consent, recordings)?

19. Can we record outbound reminder / collections calls?
    Any extra price or consent text we must play at the start?
    Must we say “this is an automated / AI call”?

--------------------------------
G. Pricing help + next step
--------------------------------

20. Please share:
    - current India rate card (voice + numbers)
    - how to raise concurrency above 50 and get volume discount
    - an India contact (email / phone / TAM) for SaaS onboarding
    - whether we can demo with a trial number before each client finishes KYC

We can join a call. Suggested time: [DATE/TIME IST].

Thank you,
[NAME]
[TITLE], [COMPANY]
[PHONE]
[EMAIL]
Plivo Auth ID: [AUTH ID]
```

---

## 6. After they reply

Keep Buddy/email as PDF. This file is the working summary.

If they say **no** to informal recovery (Q10e) or **no** to call-after-block (Q17): do not ship those features. **Both are no (see §7).**

---

## 7. Plivo Buddy replies (14 Aug 2026)

Source: Plivo Console **Buddy** (docs search). Not a signed contract. Rates/limits are **this account**. Human Sales still needed for concurrency >50, volume discount, TAM.

### Verdict

Reseller model **yes**: 1 parent India account + 1 **subaccount per client** + **own KYC** + **own Plivo number**.  
Voice bridge for India domestic: **host in India** (media anchoring).  
Do **not** ship: shared DID, informal udhar recovery, block→number B, client traffic before that client’s KYC.

```
Phase 1:  Inbound 022 + consented service outbound + missed-call → WhatsApp
Phase 2:  Marketing 140 after Tata DLT + consent + DND scrub (we build)
Phase 3:  Collections 160 only licensed NBFC/bank, that client’s 160, 8–7
Never:    Informal udhar dialer, shared 022, cold list, KYC-pending traffic
```

### Q1–5 SaaS model

| Q | Buddy |
|---|---|
| 1 Subaccounts | **Yes.** One parent, one subaccount per client. Isolated Auth ID/token, logs, webhooks. Billing still from **parent** balance. Number belongs to **one** account. |
| 2 We collect KYC | **Yes** as Reseller. **Separate compliance application per customer.** Docs: COI (MCA) or Udyam (MSME) **and** Business PAN or GST. Both mandatory. Compliance API for end users / docs / applications. |
| 3 Own vs shared CLI | **Own number only.** Do not share one caller ID across clients. Tie rental to that customer’s **approved** compliance application. |
| 4 Non-India client | **No** Indian DID / domestic routes. Only **international** rates + US/international CLI. |
| 5 Bridge outside India | India media anchoring: both legs in India. Cross-border → `violates_media_anchoring`. **Host real-time voice bridge in India** for India domestic. |

Docs: [Subaccounts](https://www.plivo.com/docs/account/concepts/subaccounts) · [India KYC](https://www.plivo.com/docs/numbers/rent-india-numbers) · [India calling](https://www.plivo.com/docs/voice/concepts/india-calling)

### Q6–9 KYC, time, API, CLI

**022/080 docs:** COI or Udyam + PAN or GST.  
**Reject:** one doc only; COI/Udyam not from MCA/MSME; missing CIN/Udyam number; **name mismatch**.

**140 extra:** Tata DLT PE + TM, active GST, Aggregator Telemarketer Declaration to Plivo, **NOC per 140 number**, Voice Header + Voice Template on Tata DLT.

**160 extra:** Valid **RBI/SEBI/IRDAI/PFRDA** licence, Tata PE (+ TM if partner-managed), BFSI Customer Application Form, Aggregator declaration, **NOC per 160 number**, Voice Header + Template. Reject: incomplete docs, PE/TM mismatch, invalid NOC/licence.

| Series | Typical time to live |
|---|---|
| 022/080 | KYC **15 min – 1 business day**, then rent and use |
| 140 | **~5–10 business days** (DLT 2–3 + alloc/NOC 1–2 + header 1–2 + template 1) |
| 160 | **~7–14 business days** (DLT 2–3 + alloc/NOC 1–2 + header 3–5 + template 1–2) |

**API:** Partial **yes**. Compliance API + buy number with main-account credentials, pass `compliance_application_id`, `subaccount`, `app_id`. Applications API sets Answer URL. **140/160 still need Tata DLT + Plivo NOC** — not full API-only.

**Own mobile/landline as CLI:** **No.** India = Plivo-rented Indian number only. Verified Caller ID **not** for India.

### Q10 Use case → series

| Use | Allowed |
|---|---|
| a) Inbound AI receptionist | **022/080** non-BFSI. BFSI service → **160** |
| b) Outbound appointment/order/support reminder | **022/080** non-BFSI. **No promo copy** on landline |
| c) Outbound sales/promo | **140 only** + explicit digital consent. Not 022, not 160 |
| d) Registered NBFC/bank EMI / overdue reminder | **160 only.** Must hold regulator licence |
| e) Shop / informal lender, not RBI-registered, “pay udhar/loan” | **Not 160.** Do not fake BFSI. If promo or no consent → **not allowed**. **Do not sell this feature** |
| f) Missed-call + WhatsApp, no live AI | Client’s own Plivo India number + KYC. 022 non-BFSI / 160 if BFSI service. India DIDs **voice-only** — **no SMS** |

Wrong series = UCC **even with opt-in**.

### Q11–12 160 / BFSI

- Plan **bank/NBFC EMI/collections on 160, not 022/080**.
- **Partner-managed:** client = **PE**, ResilioHub = **TM**, Plivo = Access Service Provider (allocate 160 + **NOC per number**). Not PE, not TM.
- Client: regulator licence + Tata PE. You: Tata TM if you place calls. PE registers Voice Header (160 as Header CLI); TM approves in partner-managed. PE registers Voice Templates (payment reminder, OTP, etc.).
- Caller ID = **that client’s allocated 160**. **No shared 160** across NBFCs.
- Constraint: Plivo accepts 160 provisioning only if **TM entity registered in Mumbai or Karnataka**; 160 via **Tata DLT only**.
- Timeline **~7–14 business days**.

Docs: [160-series](https://www.plivo.com/docs/voice/concepts/160-series-provisioning) · [140-series](https://www.plivo.com/docs/voice/concepts/140-series-provisioning)

### Q13–16 Limits, money, DND, hours

**This account (Buddy lookup):** concurrent **50**, outbound CPS **2**. India: all PSTN (in+out, Voice API + SIP) count. Formula: CPS = concurrency ÷ 25.

Exceed concurrency → **immediate reject**, no queue. Error **5030 / Concurrency Limit Breached**.

Max duration: default **4 hours** from answer; can extend to **24 hours**.

Raise capacity: tell Sales expected monthly minutes + needed concurrency/CPS. Enterprise request.

**This account rates (Buddy):**

| Item | Rate |
|---|---|
| Outbound local | **₹0.296/min** (variants may apply) |
| Inbound local | **₹0.60/min** |
| DID rent | **₹250/month** |
| SIP/Zentrunk India | **₹0.344/min** |
| Audio streaming | No separate India surcharge in retrieved pricing — billed as the voice call unless contract says else |

Billing: starts on **answer**. Min **60s**, 1-minute increments. Unanswered / busy / rejected / failed = **₹0**. Voicemail answer = **billed**. `<Dial>` transfer = **both legs** billed when each answers. 10-second answered call = **1 minute**.

**DND:** Plivo has **no** documented auto-skip / pre-dial DND API. **We scrub** in software (consent, DND, blocked, complainants). UCC API = **after** complaint (list complaints, submit opt-in proof) — [UCC management](https://www.plivo.com/docs/voice/concepts/ucc-management).

**Calling hours (8am–7pm):** **Our dialer.** Plivo does not auto-block by recovery window.

### Q17–20 Extra numbers, UCC, record, demo

| Q | Buddy |
|---|---|
| 17 Block A → immediately call from B | **Do not.** Not a safe/compliant pattern (block, opt-out, DND, UCC). |
| Extra numbers OK when | Separate number **per client**; separate **series** per use; extra **capacity** with valid consent; **replace/isolate** a number after compliance review — **not** to evade spam/block. |
| 18 UCC blast radius | Tied to **compliance ID**, not “subaccount only”. Unresolved complaint → block/suspend that compliance ID. Number **with no** compliance ID → can count against **billing entity** (parent risk). Other clients OK **only if** their IDs untouched and no billing-entity action. |
| UCC proof (all three) | Business **logo/identity** + opt-in **date within 6 months** of complaint + complainant’s **exact phone**. Then **remove** that number from lists. Calling a complainant again = violation. |
| 19 Record | **Yes** — Voice API/XML `<Record>`. Storage charged after **90 days** unless you download elsewhere. Plivo **does not** force “this is an AI call” in API — **our legal/compliance** must define disclosure for collections. |
| 20 Trial before client KYC | **No** India number until KYC approved. Reseller: **do not** run that client’s traffic before **their** compliance application is in place. Capacity/discount/TAM = **Enterprise/Sales**. Buddy asked for expected **monthly minutes**. |

Docs: [UCC](https://www.plivo.com/docs/numbers/ucc) · [Record a call](https://www.plivo.com/docs/voice/use-cases/record-a-call) · [Account limits](https://www.plivo.com/docs/voice/concepts/account-limits)

### What we must build (Plivo will not)

1. Host voice bridge **in India**.
2. Node: Subaccount + Compliance API + buy with `compliance_application_id` + `subaccount` + `app_id` (**main-account** keys for buy).
3. Dialer: consent store, DND/opt-out, hours, complainant suppress, no block-bypass.
4. UI: Marketing / Collections **locked** until 140/160 live.
5. UCC: proof pack (logo + date + number) + Plivo UCC API/dashboard.
6. Sales: monthly minutes range + concurrency raise + confirm **TM registered Mumbai or Karnataka** for 160.

### Open with human Sales (Buddy cannot close)

- Volume INR discount vs ₹0.296 outbound  
- Concurrency **>50** / CPS **>2**  
- India TAM / WhatsApp / phone  
- Confirm TM Mumbai/Karnataka for 160 partner-managed  
- Written confirmation if media server **must** be India VPS (Buddy said yes for production)