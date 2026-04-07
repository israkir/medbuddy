# MedBuddy — Product Requirements Document (PRD)

**Version:** 1.1 (prototype-aligned, 2026-04)  
**Status:** **Software prototype** — not a medical device, not for clinical decision-making, not production-grade healthcare software without separate compliance work.  
**Owner:** Product + engineering (monorepo: `apps/backend`, optional `apps/frontend`)

---

## Disclaimer

MedBuddy is a **software prototype**. It is **not** a substitute for professional medical advice, diagnosis, or treatment. All copy, prompts, and UX must preserve this boundary. **No warranty** of outcomes, availability, or regulatory fit is implied by this document.

---

## Prototype scope: text-only interactions and bounded features

This PRD treats the **product prototype** as **text in, text out** for all **conversational** interactions. That keeps validation focused: **`interpret_user_turn`** (intent + adherence slots), tool dispatch, persistence, and safety copy — without multimodal variance.

| Dimension | Prototype (this PRD) | Out of prototype product scope |
|-----------|----------------------|--------------------------------|
| **LINE** | **Text messages** → assistant → **text replies**. Reminder **push** is text-only. | Voice notes, speech-to-text, text-to-speech as **supported** user journeys (the codebase may contain experimental hooks; they are **not** part of the validated prototype feature set). |
| **HTTP API** | **`POST /v1/app/messages`** with **text** body; same assistant core as LINE. | Voice upload, streaming, or real-time audio as a first-class API. |
| **Feature set** | **Closed** set documented in **§6** and [`features.md`](features.md) (list / add / remove meds, explain, interaction check, confirm dose, profile/locale, summary, general Q&A band, off-topic refusal). | arbitrarily open-domain “do anything” assistant behavior. |

**Why text-only for the prototype:** lower cost to test, easier logging and review for safety copy, and a clear ceiling for what “works” before adding STT/TTS latency, failure modes, and accessibility expectations.

**Engineering note:** Repository code paths for LINE audio (e.g. Google Speech-to-Text / TTS) may exist for experimentation; **product acceptance** for the prototype is defined on **text** paths only until a later phase explicitly adds voice (see **§10 Growth**).

---

## 1. Vision (long-term)

**MedBuddy** is a **patient-facing medication companion**: help people **remember what they take**, **understand medications** in plain language, **surface interaction cautions** where reference data exists, and **support adherence** via familiar messaging — starting with **LINE** and a **shared HTTP API** for integrations and future clients (including a **reference Expo** app).

**For the prototype:** prioritize **LINE text** + **FastAPI** + **HTTP text chat**; keep the feature set **explicit and testable** (see §6).

---

## 2. Problem statement

Patients often struggle to:

- Maintain an accurate mental model of **what** they take, **when**, and **why**.
- Remember **doses** in daily life without intrusive tooling.
- Ask **reference-grounded** (but still non-diagnostic) questions about drugs and combinations.
- Prepare a **concise summary** for a clinic visit in their own language.

Existing tools are frequently app-centric, English-only, or disconnected from conversational channels already used daily (e.g. messaging apps in Taiwan and similar markets).

---

## 3. Goals and non-goals

### 3.1 Product goals (prototype)

| ID | Goal | Measurable direction (prototype-level) |
|----|------|--------------------------------------|
| G1 | **Reliable medication list** via natural **text** | Add/list/remove flows persist correctly with Supabase; tests cover agent tools. |
| G2 | **Understandable answers** | Explain/interaction intents use registry grounding (OpenFDA) where available; caching reduces repeat cost. |
| G3 | **Adherence support on LINE (text)** | `dose_events` materialized; **text** reminders and optional **text** nudges; chat **text** “I took it” marks adherence. |
| G4 | **Bilingual experience** | User `locale` (`en`, `zh-TW`) drives replies, LINE welcome, and reminders; onboarding can set locale/timezone. |
| G5 | **Privacy-aware LLM use** | Pattern redaction and layered patient context for external model calls; documented in `privacy.md`. |

### 3.2 Non-goals (explicit)

