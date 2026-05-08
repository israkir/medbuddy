# MedBuddy — Product Requirements Document (Extended)

> **Start here for executives / partners:** [`prd.md`](prd.md) — short summary (~2–3 pages), plain language. **This file** is the full specification (requirements IDs, metrics conditions, engineering pointers).

## Table of contents

1. [Introduction](#1-introduction)
2. [Scope and boundaries](#2-scope-and-boundaries)
3. [Problem statement](#3-problem-statement) — includes [market wedge](#34-market-wedge-and-differentiation), [go-to-market](#35-go-to-market), [alignment with executive summary](#36-alignment-with-executive-summary-prd)
4. [Strategic goals](#4-strategic-goals)
5. [Target users and personas](#5-target-users-and-personas)
6. [User journeys](#6-user-journeys)
7. [Functional requirements](#7-functional-requirements)
8. [Non-functional requirements](#8-non-functional-requirements)
9. [Out of scope](#9-out-of-scope)
10. [Success metrics](#10-success-metrics)
11. [Risks and mitigations](#11-risks-and-mitigations)
12. [Assumptions and dependencies](#12-assumptions-and-dependencies)
13. [Open decisions](#13-open-decisions)
14. [Phased roadmap](#14-phased-roadmap)
15. [Related documentation](#15-related-documentation)

---

## 1. Introduction

MedBuddy is a **patient-facing medication companion** that helps people remember what they take, understand their medications in plain language, flag potential interaction concerns, and stay on top of their daily doses — delivered through **LINE Messaging** (the dominant chat platform in Taiwan) and an **HTTP API** for integrations and future clients.

**How users interact today:**
- **By text** on LINE or via the HTTP API.
- **By voice** on LINE when enabled — we turn the recording into text (**speech-to-text**), then the same assistant handles it; we can optionally send a **spoken** reply if that’s configured. Partner apps can upload a short clip via the HTTP **`/v1/app/messages/voice`** endpoint.

The **live prototype** supports **both typing and voice**. For **closing this pilot**, we **do not** require pass/fail targets on transcription accuracy, synthetic-voice quality, or **cost per voice message**—that bundle is **NG-1** until leadership agrees criteria under **OD-3** (see **Sections 9–10**). After that, we can add formal **service-level** expectations for voice.

---

## 2. Scope and boundaries

**What we measure for pilot success** stays focused: Section **10** does **not** add voice-accuracy or voice-cost gates yet (**NG-1**). In production configuration, users may still use **text or voice** on LINE (and voice uploads on HTTP); after transcription, the **same features** apply as for typed input.

| Dimension | In the deployed prototype | Pilot success criteria (Section 10) |
|-----------|------------------------|------------------------------|
| **LINE** | Text and voice in; text replies out; optional spoken replies when configured; text dose reminders | Voice **quality and cost** are **not** pass/fail until **OD-3** |
| **HTTP API** | Text and voice upload endpoints; same assistant as LINE | Same |
| **Features** | Full intent set in Section 7 | Same behavior after speech-to-text |
| **Mobile** | Integrations + reference Expo app via HTTP | Reference app is **not** a co-equal pilot channel |

---

## 3. Problem statement

Patients managing chronic medications in Taiwan face three persistent gaps:

**1. Scattered mental model**
People struggle to maintain an accurate picture of what they take, when, and why — especially when managing medications for a family member or juggling multiple prescribers. There is no single place that holds the complete, up-to-date picture.

**2. Adherence friction**
Existing reminder tools are either intrusive (standalone apps that require behavior change) or passive (paper instructions nobody follows). Most patients in Taiwan already use LINE daily. A medication companion inside that familiar channel removes the adoption barrier entirely.

**3. Language and information gap**
Most drug-reference tools are English-only or use clinical language inaccessible to patients. Pharmacy consultations are short, and there is no easy channel for follow-up questions in plain Traditional Chinese.

Existing tools are app-centric, English-only, or disconnected from the conversational channels embedded in daily life in Taiwan.

### 3.4 Market wedge and differentiation

MedBuddy’s wedge is the overlap of **LINE as daily infrastructure in Taiwan**, **chronic polypharmacy with a comprehension/adherence gap**, and **Traditional Chinese–first plain language**—delivered **without a separate install**.

| Lever | What it means for us |
|-------|---------------------|
| **Channel** | LINE removes adoption friction versus standalone med apps; reminders and Q&A land where family chat already happens. |
| **Job to be done** | Combined **med list + explain/interaction/side-effect framing (non-diagnostic) + dose reminders and confirm/miss in chat**—not “alerts only.” |
| **Locale** | **zh-TW** and **en**, including mid-session switch; many drug tools remain English-heavy or clinically opaque. |
| **Architecture** | **One assistant core** on LINE and the **HTTP API**—partners and CI validate the same product surface patients use. |
| **Trust** | **G5** / [privacy.md](privacy.md): redaction and narrow model context versus pasting health text into a generic chatbot. |

### 3.5 Go-to-market

| Element | Direction |
|---------|-----------|
| **Beachhead** | Taiwan; LINE-forward; adults and caregivers on **2–6 chronic meds** (**Section 5.1**). |
| **Distribution** | Primary: **LINE** official account / bot. **HTTP API** enables tests, integrations, and future **B2B2C**—not the first mass consumer channel. |
| **Pilot** | **Small, controlled cohort**; recruitment specifics (community vs. clinical vs. partner-led) remain **operational choices**—not commitments in this PRD. |
| **Positioning** | Wellness-oriented **medication companion**; no certified **medical device** claims (**R-6**); emergencies → fixed safety copy, not generative triage. |
| **Growth gate** | **Section 10** met; **OD-1** (Taiwan regulatory classification) and stakeholder appetite before scaled acquisition or institutional packaging (**OD-4**). |

### 3.6 Alignment with executive summary PRD

The executive summary **[`prd.md`](prd.md)** carries the same **wedge**, **go-to-market**, and **roadmap sequencing rationale** in short form. Sections **3.4–3.5** and **Section 14** (including sequencing preamble) here are authoritative for tables, requirement IDs, and exit criteria; **`prd.md`** should stay in lockstep on narrative—if positioning or phase order changes, update both files in the same change.

---

## 4. Strategic goals

The last column is **“does the codebase support it + CI”**—not “pilot passed.” Closing the pilot still requires **Section 10** (targets and how we measure them). Day-to-day engineering: GitHub Actions (lint + tests), local **`make be-check`**.

| ID | Goal | What we accept for the pilot | Evidence in the repo today |
|----|------|------------------------------|----------------------------|
| **G1** | **Reliable medication list** | Add, update, and remove work end-to-end; tests cover the paths; no data loss in the cohort. | Medication agent + CRUD tools; Supabase or in‑memory store; pytest with mock integration mode. |
| **G2** | **Understandable drug answers** | Answers use drug reference data when we have it; no diagnosing or prescribing; human review for tone/clarity in both languages. | Explain / interaction / side-effect tools; OpenFDA (+ TFDA stub); caches; localized prompts and copy. |
| **G3** | **Adherence support on LINE** | Reminders at the right local time; user can confirm or report a miss **in chat** (typed or voice transcribed on LINE). | Dose events, job queue, LINE delivery, confirm/missed tools, reminder recovery endpoint (see [reminders.md](reminders.md), [tdd-extended.md](tdd-extended.md)). |
| **G4** | **Bilingual experience** | Full **zh-TW** and **en**; user can switch language mid-chat; native speaker check. | Locale files, profile + chat language, localized LINE strings. |
| **G5** | **Privacy-first AI use** | Redact before every AI call; only documented context reaches the model. | Redaction helpers + patient context builders per [privacy.md](privacy.md) / [llm-context.md](llm-context.md); logs avoid raw user text. |
| — | **Emergency handling** | Life‑threatening wording → **fixed** safety message, not a free-form AI medical opinion. | Emergency intent → template reply only. |
| — | **Voice** | Shipped in prototype; **Section 10** still skips formal voice performance bars until **OD-3** (**NG-1**). | LINE speech-to-text / optional text-to-speech; HTTP voice upload route. |

---

## 5. Target users and personas

### 5.1 Primary persona: Home medication manager

**Who:** Adults (40–75) managing their own chronic medications, or a caregiver managing a family member's regimen. Fluent in Traditional Chinese; may have basic English.

**What they need:** "When I'm unsure about my medications or forget whether I took a dose, I want to ask a quick question in LINE and get a plain-language answer — without switching apps or waiting for my next pharmacy visit."

**Key behaviors:**
- Uses LINE daily for family communication.
- Manages 2–6 chronic medications; the list changes occasionally.
- Forgets doses 1–3 times per week.
- Avoids English medical vocabulary; wants answers in conversational Chinese.

**Pain points:**
- Drug package inserts are written in clinical language.
- Pharmacy consultations are short; follow-up questions have no easy channel.
- Reminder apps feel like extra work to set up and maintain.

### 5.2 Secondary users: Doctors, institutions, API integrators

Aligned with **[`prd.md`](prd.md)** (“Who it’s for”): secondary users are **doctors**, **health care institutions**, and **teams integrating via the HTTP API**—not a second “chat patient” cohort for the LINE pilot, but audiences who benefit from or deliver the same core assistant.

**Doctors and clinical staff** — They may receive **visit-prep summaries** and structured med context from patients (exported from chat or via API). The assistant does **not** diagnose, prescribe, or change doses (**Section 9**); clinical decisions stay with licensed professionals.

**Health care institutions** — Hospitals, clinics, or programs that **pilot or embed** the product through integrations, partnerships, or future B2B2C paths (**Growth**, **OD-4**), subject to **OD-1** (Taiwan regulatory classification) and institutional agreements.

**API integrators** — Developers and vendor teams using **direct HTTP API** calls, scripts, tests, or mobile wrappers to run the same assistant pipeline as LINE—without forking behavior (**C-3**, **C-4**, **A-1**).

### 5.3 Anti-persona

Users expecting **emergency triage**, **dose optimization**, or a replacement for a pharmacist or physician. MedBuddy explicitly redirects these users to appropriate professional channels. Any message that signals a life-threatening situation gets a fixed safety response — not the assistant.

---

## 6. User journeys

### 6.1 Onboarding

The user opens or follows the LINE bot (or calls the onboarding API endpoint). The system greets them in the appropriate language: on LINE **follow**, **`patients.locale`** may be seeded from LINE’s user profile **`language`** (HTTP API) before the fixed welcome; on the reference app, **`GET /v1/app/me`** may sync locale from the device tag (**`X-MedBuddy-Locale`**) until onboarding is completed. The journey continues with preferred name, timezone, and disclaimer before medical content is emphasized.

**Success state:** The user is greeted by name, their language is set, and they have seen the disclaimer.

### 6.2 Building the medication list

The user describes a medication in natural language — name, dose, schedule, or any combination. The assistant extracts the details, summarizes them in plain language for confirmation, and optionally shares key drug information (what it's for, notable warnings) when registry data is available.

**Success state:** The medication appears in the user's list with correct details. The acknowledgment is grounded and specific — not a generic "saved."

### 6.3 Day-to-day question answering

The user types — or on LINE, sends a voice note — questions like "what is this medication for?", "can I take these two together?", "show me my medication list", or reports a vital sign. The assistant responds in plain language in the user's locale.

**Success state:** The user gets a clear, accurate, non-diagnostic answer. Off-topic requests (e.g., "diagnose this pain") receive a consistent, polite refusal and a referral prompt.

### 6.4 Adherence cycle

The system sends a scheduled reminder via LINE at the user's configured local time. The user replies to confirm they took their dose, or reports a miss.

**Success state:** Reminder delivered at the correct local time. The user's reply is recognized and recorded. Missed doses can be reported and are tracked.

### 6.5 Visit preparation

The user asks for a summary. The assistant produces a structured, doctor-ready document in the user's language: current medications, recent changes, any noted symptoms or vitals, and space for questions.

**Success state:** The summary is coherent, in the correct language, and contains no diagnosis language. The user can share it directly with a clinician.

---

## 7. Functional requirements

Full technical implementation details are in [`tdd-extended.md`](tdd-extended.md).

### 7.1 Channels

| # | Requirement | In pilot |
|---|-------------|----------|
| C-1 | LINE accepts text messages and, where configured, voice notes; the assistant responds with text and optionally a spoken reply | Yes |
| C-2 | When a user joins the LINE bot, the system creates their profile and sends a localized welcome with a disclaimer | Yes |
| C-3 | The HTTP API accepts a text message and returns a text reply, using the same assistant as LINE | Yes |
| C-4 | The HTTP API accepts a voice upload, transcribes it, runs the assistant, and returns the reply and transcript | Yes |
| C-5 | API endpoints for health check, user profile, onboarding, and summary are functional | Yes |
| C-6 | An internal endpoint allows a scheduled job to re-send any missed reminders | Yes |

### 7.2 Conversation and assistant behavior

| # | Requirement | In pilot |
|---|-------------|----------|
| A-1 | A single assistant pipeline handles all channels — LINE text, LINE voice, HTTP text, HTTP voice — with identical behavior for the same input | Yes |
| A-2 | Each user message is understood in the context of the recent conversation, so short follow-ups and references to earlier turns are handled naturally | Yes |
| A-3 | Supported intents: list medications, upcoming doses, add medication, remove medication, update medication, explain a medication, check interactions, confirm a dose, report a missed dose, report side effects, log a vital sign, request a summary, update profile (including language and timezone), emergency (life-threatening situation → fixed safety message, no AI involvement), general health question, off-topic refusal | Yes |
| A-4 | General questions and vital logging get a direct response without requiring drug data to be fetched first | Yes |
| A-5 | When a user adds a medication with a schedule, reminder preferences are extracted and used to create upcoming dose reminders | Yes |

### 7.3 Data

| # | Requirement | In pilot |
|---|-------------|----------|
| D-1 | User profiles, medications, conversation history, and dose events are stored persistently with appropriate access controls | Yes |
| D-2 | Drug reference information is cached to reduce repeated external lookups and AI costs | Yes |
| D-3 | The full application can run without any external services for local development and testing | Yes |

### 7.4 Reminders

| # | Requirement | In pilot |
|---|-------------|----------|
| R-1 | Adding or changing a medication rebuilds the user's upcoming dose reminders to match their preferences | Yes |
| R-2 | Reminders are delivered via LINE at the user's scheduled local time | Yes (when configured) |
| R-3 | When a user says they took a dose, the corresponding reminder is marked as taken | Yes |
| R-4 | When a user reports a missed dose, the most recent pending reminder is marked as missed | Yes |
| R-5 | Reminder messages are written in the user's language | Yes |

### 7.5 Language support

| # | Requirement | In pilot |
|---|-------------|----------|
| L-1 | All replies, reminders, and onboarding copy are available in Traditional Chinese (`zh-TW`) and English (`en`) | Yes |
| L-2 | Dose scheduling and reminder copy respect the user's timezone; default is Taipei time | Yes |
| L-3 | Users can change their language or timezone through a natural conversation | Yes |

### 7.6 Operations

| # | Requirement | In pilot |
|---|-------------|----------|
| O-1 | System activity is logged (intent, anonymized user reference, medication count) without recording the user's raw message text | Yes |
| O-2 | An automated test suite and a change log are maintained for all behavior-affecting changes | Yes |

---

## 8. Non-functional requirements

| # | Attribute | Requirement |
|---|-----------|-------------|
| N-1 | **Architecture** | Core business logic is decoupled from the AI provider and data store — either can be swapped without touching product behavior |
| N-2 | **Security** | LINE message authenticity is verified on every request. The internal reminder endpoint requires a shared secret. All credentials come from environment configuration — none hardcoded |
| N-3 | **Privacy** | Personal information is redacted before every AI call. The scope of what the AI can see is defined in [`privacy.md`](privacy.md) and not expanded without documentation |
| N-4 | **Deployability** | One-command local setup. One-click cloud deploy. Full demo mode available with no external credentials |
| N-5 | **Reliability** | A scheduled recovery job re-sends any reminders missed due to infrastructure restarts. Dose confirmation is idempotent |
| N-6 | **Latency** | Text replies target under 5 seconds for typical inputs. Best-effort for the prototype; no SLA commitment |
| N-7 | **Expectations** | This is a prototype suitable for small controlled pilots only. No uptime or performance guarantees |

### 8.1 Non-functional posture (response speed + always-on reliability)

To keep product and engineering aligned, architecture decisions are evaluated with response speed and always-on service reliability as first-priority outcomes:

| Lens | Product expectation | KPI used |
|---|---|---|
| **Response speed** | Answers stay fast at normal and peak traffic. | Assistant-turn latency (p95/p99), webhook ack latency, queue lag/age. |
| **Availability** | Core chat + reminder paths stay reachable during dependency issues. | API uptime, reminder delivery success %, SLO burn rate. |
| **Reliability** | Failures recover automatically without duplicate or dropped reminders. | Reconcile recovery coverage, retry success %, idempotency error rate. |
| **Optimization (supporting)** | Efficiency work supports speed/reliability but does not replace them as goals. | Cache hit rate, LLM calls per turn (diagnostic). |

Decision reviews and pilot retrospectives should record all four fields for major changes:

1. **Decision** — what architecture or product behavior changed.
2. **Impact** — which lens is expected to improve.
3. **Metric** — what measurable KPI confirms improvement.
4. **Guardrail** — fallback/degradation behavior when dependencies fail.

---

## 9. Out of scope

| # | Item | Why |
|---|------|-----|
| NG-1 | **Formal voice metrics** as pilot pass/fail (transcription accuracy, reply voice quality, latency, **cost per voice turn**) | Typing and voice are **live** in deployment; **Section 10** sign-off does **not** require those bars until product defines them (**OD-3**) |
| NG-2 | Clinical diagnosis or prescribing guidance | Regulatory and liability boundary; the assistant is explicitly designed to avoid this |
| NG-3 | Taiwan drug authority (TFDA) live data | US drug registry (OpenFDA) is the primary data source for the pilot |
| NG-4 | Rich interactive message formats (buttons, carousels) | All reminders and interactions are plain text in v1 |
| NG-5 | Push notifications for non-LINE users | Reminders are LINE-only in current scope |
| NG-6 | Mobile app as a co-equal validated channel | The mobile app is a reference implementation; see [`frontend-expo.md`](frontend-expo.md) |
| NG-7 | Regulatory clearance (HIPAA, TFDA, MDR, etc.) | Any real-world clinical deployment requires separate legal and clinical review |
| NG-8 | Per-user authentication for the HTTP API | A shared access token is sufficient for a controlled pilot; per-user auth is a Growth-phase item |

---

## 10. Success metrics

We score the pilot **when it ends**, using the table below. **Owners:** product + ops. For **G2**, lock the **drug/intent sample and review method** before the first pilot user.

**Explicitly not required to “pass” this pilot:** targets for transcription accuracy, synthetic voice quality, word-error rate, or **cost per voice user**—even if many people use voice (**NG-1**).

| Goal | Metric | Target | Conditions for calling it “met” |
|------|--------|--------|-----------------------------------|
| G1 — Reliable list | No data-loss incidents; add/remove flows covered by automated tests | 100% test pass; 0 incidents | CI on **`main`** green (tests + repo workflow). Pilot: zero data-loss for enrolled users; anomalies documented. |
| G2 — Understandable answers | Sample dialogs; no diagnosis language; reference data used for common queries | Reviewer sign-off; ≥ 80% reference-grounded explain/interaction turns | Review [use-cases.md](use-cases.md) or pilot exports. On an **agreed** drug/intent set, **≥ 80%** of explain+interaction turns show registry grounding in logs; method documented. |
| G3 — Adherence | Reminder delivery in staging; human end-to-end cycle | ≥ 95% delivery; one full add → remind → confirm | Over an agreed window, **≥ 95%** of **due** reminders become successful LINE pushes when queue, worker, and LINE access are healthy (exclude planned downtime). At least **one** real **add → schedule → push → confirm** with a human. |
| G4 — Bilingual | Native validation; language switch | Native speaker sign-off on both | **zh-TW** and **en** in onboarding, errors, reminders, summary; mid-session language switch verified. |
| G5 — Privacy | Audit of AI inputs | 0 violations in a 20-turn audit | **20** turns sampled; inputs checked per [llm-context.md](llm-context.md)—**0** breaches of [privacy.md](privacy.md). |

---

## 11. Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation (product / process) | How the current build addresses it *(see [`tdd-extended.md`](tdd-extended.md))* |
|---|------|------------|--------|------------------------------|----------------------------------------------------------------------------------|
| R-1 | AI produces diagnosis language or unsafe advice | Medium | High | Strict persona guardrails; qualitative review before pilot | Localized persona + intent rules; life‑threatening messages → **fixed** template only (no generative body). Details: [tdd-extended.md](tdd-extended.md). |
| R-2 | Drug registry returns no data for a medication | High | Low | Graceful answer without registry; record the gap | Model-only fallback; logs/cache show whether data came from registry or model. |
| R-3 | Reminder delivery fails due to infrastructure | Medium | Medium | Recovery job re-enqueues periodically | Internal reconcile endpoint + queued jobs + idempotent “sent” marking; optional nudges. |
| R-4 | Personal info in free text reaches the AI | Medium | High | Redact every message; residual risk in [privacy.md](privacy.md) | Redaction + patient context builder omit sensitive fields per privacy spec. |
| R-5 | LINE delivery times out | Low | Medium | Acknowledge fast; send reply when ready | LINE webhook returns quickly; reply is sent after processing. |
| R-6 | Pilot users mistake product for a certified medical device | Medium | High | Disclaimers everywhere; internal trial policy | Disclaimer on join; reminder/summary copy; org policy—not only code. |

---

## 12. Assumptions and dependencies

### Assumptions

- Pilot users can use **text or voice** in LINE (when enabled) and have an active LINE account.
- The US drug registry (OpenFDA) provides adequate coverage for the medications in the pilot cohort; the Taiwan drug authority (TFDA) is not required for initial validation.
- Cloud infrastructure (database, job queue) is available in the pilot environment; local mock mode is for development and CI only.
- Taipei timezone covers the majority of the pilot cohort.

### External dependencies

| Dependency | Risk if unavailable |
|------------|---------------------|
| LINE Messaging API | Primary channel unavailable |
| AI provider (Gemini or OpenAI) | All assistant responses fail |
| Database (Supabase / Postgres) | Persistence unavailable; fallback to in-memory mock for dev only |
| Job queue (Redis) | Reminder delivery disabled; recovery job becomes a no-op |
| Drug registry (OpenFDA) | Drug grounding unavailable; AI-only replies |

---

## 13. Open decisions

| ID | Question | Owner | When needed | Notes |
|----|----------|-------|-------------|-------|
| OD-1 | Regulatory classification for Taiwan: general wellness app vs. regulated software | Legal / Product | Before Growth phase | Determines what the product can claim and whether TFDA registration is required. Also the gate for all T3 features and T2 B2B2C contracts. |
| OD-2 | Long-term identity model for HTTP API users | Engineering | Growth phase | Options include per-user tokens, OAuth, or device attestation. Gate for T2.3 API hardening. |
| OD-3 | Criteria to promote voice from "implemented" to a fully supported, signed-off product feature | Product | Growth phase | Requires accuracy targets, cost model, failure fallback behavior, and updated PRD acceptance criteria. Gate for T3.5 (voice-first / smart-speaker). |
| OD-4 | Clinician-facing summary formats for institutional partners | Product | Growth phase | Depends on whether a clinical partner enters the pilot. T2.1 (clinician summary handoff) builds directly on this decision. |
| OD-5 | Data residency requirements for Taiwan regulations and future markets | Legal | Before international expansion | Relevant for the Global phase and required before T3.1 (NHI PharmaCloud) and T3.3 (channel expansion). |

### Feature-tier trigger signals (complement to open decisions)

Each tier of future feature directions has explicit pilot-phase signals that must be observed before building. These are not timelines — they are evidence gates.

| Tier | Signal required to unlock |
|------|--------------------------|
| **T1 — Adjacent depth** | Pilot exit criteria met (≥95% reminder delivery, ≥80% grounded Q&A, 0 data-loss, 0 privacy violations). Each T1 feature additionally has its own named signal (e.g. ≥30% of users mention a family member at onboarding → T1.1; ≥20% funnel drop-off at "build the list" → T1.2). |
| **T2 — Platform & B2B2C** | First paying clinic, pharmacy chain, or pharma partner LOI. OD-1 and OD-2 resolved. |
| **T3 — Frontier bets** | OD-1 and OD-5 resolved. Series A funding secured. T3-specific sub-gates listed per feature (e.g. NHI pilot program for T3.1; clean adherence delta measurable from T1.5 + T2.2 for T3.2; psychiatry clinic partner + clinical advisor sign-off for T3.4). |

---

## 14. Phased roadmap

Each phase ends with an explicit **go / no-go** against exit criteria before spending on the next horizon. Prototype completed in **April 2026**; MVP + Taiwan pilot are in flight with a target pilot-exit window around **Q3 2026**. Later phases remain gate-based.

**Sequencing rationale (aligned with [`prd.md`](prd.md))**

1. **Prototype** — **Time-boxed** de-risking of the hardest integration slice (e.g. LINE + assistant + thin persistence) before committing to full MVP + pilot execution. Cheap **no-go** if the stack or scope is wrong.
2. **MVP + Taiwan Pilot** — Follows only a **go** from Prototype: live infra, pilot **Section 7** intents, **Section 10** metrics (**NG-1** still exempts formal voice SLAs), bilingual UX, and governance. Validates **add → remind → confirm** with real users at small **N**.
3. **Growth (Japan-first)** — Assumes MVP pilot exit under **Section 10** and clearer **OD-1**: harden **voice** (**OD-3**), retention, cost/latency, API identity (**OD-2**), and regional drug data—**without** global regulatory or residency promises.
4. **Regional / Global** — Only after **Growth** evidence and **legal/clinical** sign-off: **OD-5**, **OD-4**, and multi-region posture. This is a direction, not a worldwide launch commitment.

| Phase | Horizon | Purpose |
|-------|---------|---------|
| **Prototype** | **Completed (Apr 2026)** | Fast **time-box** slice completed; outcome was a go decision for MVP. |
| **MVP + Taiwan Pilot** | **In flight (~Q3 2026 pilot-exit target)** | Controlled pilot with **text and voice** on LINE; live database, reminders, governance, **Section 10** metrics (**NG-1** still excludes formal voice bars). |
| **Growth (Japan-first)** | **Post-pilot gate** | Hardening and scale after pilot exit, OD-1 clarity, and cost/MAU proof; not full regulatory product claims. |
| **Regional / Global** | **Post-growth, gate-based** | Multi-market expansion only after **Growth** results and **legal/clinical** review. |

---

### Phase 1: Prototype

**Objective:** De-risk the core loop under a fixed time-box. Scope must be **pre-negotiated** so the team does not attempt full **Section 7** coverage in one short prototype cycle.

| Theme | Exit criteria (end of prototype cycle) |
|-------|------------------------------|
| **Slice** | At least one path works end-to-end in a **defined** environment (e.g. mock or staging): user message → assistant reply → optional persistence sanity check |
| **Channel** | If LINE is in scope: webhook receives and responds OR documented blocker with owner |
| **Decision** | Written **go / no-go** for MVP: agree MVP scope, owners, and start date; or pivot/stop |
| **Honesty** | No marketing or patient promises beyond what was actually demoed |

**Go criteria:** Stakeholders agree the prototype met its **predefined** success checks; MVP + pilot phase is formally chartered.

---

### Phase 2: MVP + Taiwan Pilot

**Objective:** A credible medication companion on LINE and the HTTP API, with a small controlled pilot using **text and voice** (same assistant after speech-to-text) — honest disclaimers and a stable set of user intents. **Section 10** still omits formal voice **service levels** (**NG-1**).

| Theme | Exit criteria |
|-------|--------------|
| Core conversational experience | All supported intents work reliably **from typed and spoken input** where voice is on. Onboarding, profile updates, and language switching work on a live database. Errors show clear user-facing messages |
| Drug information | Drug registry lookups work reliably for common medications. Results are visible in logs without exposing personal information |
| Reminders | Text reminders proven in at least one staging environment. Chat-based dose confirmation validated with a real tester. Recovery job tested after a simulated outage |
| Quality | Automated tests fully passing. Deployment and scheduled-job runbooks documented. Pilot feedback captured |
| Governance | Disclaimer visible at onboarding and in summaries. Internal policy defining who may join the trial. No external claims that this is a "medical product" |

**Go criteria:** Pilot cohort completes add → remind → confirm without data loss. Team confirms **Section 10** was applied—including **NG-1** (no pass/fail on transcription accuracy, synthetic voice quality, or voice cost yet).

---

### Phase 3: Growth (Japan-first)

**Objective:** Move from “works in a pilot” toward “could serve a broader audience” — without claiming regulatory readiness.

| Theme | Goals |
|-------|-------|
| **Voice (hardening)** | Voice is already **live**; Growth adds **agreed targets** (accuracy, fallbacks like “please type”), cost/latency budgets, and updates **Section 10** (**OD-3**) |
| **Retention and adherence** | Users can adjust reminder preferences conversationally. Richer adherence history. Caregiver read-only summaries (requires policy review — **T1.1**) |
| **Regional drug data** | Taiwan drug registry or equivalent where legally and technically viable. Improved data caching strategy |
| **Mobile** | Reference mobile app hardened beyond prototype: stronger auth, cost controls, optional local notifications if the product expands beyond LINE |
| **Operations** | Cost and latency targets per AI call. Basic product analytics (active users, intent breakdown). Incident response playbook. Content safety review loop for new prompts |
| **T1 features (if pilot-signal met)** | Adjacent-depth features that earned their trigger: blister-pack photo recognition (**T1.2**), missed-dose pattern reflection (**T1.5**), vitals trend deltas (**T1.6**). Each requires its named pilot signal before scoping. |
| **T2 features (if first LOI signed)** | Clinician summary handoff (**T2.1**), pharma-sponsored PSP overlay (**T2.2**), API hardening for integrators (**T2.3**). OD-1 and OD-2 must resolve before B2B2C contracts are signed. |

**Go criteria:** Monthly cost per active user modeled and acceptable (targeting **< US$0.05 / MAU / month at MVP-level operation** and **< US$0.02 at Growth maturity** as caching/ops improve). Any promoted voice feature meets an agreed error-rate threshold. Compliance review roadmap in place before moving past informal pilots.

---

### Phase 4: Regional / Global

**Objective:** Only pursue after **Growth** validates demand and **legal / clinical** review clears the path. Regional/global expansion is a later-stage planning horizon, not a commitment to launch.

| Theme | Direction |
|-------|-----------|
| **Markets** | Multi-region deployment with data residency options. Additional languages based on market research. **Mainland China is excluded from this roadmap and treated as a separate product/JV decision.** |
| **Compliance** | Regulatory classification per country. Privacy impact assessments if handling health data at scale |
| **Ecosystem** | Export formats compatible with electronic medical records. Institutional pilots. Optional B2B packaging |
| **UX** | Native apps and richer LINE interfaces as primary channels. Accessibility standards |
| **T3 features (if gates cleared)** | NHI PharmaCloud / My Health Bank import (**T3.1**, Taiwan moat — requires OD-1 + OD-5 + HPA pilot program); insurer / NHI value-based adherence contracts (**T3.2** — requires measurable adherence delta from T1.5 + T2.2); KakaoTalk and WhatsApp channel expansion (**T3.3** — requires Series A + country drug-data source); voice-first elderly / smart-speaker bridge (**T3.5** — requires OD-3 closed + Japan launch readiness). Psychiatric specialty (**T3.4**) and RWD aggregates (**T3.6**) are separately gated by clinical sign-off and ethics board respectively — see feature-directions companion. |

> **Guardrail:** "Global" describes a capability direction, not a committed worldwide launch. T3 features are options that open when regulatory and market conditions are met — not a committed feature set. Mainland China remains a separate product path because it requires a distinct channel/regulatory stack (for example WeChat delivery, approved domestic LLMs, and on-shore compliance posture).

---

## 15. Related documentation

| Document | Purpose |
|----------|---------|
| [`prd.md`](prd.md) | Short PRD (~2–3 pages) — executive / partner summary |
| [`features.md`](features.md) | Capability catalog — product and engineering alignment on each feature, including future feature directions (T1/T2/T3) |
| [`use-cases.md`](use-cases.md) | Narrated flows and example user conversations |
| [`tdd.md`](tdd.md) | Condensed Technical Design Document (~2–3 pages): architecture diagrams and rationale |
| [`tdd-extended.md`](tdd-extended.md) | Full technical design — API contracts, data schema, system internals |
| [`reminders.md`](reminders.md) | Dose reminder scheduling and delivery details |
| [`privacy.md`](privacy.md) | Personal information handling and AI context boundaries |
| [`frontend-expo.md`](frontend-expo.md) | Reference mobile client — screens, mock mode, and limitations |
| [`../README.md`](../README.md) | Repository overview and quick-start guide |
