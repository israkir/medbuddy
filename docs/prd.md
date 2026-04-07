# MedBuddy — Product Requirements Document

## Table of contents

1. [Introduction](#1-introduction)
2. [Prototype scope and boundaries](#2-prototype-scope-and-boundaries)
3. [Problem statement](#3-problem-statement)
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

MedBuddy is a **patient-facing medication companion** that helps people remember what they take, understand their medications in plain language, flag potential interaction concerns, and support adherence — delivered through **LINE Messaging** (the dominant chat platform in Taiwan) and a shared **HTTP API** for integrations and future clients.

The current phase is a **text-only prototype** targeting a small controlled pilot on LINE. Success means completing the add / list / remind / confirm adherence cycle reliably for a real cohort, with honest safety disclaimers and bilingual (Traditional Chinese / English) support, before expanding modality or scale.

---

## 2. Prototype scope and boundaries

The prototype validates **text-in, text-out** conversational interactions only. This scope boundary is intentional: lower cost to test, easier safety-copy review, and a clear ceiling for what "works" before adding STT/TTS failure modes and latency.

| Dimension | In prototype scope | Out of prototype scope |
|-----------|--------------------|------------------------|
| **LINE** | Text messages → assistant → text replies. Dose reminder push is text only. | Voice notes, STT/TTS as supported user journeys (engineering exploration only). |
| **HTTP API** | `POST /v1/app/messages` with text body; same assistant core as LINE. | Voice upload, streaming, real-time audio. |
| **Feature set** | Closed set in §7: list/add/remove meds, explain, interaction check, confirm dose, profile/locale, health summary, general Q&A, off-topic refusal. | Open-domain "do anything" assistant behavior. |
| **Mobile client** | HTTP API is callable by integrations and the reference Expo app. | Expo app as a co-equal validated channel. |

> **Engineering note:** Repository code paths for LINE audio (Google Speech-to-Text / TTS) may exist for experimentation. Product acceptance for the prototype is defined on **text paths only** until a future phase explicitly promotes voice.

---

## 3. Problem statement

Patients managing chronic medications in Taiwan and similar markets face three persistent gaps:

1. **Mental model fragmentation** — people struggle to maintain an accurate, up-to-date picture of what they take, when, and why, particularly when managing medications for a family member or across multiple prescribers.

2. **Adherence without friction** — reminder tools are either too intrusive (standalone apps requiring behavior change) or too passive (paper instructions). Most patients already use LINE daily; a medication companion inside that familiar channel removes the adoption barrier.

3. **Language and information asymmetry** — most drug-reference tools are English-only or use clinical language that is inaccessible to patients. Pharmacy consultations are short; patients leave without plain-language answers to follow-up questions.

Existing tools are app-centric, English-only, or disconnected from conversational channels already embedded in daily life in Taiwan.

---

## 4. Strategic goals

Goals are ordered by priority. Each has a measurable acceptance criterion for the prototype phase.

| ID | Goal | Prototype acceptance criterion |
|----|------|-------------------------------|
| **G1** | **Reliable medication list** via natural text | Add/list/remove flows persist correctly end-to-end. Test suite covers all CRUD paths. Zero data-loss incidents in pilot cohort. |
| **G2** | **Understandable drug answers** | Explain and interaction-check responses are grounded in registry data (OpenFDA) where available. Responses contain no diagnosis language. Qualitative review confirms plain-language readability. |
| **G3** | **Adherence support on LINE (text)** | Dose events materialize after a medication is added. Text reminders deliver. User can confirm a dose by typing; confirmation is recorded. |
| **G4** | **Bilingual experience** | User locale (`en`, `zh-TW`) drives all replies, reminders, and onboarding. Locale can be changed via conversation. Both locales are validated by a native speaker in the pilot. |
| **G5** | **Privacy-aware LLM use** | Pattern-based PII redaction applied before every LLM call. Patient context sent to LLM is de-identified (no raw name, exact age, health notes). Documented in `privacy.md`; no undocumented expansion of LLM context. |

---

## 5. Target users and personas

### 5.1 Primary persona: Home medication manager

**Who:** Adults (40–75) managing their own chronic medications, or a caregiver managing a family member's regimen. Fluent in Traditional Chinese; may have basic English.

**Job to be done:** "When I'm unsure about my medications or forget whether I took a dose, I want to ask a quick question in LINE and get a plain-language answer or confirmation — without switching apps or waiting for my next pharmacy visit."

**Key behaviors:**
- Uses LINE daily for family communication.
- Has 2–6 chronic medications; list changes occasionally.
- Forgets doses 1–3 times per week.
- Avoids English medical vocabulary; wants answers in conversational Chinese.

**Pain points:**
- Drug inserts are printed in clinical language.
- Pharmacy consultations are short; follow-up questions have no easy channel.
- Reminder apps feel like extra work to set up and maintain.

### 5.2 Secondary persona: API integrator

**Who:** Engineers or clinical partners calling `/v1/app/*` directly (scripts, integrations, or the reference Expo app) with a stable user ID.

**Job to be done:** "I need to embed the same medication assistant core into my integration or test environment without depending on LINE."

### 5.3 Anti-persona

Users expecting **emergency triage**, **dose calculation optimization**, or a replacement for a pharmacist or physician. All messaging must redirect these users to appropriate professional channels.

---

## 6. User journeys

### 6.1 Onboarding

User follows or opens the LINE bot (or calls `/v1/app/onboarding`). System greets in the detected locale and prompts for a preferred name and optional timezone. Profile is saved. Disclaimer is displayed.

**Success state:** User is greeted by name, locale is set, and disclaimer is visible before any medical content.

### 6.2 Building the medication list

User types a medication name (and optional dosage, schedule) in natural language. System extracts the structured details, confirms with the user in plain language, and optionally surfaces basic drug reference information (indication, key warnings) when registry data is available.

**Success state:** Medication appears in the user's list with correct name, dosage, and schedule. User receives a grounded acknowledgment, not a generic "saved."

### 6.3 Day-to-day question answering

User types questions like "what is this medication for?", "can I take these two together?", "show me my medication list", or logs a vital sign. System responds with de-identified, registry-grounded answers where available, and clearly signals when professional advice is needed.

**Success state:** User receives a plain-language, accurate, non-diagnostic answer. Off-topic requests (e.g. "diagnose my pain") receive a consistent refusal with a referral prompt.

### 6.4 Adherence cycle

System sends a scheduled **text** reminder via LINE push at the user's configured local time. User replies "I took it" or similar phrasing. System confirms the dose was recorded.

**Success state:** Reminder delivered at the correct local time. User's typed confirmation is recognized and recorded. Missed doses can be reported.

### 6.5 Visit preparation

User requests a summary. System produces a structured, doctor-ready summary in the user's locale: medications, recent changes, any noted symptoms or vitals, and a space for questions.

**Success state:** Summary is coherent, bilingual-ready, and contains no diagnosis language. Suitable for the user to share with a clinician.

---

## 7. Functional requirements

Requirements are feature-level. Implementation details are in [`tdd.md`](tdd.md).

### 7.1 Channels

| ID | Requirement | Prototype |
|----|-------------|-----------|
| C-1 | LINE webhook accepts verified text message events; assistant processes and replies with text. | Yes |
| C-2 | LINE follow event creates a user record and sends a localized welcome message with disclaimer. | Yes |
| C-3 | HTTP `POST /messages` accepts a text body, runs the same assistant pipeline as LINE, and returns a text reply. | Yes |
| C-4 | HTTP endpoints for health check, user profile (`/me`), onboarding, and summary are documented and functional. | Yes |
| C-5 | Internal reminder reconcile endpoint allows a cron job to re-enqueue missed reminder deliveries. | Yes |
| C-6 | LINE audio message → STT → assistant → optional TTS reply. | **No** — engineering exploratory only. |

### 7.2 Conversation and intent handling

| ID | Requirement | Prototype |
|----|-------------|-----------|
| A-1 | A single assistant pipeline handles both LINE text and HTTP text with identical behavior. | Yes |
| A-2 | Each user turn is classified into a structured intent with adherence fields before tool dispatch. Recent (redacted) conversation history informs classification for short follow-ups. | Yes |
| A-3 | The following intents are supported: list medications, add medication, remove medication, update medication, explain medication, check interactions, confirm dose, report missed dose, report side effects, log vital, request summary, update profile (including locale and timezone), general question, off-topic. | Yes |
| A-4 | General questions and vital logging produce a composed reply without mandatory drug data prefetch. | Yes |
| A-5 | When a medication is added, reminder preferences extracted from the user's message drive dose event creation. | Yes |

### 7.3 Data and persistence

| ID | Requirement | Prototype |
|----|-------------|-----------|
| D-1 | User profiles, medications, conversation history, drug cache, and dose events persist in Supabase (Postgres) with row-level security. | Yes |
| D-2 | A shared drug reference cache (OpenFDA-backed) and a per-patient personalized reply cache reduce repeated external calls and LLM costs. | Yes |
| D-3 | When Supabase is not configured, in-memory mocks allow the full application to run for local development and CI without external keys. | Yes |

### 7.4 Reminders

| ID | Requirement | Prototype |
|----|-------------|-----------|
| R-1 | Adding or removing a medication rebuilds upcoming dose events according to user preferences and system defaults. | Yes |
| R-2 | A background worker delivers text LINE reminders at the scheduled local time using deferred job queuing (Redis). | Yes (when Redis configured) |
| R-3 | When a user's typed message indicates they took a dose, the pending dose event is marked as taken. | Yes |
| R-4 | Missed dose reporting marks the most recent pending dose event as missed. | Yes |
| R-5 | Reminder text respects the user's locale. | Yes |

### 7.5 Localization

| ID | Requirement | Prototype |
|----|-------------|-----------|
| L-1 | Backend supports `zh-TW` and `en` locales. Per-user locale overrides the server default. | Yes |
| L-2 | User timezone (IANA string) drives dose scheduling and reminder message copy. Default is `Asia/Taipei`. | Yes |
| L-3 | User can change their locale and timezone through a conversational update. | Yes |

### 7.6 Operations

| ID | Requirement | Prototype |
|----|-------------|-----------|
| O-1 | Structured logs record assistant activity (intent, user key, medication count) without raw user message text. | Yes |
| O-2 | CI checks, Makefile targets, and a CHANGELOG are maintained for all behavior-affecting changes. | Yes |

---

## 8. Non-functional requirements

| ID | Attribute | Requirement | Prototype target |
|----|-----------|-------------|-----------------|
| N-1 | **Architecture** | Hexagonal ports/adapters; swappable LLM provider and storage without touching business logic. | Enforced via protocol interfaces; documented in `tdd.md`. |
| N-2 | **Security** | LINE signature verification in real mode. Internal cron endpoint protected by a shared secret. Secrets loaded from environment only, never from code. | No known bypasses. Documented auth model. |
| N-3 | **Privacy** | PII redaction applied before every external LLM call. Patient context sent to LLM must not exceed documented de-identification boundaries. | See `privacy.md`. |
| N-4 | **Deployability** | Docker + Compose for local. Render blueprint for cloud. Mock mode available for demos without any API keys. | One-command local start; one-click Render deploy. |
| N-5 | **Reliability** | Reconcile endpoint mitigates missed reminder jobs after Redis/worker restarts. Adherence marking is idempotent. | Reconcile demonstrated in staging. |
| N-6 | **Latency** | Assistant text turn responds within 5 seconds at p90 for typical inputs. | Best-effort for prototype; no SLA commitment. |
| N-7 | **Expectations** | No SLA commitments for prototype. Suitable for small controlled pilots only. | Documented explicitly. |

---

## 9. Out of scope

| ID | Item | Rationale |
|----|------|-----------|
| NG-1 | Voice as part of prototype acceptance | STT/TTS may exist in code; prototype sign-off is text-only (§2). |
| NG-2 | Clinical diagnosis or prescribing guidance | Regulatory and liability boundary; prompts enforce this. |
| NG-3 | TFDA live API integration | Stub until a real client; OpenFDA is the primary registry today. |
| NG-4 | Rich LINE Flex messages or postback "mark taken" | Reminders are plain text; adherence is chat-text only in v1. |
| NG-5 | Local push notifications for standalone HTTP users | LINE-only reminder delivery in current scope. |
| NG-6 | Expo app as a co-equal validated channel | Reference / future; see `frontend-expo.md`. |
| NG-7 | Production regulatory clearance (HIPAA, TFDA, MDR) | Any real-world clinical deployment needs separate legal and clinical review. |
| NG-8 | Per-user authentication beyond shared bearer token | Shared bearer token is sufficient for a controlled pilot; per-user auth is a Growth-phase item. |

---

## 10. Success metrics

Prototype success is judged against these criteria at pilot conclusion.

| Goal | Metric | Target |
|------|--------|--------|
| G1 — Reliable list | Zero data-loss incidents across pilot cohort. Add/remove round-trip covered by automated tests. | 100% test pass rate; 0 production data-loss reports. |
| G2 — Understandable answers | Qualitative review: sample text dialogs in `use-cases.md` contain no diagnosis language. OpenFDA grounding fires for ≥ 80% of explain/interaction queries for common drugs. | Reviewer sign-off on sample set. |
| G3 — Adherence support | Reminder delivery success rate in staging environment. At least one full add → remind → confirm cycle validated with a tester. | ≥ 95% delivery on staging. End-to-end cycle validated. |
| G4 — Bilingual | Both `zh-TW` and `en` locales validated by a native speaker. Locale can be switched mid-conversation. | Native speaker sign-off on both locales. |
| G5 — Privacy | No raw PII fields observed in LLM prompts during audit of 20 sample turns. | 0 violations in audit. |

**Explicitly not required for prototype:** voice success rate, word error rate (WER), TTS quality, multimodal analytics, cost-per-user.

---

## 11. Risks and mitigations

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|------------|--------|------------|
| R-1 | LLM produces diagnosis language or unsafe medical advice | Medium | High | System persona prompt enforces non-diagnostic framing; qualitative review before pilot. |
| R-2 | OpenFDA data unavailable or returns no results for a drug | High | Low | System degrades gracefully: LLM-only reply without registry grounding; `llm_meta.source` records the gap. |
| R-3 | Redis/worker failure causes missed reminders | Medium | Medium | Reconcile endpoint re-enqueues due reminders on cron schedule (15–60 min). |
| R-4 | PII leakage to LLM via free-text user messages | Medium | High | Pattern-based redaction applied; system prompt instructs model on masked content. Residual risk documented in `privacy.md`. |
| R-5 | LINE webhook delivery failure or timeouts | Low | Medium | LINE requires a 200 ACK immediately; reply is async after ACK. Retry by LINE platform on failure. |
| R-6 | Pilot cohort misunderstands prototype as a medical device | Medium | High | Disclaimer in onboarding, reminder messages, and summary responses. Internal policy for who may use the trial. |

---

## 12. Assumptions and dependencies

### Assumptions

- Users are comfortable typing in LINE and have an active LINE account.
- OpenFDA provides sufficient coverage for the common drugs in the pilot cohort; TFDA is not required for initial validation.
- Supabase and Redis are available in the pilot environment; in-memory mocks are only for CI and demo.
- A single timezone (`Asia/Taipei`) covers the majority of the pilot cohort.

### External dependencies

| Dependency | Owner | Risk if unavailable |
|------------|-------|---------------------|
| LINE Messaging API | LINE Corporation | Primary channel unavailable |
| LLM provider (Gemini or OpenAI) | Google / OpenAI | All assistant turns fail |
| Supabase (Postgres) | Supabase | Persistence unavailable; fallback to in-memory mocks only in dev |
| Redis + arq | Self-managed / Render Key Value | Reminder delivery disabled; reconcile path degrades to no-op |
| OpenFDA HTTP API | FDA | Drug grounding unavailable; LLM-only replies |

---

## 13. Open decisions

| ID | Decision | Owner | Due | Notes |
|----|----------|-------|-----|-------|
| OD-1 | Regulatory classification: general wellness vs regulated software for Taiwan market | Legal / Product | Before Growth phase | Determines what claims copy can say and whether TFDA registration is required. |
| OD-2 | Long-term identity model for HTTP API users (beyond shared bearer token) | Engineering | Growth phase | Options: per-user JWT, OAuth, device attestation. |
| OD-3 | Criteria to promote LINE audio from "engineering exploratory" to a supported product feature | Product | Growth phase | Requires accuracy target, cost model, fallback behavior, and updated PRD. |
| OD-4 | Institution-specific summary formats for clinical partnerships | Product | Growth phase | Depends on whether any clinical partner enters the pilot. |
| OD-5 | Data residency requirements for Taiwan regulations | Legal | Before any international expansion | Relevant for Global phase. |

---

## 14. Phased roadmap

Horizons are product intent, not guarantees. Each phase requires an explicit go/no-go decision against its exit criteria before the next phase begins.

### 14.1 Prototype → MVP (0–3 months)

**Objective:** A credible, text-only medication companion on LINE + HTTP for a small controlled pilot, with a frozen intent surface and honest disclaimers.

| Theme | Exit criteria |
|-------|--------------|
| **Core text UX** | All §7 intents stable. Onboarding, profile update, locale/timezone all validated on real Supabase. Clear failure messages for all error states. |
| **Drug grounding** | OpenFDA path reliable for common queries. Reference and personalization caches observable in logs (no PII). |
| **Reminders** | Text reminders proven in one staging/pilot environment. Chat-based adherence confirmation validated with testers. Reconcile endpoint tested after a simulated worker restart. |
| **Quality** | Test suite fully green. Runbooks for deploy and cron documented. Pilot feedback captured (form or structured interviews). |
| **Governance** | Disclaimer visible at onboarding and in summaries. Internal policy defining who may participate in the trial. No external marketing as a "medical product." |

**Go criteria:** Pilot cohort completes add/list/reminder/confirm cycle without data loss. Team signs off that text-only scope is what was tested.

### 14.2 MVP → Growth (3–12 months)

**Objective:** Move from "works in a pilot" toward "could serve a wider audience" — without claiming full regulatory readiness.

| Theme | Goals |
|-------|-------|
| **Voice (conditional)** | If demand is clear: promote LINE audio to a supported feature with STT/TTS SLAs, failure fallbacks ("please type or retry"), and updated PRD acceptance criteria. |
| **Retention and adherence** | Conversational adjustment of reminder preferences. Richer adherence history view. Consider caregiver-facing read-only summaries (policy review required). |
| **Regional data** | TFDA or additional registries where legally and technically viable. Improved caching strategy. |
| **Mobile** | Reference Expo app beyond prototype: auth model hardened, cost controls, optional local notifications if the product strategy extends beyond LINE. |
| **Operability** | Cost and latency budgets per LLM call. Basic product analytics (active users, intent distribution). Incident response playbook. Content safety review loop for new prompts. |

**Go criteria:** Repeatable monthly cost per active user modeled. Any promoted voice feature meets an agreed error-rate threshold. Compliance review roadmap in place if moving past informal pilots.

### 14.3 Growth → Global (12+ months)

**Objective:** Only pursue after Growth indicates demand **and** after legal/clinical review — not implied by the prototype.

| Theme | Direction |
|-------|-----------|
| **Markets** | Multi-region deploy with data residency options. Additional languages driven by market research. |
| **Compliance** | Deliberate classification per country (wellness vs regulated software). DPIA / HIPAA / comparable workflows if handling PHI at scale. |
| **Ecosystem** | EMR-friendly export formats. Institutional pilots. Optional B2B packaging. |
| **UX** | Native apps and/or rich LINE UI as primary channels. Accessibility standards (WCAG-aware). |

> **Guardrail:** "Global" describes a capability direction, not a committed worldwide launch.

---

## 15. Related documentation

| Document | Purpose |
|----------|---------|
| [`features.md`](features.md) | Capability catalog — product/engineering alignment on each feature. |
| [`use-cases.md`](use-cases.md) | Narrated flows and example utterances. |
| [`tdd.md`](tdd.md) | Technical design, API reference, data model, deployment topology. |
| [`reminders.md`](reminders.md) | Dose reminder operations and scheduling detail. |
| [`privacy.md`](privacy.md) | PII redaction scope and LLM context boundaries. |
| [`llm-context.md`](llm-context.md) | What is and is not sent to the LLM. |
| [`frontend-expo.md`](frontend-expo.md) | Reference Expo client — screens, mock mode, and limitations. |
| [`../README.md`](../README.md) | Repo overview and quick-start guide. |