| ID | Non-goal | Notes |
|----|----------|--------|
| NG0 | **Voice as part of prototype acceptance** | STT/TTS may exist in code; **prototype sign-off is text-only** (§0). |
| NG1 | **Clinical diagnosis or prescribing** | Assistant refuses off-topic and avoids replacing professionals. |
| NG2 | **Full Taiwan FDA (TFDA) live integration** | Stub until real client; OpenFDA is the primary registry path today. |
| NG3 | **Rich LINE Flex / postback “mark taken”** | Reminders are **text** push; adherence is **chat text** via **`interpret_user_turn`** adherence fields + **`ConfirmDoseTool`** (intent often `confirm_dose`). |
| NG4 | **Local push notifications for standalone HTTP users** | LINE-only reminder delivery in current prototype scope. |
| NG5 | **Expo app as co-equal channel** | Expo is **reference / future**; see `frontend-expo.md`. |
| NG6 | **Production regulatory clearance** | Out of scope for prototype; any real-world deploy needs separate legal/clinical review. |

---

## 4. Target users and personas

### 4.1 Primary persona: “Home medication manager”

- **Adults** managing their own chronic medications or a family member’s list.
- **Comfortable with LINE** (or willing to use it for med support).
- **Traditional Chinese (zh-TW)** or **English** preference.
- **Prototype:** interacts in **typed text**; large-type / accessibility refinements may follow in Growth.

### 4.2 Secondary persona: “Integrator / mobile pilot”

- Engineers or partners calling **`/v1/app/*`** with `X-App-User-Id` (and optional bearer) for the same **text** assistant without LINE.

### 4.3 Anti-persona

- Users expecting **emergency triage**, **dose optimization**, or **replacing a pharmacist** — out of scope; messaging must redirect to professionals.

---

## 5. User journeys (high level)

1. **Onboard** — LINE follow or app onboarding; preferred name, optional demographics, emergency contact, health notes; **timezone** and **locale** where applicable (**text** profile updates via `update_profile` on LINE).
2. **Build the list** — User **types** medications in natural language; system persists and confirms with **grounded** acknowledgment when drug data is available.
3. **Day-to-day** — User **types** questions: what a drug is for, interactions, list meds, vitals in text, or **doctor-ready summary**.
4. **Adherence** — System schedules **`dose_events`**; LINE sends **text** reminder and optional **text** nudges; user **types** adherence; **`interpret_user_turn`** sets slots and **`ConfirmDoseTool`** records **`taken_at`** / dose notes when appropriate.
5. **Visit prep (reference app)** — Optional Expo flow (still **text-first** in API terms unless explicitly extended); see `frontend-expo.md`.

**Deeper flows and utterances:** `docs/use-cases.md`

---

## 6. Functional requirements (prototype feature set)

Requirements are **themes**; detailed acceptance-style bullets live in **`docs/features.md`**. **Prototype validation applies only to rows that assume text I/O** unless a future phase promotes voice.

### 6.1 Channels

| Req ID | Requirement | Prototype? |
|--------|-------------|------------|
| C-1 | LINE webhook accepts verified events; **text** messages run shared assistant turn; **text** reply. | **Yes** |
| C-2 | LINE **audio** → STT → assistant → optional TTS | **No** — engineering exploratory only; not in prototype acceptance (§0). |
| C-3 | HTTP `/v1/app/health`, `/info`, `/me`, **`POST /messages` (text)**, onboarding, `/summary` with documented auth model. | **Yes** (text chat) |
| C-4 | Internal **reminder reconcile** endpoint for cron-style safety net. | **Yes** (staging/pilot) |

### 6.2 Assistant and intents (closed set for prototype)

| Req ID | Requirement | Prototype? |
|--------|-------------|------------|
| A-1 | Single pipeline `run_assistant_text_turn` for LINE **text** and HTTP **text** chat. | **Yes** |
| A-2 | LLM **`interpret_user_turn`** (intent + structured adherence fields) with recent **redacted** dialogue for short follow-ups. | **Yes** |
| A-3 | Tools: list/add/remove medications, explain medication, interaction check, confirm dose, health summary, profile update, locale change, off-topic handling. | **Yes** |
| A-4 | `general_question` / `log_vital` fall back to composed reply without automatic drug prefetch. | **Yes** |
| A-5 | Medication add stores **reminder preferences** in metadata when extracted (drives `dose_events`). | **Yes** |

### 6.3 Data and persistence

| Req ID | Requirement | Prototype? |
|--------|-------------|------------|
| D-1 | Supabase (pilot): patients, medications, conversations, drug caches, dose events; RLS for `anon` key usage. | **Yes** |
| D-2 | Drug reference cache (OpenFDA-backed) and per-patient personalization cache for explain/interaction. | **Yes** |
| D-3 | In-memory mocks when Supabase unset (CI/local). | **Yes** |

### 6.4 Reminders (LINE, text push)

| Req ID | Requirement | Prototype? |
|--------|-------------|------------|
| R-1 | After add/remove medication, rebuild upcoming `dose_events` per prefs and defaults (including multi-daily local times where implemented). | **Yes** |
| R-2 | Redis + arq deferred jobs push **text** LINE reminders; optional **text** nudge chain. | **Yes** (environment-dependent) |
| R-3 | **Text** chat, when interpretation sets **`record_pending_dose_as_taken`**, sets `taken_at` on matching pending events. | **Yes** |
| R-4 | Reminder copy respects user **locale**. | **Yes** |

### 6.5 Localization

| Req ID | Requirement | Prototype? |
|--------|-------------|------------|
| L-1 | Backend locales `zh-TW` and `en`; per-user `locale` overrides process default. | **Yes** |
| L-2 | Timezone (IANA) from patient record drives scheduling and reminder copy. | **Yes** |

### 6.6 Operations and quality

| Req ID | Requirement | Prototype? |
|--------|-------------|------------|
| O-1 | Structured logging without raw user content in shared logs. | **Yes** |
| O-2 | Makefile / CI checks documented; behavior changes recorded in `CHANGELOG.md`. | **Yes** |

---

## 7. Non-functional requirements (prototype-appropriate)

| NFR ID | Area | Requirement |
|--------|------|-------------|
| N-1 | **Architecture** | Hexagonal ports/adapters; swappable LLM (Gemini/OpenAI) and integrations. |
| N-2 | **Security** | LINE signature verification in real mode; mobile bearer optional; cron secret for internal reconcile; secrets in env only. |
| N-3 | **Privacy** | Documented redaction and LLM context policy (`privacy.md`, `llm-context.md`). Prototype must not expand LLM context beyond documented boundaries without revisiting privacy docs. |
| N-4 | **Deployability** | Docker + Compose; Render blueprint; mock mode for demos without keys. |
| N-5 | **Reliability** | Reconcile endpoint mitigates missed reminder jobs; dose model supports idempotent-ish adherence marking. |
| N-6 | **Expectations** | No SLA commitments for prototype; “best effort” suitable for **small controlled pilots** only. |

---

## 8. Integrations (dependency summary)

| Integration | Role | Prototype need |
|-------------|------|----------------|
| LINE Messaging API | Webhook + **text** reply + **text** push reminders | **Yes** (primary channel) |
| LLM (Gemini or OpenAI) | `interpret_user_turn`, compose, structured extract | **Yes** |
| Supabase Postgres | Persistence | **Yes** for real pilot |
| Redis + arq | Reminder workers | **Yes** if reminders in pilot |
| OpenFDA HTTP | Label grounding | **Yes** (explain/interaction grounding) |
| Google Speech-to-Text | LINE STT | **No** for prototype product acceptance |
| edge-tts | LINE TTS | **No** for prototype product acceptance |

**Full matrix:** root `README.md`, `apps/backend/README.md`

---

## 9. Metrics and validation (prototype)

Success for the **text** prototype is judged by:

- **Correctness:** pytest (and manual scripts) for agent turns, reminders materialization, locale/timezone behavior.
- **Qualitative review:** sample **text** dialogs in `use-cases.md`; no diagnosis language in default persona; off-topic refusals feel consistent.
- **Operational (pilot):** webhook stability, reminder delivery where Redis is enabled, reconcile drill.
- **Explicitly not required for prototype:** voice success rate, WER, TTS quality, or multimodal analytics.

---

## 10. Phased roadmap: MVP, Growth, Global

Horizons are **product intent**, not guarantees. They assume continued investment and separate decisions on compliance for anything beyond a lab/pilot.

### 10.1 MVP — up to ~3 months (harden the text prototype)

**Objective:** A **credible, text-only** medication companion on **LINE + HTTP** for a **small pilot**, with a **frozen** intent/tool surface and honest disclaimers.

| Theme | Goals (realistic) |
|-------|-------------------|
| **Core text UX** | Stable flows for §6 intents; clear failure messages; onboarding + profile + locale + timezone validated on real Supabase. |
| **Grounding** | OpenFDA path reliable for common queries; personalization/reference caches TTL’d and observable in logs (not PII). |
| **Reminders** | Text reminders + reconcile proven in one staging/pilot environment; chat adherence (**`interpret_user_turn`** + **`ConfirmDoseTool`**) validated with testers. |
| **Quality** | Test suite green; documented runbooks for deploy and cron; pilot feedback captured (simple form or interviews). |
| **Governance** | Disclaimer visible; internal policy for who may use the trial; no marketing as a “medical product.” |

**Exit criteria (example):** pilot cohort completes add/list/reminder/confirm cycle without data loss; team signs off that **text-only** scope is what was tested.

### 10.2 Growth — up to ~1 year (expand modality, depth, and readiness)

**Objective:** Move from “works in a pilot” toward “could serve a wider audience” **without** claiming full global or regulatory readiness.

| Theme | Goals (realistic) |
|-------|-------------------|
| **Voice (optional product)** | If demand is clear: promote LINE **audio** to **supported** — STT/TTS SLAs, failure fallbacks (“please type or retry”), and updated PRD acceptance. |
| **Retention & adherence** | Follow-up chat to **adjust reminder preferences**; richer adherence views; consider caregiver-facing **read-only** summaries (policy-dependent). |
| **Regional data** | TFDA or additional registries **where legally and technically viable**; improved cache strategy (e.g. semantic drug Q&A caching per `TODO.md`). |
| **Mobile** | Exp beyond reference: auth model, cost controls, optional local notifications **if** product strategy leaves LINE-only reminders. |
| **Operability** | Cost/latency budgets for LLM; basic product analytics; incident response playbook; content safety review loop for new prompts. |

**Exit criteria (example):** repeatable monthly cost per active user; voice (if launched) meets agreed error-rate bar; roadmap for compliance review **if** moving past informal pilots.

### 10.3 Global — after ~1 year (scale and jurisdiction-aware product)

**Objective:** Only pursue **after** Growth indicates demand and **after** legal/clinical review — not implied by the prototype repo.

| Theme | Goals (realistic, non-committing) |
|-------|-----------------------------------|
| **Markets** | Multi-region deploy with **data residency** options; languages beyond `en` / `zh-TW` driven by market research. |
| **Compliance posture** | Deliberate classification (e.g. wellness vs regulated software) per country; DPIA / HIPAA / comparable workflows **if** handling PHI at scale. |
| **Ecosystem** | EMR-friendly export formats; institutional pilots; optional B2B packaging **if** business model supports it. |
| **UX** | Native apps and/or rich LINE UI as **primary** channels; accessibility standards (WCAG-aware) for voice and visual UI. |

**Guardrail:** “Global” here means **capability direction**, not a promise of worldwide launch.

---

## 11. Open questions

1. **Regulatory / market**: jurisdiction-specific claims copy, data residency, and whether the offering remains general wellness vs regulated software.
2. **Identity**: long-term auth model beyond `X-App-User-Id` + optional bearer for standalone clients.
3. **Clinical partnerships**: whether summary formats need institution-specific templates.
4. **Voice promotion**: criteria to move LINE audio from “engineering only” to **Growth** acceptance (accuracy, cost, accessibility).

---

## 12. Related documentation

| Document | Purpose |
|----------|---------|
| [`features.md`](features.md) | Capability catalog (product/engineering alignment). |
| [`use-cases.md`](use-cases.md) | Narrated flows and example utterances. |
| [`architecture.md`](architecture.md) | Technical design, API reference, data model. |
| [`reminders.md`](reminders.md) | Dose reminders operations detail. |
| [`privacy.md`](privacy.md) | PII and LLM boundaries. |
| [`frontend-expo.md`](frontend-expo.md) | Reference Expo client only. |
| [`../README.md`](../README.md) | Repo overview and quick start. |
