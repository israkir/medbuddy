# MedBuddy — Feature catalog

This document is the **capability catalog**: what the product does, who it is for, and how it is implemented. It follows a consistent **feature-spec** shape so product and engineering can align on scope, behavior, and constraints.

**Disclaimer:** MedBuddy is a software prototype. It is **not** a substitute for professional medical advice, diagnosis, or treatment.

**Related docs**

| Document | Purpose |
|----------|---------|
| [`use-cases.md`](use-cases.md) | Narrated user flows, example utterances, and step-by-step handling |
| [`reminders.md`](reminders.md) | LINE dose reminder scheduling, workers, and ops |
| [`privacy.md`](privacy.md) | PII boundaries and LLM data shaping |
| [`frontend-expo.md`](frontend-expo.md) | **Reference / future:** Expo app only — not mixed with primary LINE + backend features |

---

## How each feature is described

| Field | Meaning |
|-------|---------|
| **Summary** | One sentence: what this capability does |
| **User value** | Problem solved or outcome for the user |
| **Capabilities** | Observable behaviors and boundaries (acceptance-style) |
| **Implementation** | How the codebase delivers it (components, pipelines) |
| **Configuration** | Env vars, flags, or deployment notes when relevant |
| **Limitations** | Explicit non-goals or prototype constraints for this slice |

Sections below use these fields where they add clarity; small or purely operational items may use a compact table only.

---

## 1. Delivery channels

### 1.1 LINE Messaging API

**Summary:** Receive LINE events (follow, text, voice), authenticate the webhook, and run the shared assistant pipeline for text and transcribed voice.

**User value:** Primary user-facing channel: chat and voice in LINE, with optional TTS replies and the same assistant core as the HTTP API.

**Capabilities**

- Webhook endpoint accepts verified LINE events when `LINE_CHANNEL_SECRET` is set; mock mode may skip signature verification (see backend README).
- New followers get a deterministic **welcome** from i18n (`get_or_create_user`); this path does **not** call `run_assistant_text_turn`.
- Text messages map LINE `userId` → `user_key` → `run_assistant_text_turn(user_key, user_text)` → reply as LINE text (or batch with audio for voice replies).
- Voice messages: download audio → STT (Whisper HTTP or mock) → same assistant pipeline on transcript; optional TTS returns a short-lived public URL under `/internal-media/...` with batch audio + text and TTL cleanup.

**Implementation**

- `line-bot-sdk`: `WebhookParser` / `SignatureValidator`, `AsyncMessagingApi` / `AsyncMessagingApiBlob` for replies and blob download.

**Configuration**

- `LINE_CHANNEL_SECRET`, `PUBLIC_BASE_URL` (for TTS fetch), Whisper/TTS service settings as documented in the backend README.

---

### 1.2 Standalone HTTP API (`/v1/app`)

**Summary:** REST surface for **non-LINE** HTTP clients: health, service info, profile, onboarding, assistant chat, and structured health summary.

**User value:** Same assistant and persistence as LINE without the Messaging API — for integrations, tests, and optional mobile or web clients.

**Capabilities**

- All routes require `X-App-User-Id` (4–128 chars). When `MEDBUDDY_MOBILE_BEARER_TOKEN` is set and mocks are not forcing open access, clients send `Authorization: Bearer <token>`.
- **`GET /v1/app/health`** — JSON health for mobile probes.
- **`GET /v1/app/info`** — Non-secret service metadata.
- **`GET /v1/app/me`** — `app_user_id` and profile: `preferred_name`, `age_years`, `gender`, `emergency_contact`, `health_notes`, `timezone` (IANA, default `Asia/Taipei`), `onboarding_completed_at`.
- **`POST /v1/app/onboarding`** — Persists onboarding via `UserDataPort.save_onboarding_profile`; required `preferred_name`; optional demographics, emergency contact, health notes, optional IANA **`timezone`** (clients typically send the device zone).
- **`POST /v1/app/messages`** — Body `text` (1–8000 chars); resolves auth → `run_assistant_text_turn(user_key=app_user_id, user_text)` → `{"reply":"…"}`.
- **`GET /v1/app/summary`** — Structured doctor-ready summary via `GenerateHealthSummaryTool`.

**Implementation**

- Routes in `channels/mobile/routes.py` (or equivalent); wired through the same assistant entrypoint as LINE text.

**Reference client**

- The repo includes an **Expo** app that consumes this API — documented separately as a **future / reference product**: [`frontend-expo.md`](frontend-expo.md).

---

### 1.3 Global and operations routes

**Summary:** Liveness, internal media for TTS, and cron-style reminder reconciliation.

**User value:** Operations and LINE audio delivery without exposing assistant logic on extra paths.

**Capabilities**

- **`GET /health`** — Plain-text liveness for load balancers and Compose.
- **`GET /internal-media/{file_id}`** — Serves generated TTS for LINE; `PUBLIC_BASE_URL` must point at this host.
- **`POST /internal/reminders/reconcile`** — When `MEDBUDDY_CRON_SECRET` matches header `X-Cron-Secret`, re-enqueues reminder jobs for due, unsent, not-taken `dose_events`.

---

## 2. Agent layer (hexagonal + tool dispatch)

**Summary:** Classified intents map to small, testable tools behind `MedicationAgent` and port interfaces.

**User value:** Predictable behavior per intent, isolated tests, and swappable integrations.

**Capabilities**

- Business logic depends on `protocols/` ports; `container.py` wires mock or real adapters at startup—no direct imports from `integrations/` in domain code.
- Tools return `ToolResult` (text + optional metadata).

**Implementation**

| Tool class | Intent(s) | Location |
|------------|-----------|----------|
| `ListMedicationsTool` | `list_medications` | `agents/tools/medication_crud.py` |
| `AddMedicationTool` | `add_medication` | `agents/tools/medication_crud.py` |
| `RemoveMedicationTool` | `remove_medication` | `agents/tools/medication_crud.py` |
| `ExplainMedicationTool` | `explain_medication` | `agents/tools/drug_lookup.py` |
| `InteractionCheckTool` | `interaction_check` | `agents/tools/interaction_check.py` |
| `GenerateHealthSummaryTool` | `request_summary` | `agents/tools/health_summary.py` |

---

## 3. Shared assistant pipeline

**Summary:** `run_assistant_text_turn` (`application/assistant_turn.py`) is the single core for LINE text/voice (post-STT) and `POST /v1/app/messages`.

**User value:** One pipeline so behavior and safety rules stay consistent across channels.

**Capabilities**

- Intent classification via configured LLM (e.g. Gemini) or mock rules in tests.
- Handling order (simplified): optional intent hooks → profile intent (`UPDATE_PROFILE`) → medication intents (list / add / remove) → explain / interaction path with caches and drug grounding → generic `compose_reply` for other intents.
- Drug snippet prefetch in the main turn applies to `explain_medication`, `interaction_check`, and (after a successful save) `add_medication` only.
- For `explain_medication` and `interaction_check`, locale-specific **companion** instructions bias replies toward purpose, timing rationale, and cautions—without replacing clinician advice.

**Limitations**

- Arbitrary intents do not get automatic drug API prefetch unless they match the above.

---

## 4. Assistant intents

Identifiers match `Intent` in `medbuddy.models.domain`.

### 4.1 `list_medications`

| Field | Content |
|-------|---------|
| **Summary** | Return the user’s saved medication list with i18n framing. |
| **User value** | Quick inventory without LLM hallucination on list contents. |
| **Capabilities** | No LLM compose for the list body; data from `UserDataPort.list_medications` plus i18n intro / empty state. Display may use `build_patient_context_for_chat_display` for full stored lines in user-facing copy—that string is not for external LLM APIs (see `privacy.md`). |

### 4.2 `add_medication`

| Field | Content |
|-------|---------|
| **Summary** | Parse natural language into a medication row, persist, and confirm with grounded copy. |
| **User value** | Add drugs with schedule in chat without a structured form. |
| **Capabilities** | Extraction via LLM JSON or mock heuristics → `MedicationDraft`; missing drug name → i18n `medication.add_incomplete` (no full compose). Persist via `UserDataPort.add_medication`. Post-save: reload list, `DrugDataPort` snippets for the **new** drug only (OpenFDA HTTP; TFDA stub until integrated; mocks may simulate TFDA). Does **not** use `drug_personalization_cache`. Reply via `LLMPort.compose_medication_added_reply` or i18n `medication.added` on failure. |
| **Implementation** | Successful add may trigger reminder sync when Supabase + reminder wiring apply (§8). |

### 4.3 `remove_medication`

| Field | Content |
|-------|---------|
| **Summary** | Resolve and delete a tracked medication by name. |
| **User value** | Stop tracking a drug without navigating settings. |
| **Capabilities** | Resolve row (LLM JSON or mock match) → `delete_medication` → i18n confirmation or not-found. Reminder rebuild when configured (same hook as add). |

### 4.4 `explain_medication`

| Field | Content |
|-------|---------|
| **Summary** | Answer what a drug is for and related comprehension questions with optional reference grounding and reply caching. |
| **User value** | Understand medications in context of their list, with less repeated LLM cost when cached. |
| **Capabilities** | Supabase: if `drug_personalization_cache` has a fresh row for `(user, query_fingerprint)` (fingerprint includes hash of current med list in de-identified form), return cached text, append turns, skip remote fetch and LLM. Else: `DrugDataPort` + `CachingDrugData` → `drug_reference_cache` (TTL `MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS`). Load history, store user turn; hooks / medication short-circuits; else `compose_reply` with persona, LLM-safe patient context, grounding, history. After compose: upsert personalization; `llm_meta.source` reflects `openfda` / `tfda` / model as applicable. |

### 4.5 `interaction_check`

| Field | Content |
|-------|---------|
| **Summary** | Drug–drug or combination cautions using the same pipeline as explain with interaction-focused prompting. |
| **User value** | Surface interaction concerns grounded on references where available. |
| **Capabilities** | Personalization hit → reference cache → `compose_reply` with interaction add-on → optional cache save. |

### 4.6 `update_profile`

| Field | Content |
|-------|---------|
| **Summary** | Update profile fields from conversational text. |
| **User value** | Correct name, emergency contact, or notes without a separate settings API for every field. |
| **Capabilities** | `UserDataPort.patch_user_profile` via `parse_profile_patch_from_text`—local heuristics, **no** LLM JSON extraction for stored PII fields. |

### 4.7 `confirm_dose` / `log_vital` / `request_summary` / `general_question`

| Field | Content |
|-------|---------|
| **Summary** | General assistant behaviors: dosing concerns, vitals, summaries, small talk. |
| **User value** | Same assistant persona for adjacent questions without forcing everything into medication CRUD. |
| **Capabilities** | No automatic drug API prefetch in the main turn (unlike explain/interaction/add ack). Replies via hooks, medication handlers, or generic `compose_reply` without explain/interaction companion add-on unless the classified intent is one of those paths. |

---

## 5. Privacy and LLM data shaping

**Summary:** Pattern-based redaction and layered patient context so LLM calls minimize unnecessary PII while the UI can still show full list copy where intended.

**User value:** Reduces accidental leakage to model providers; keeps UX honest about what is stored.

**Capabilities**

| Concern | Behavior |
|---------|----------|
| Redaction | Before `classify_intent`, `compose_reply`, and medication extract/remove LLM calls: `redact_pii_text` / `redact_conversation_turns_for_llm` (emails, typical phone shapes, long digit runs). Pattern-based, not full PHI scrubbing. |
| Patient context for LLM | `build_patient_context_for_llm` — coarse signals (e.g. “preferred name on file” without the name), age band, medication lines; not raw `preferred_name`, `health_notes`, `emergency_contact`, exact `age_years`. |
| Patient context for display | `build_patient_context_for_chat_display` — full snippet for user-facing list replies only. |
| Storage | Conversation rows may store original user text; copies sent to the LLM adapter are redacted. |
| Cache fingerprinting | De-identified context (and redacted query where applicable); stored personalized text may still be sensitive. |

**Related:** [`privacy.md`](privacy.md).

---

## 6. Persistence and caching (Supabase)

**Summary:** Optional Postgres-backed users, medications, conversations, drug caches, and dose events when Supabase is configured.

**User value:** Durable state across restarts, shared caches for drug reference and personalization, foundation for reminders.

**Capabilities**

When `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (or `SUPABASE_ANON_KEY`) are set and the `supabase` extra is installed, `UserDataPort` and `ConversationStorePort` use Postgres (schema `apps/backend/supabase/schema.sql`, RLS for `anon`).

| Layer | Tables / behavior | Role |
|-------|-------------------|------|
| Users & profile | `users` | `external_user_id`, onboarding fields, `gender`, `timezone`, `onboarding_completed_at`, etc. |
| Medications | `medications` | Per-user list for assistant and reminders. |
| Conversation | `conversation_turns` | Recent dialogue; `created_at` for turn time. |
| Drug reference | `drug_reference_cache` | Shared snippets: `source`, `query_key`, label fields, TTL `expires_at`. |
| Personalization | `drug_personalization_cache` | Per-user cached explain/interaction replies; unique `(user_id, query_fingerprint)`; TTL `MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS`. |
| Dose reminders | `dose_events` | Scheduled instants, optional `taken_at`, `reminder_sent_at`. |

**Limitations**

- Without Supabase: in-memory `MockUserData` / mock conversation store; `CachingDrugData` and `SupabaseDrugCaches` are not wired.

**Related:** [`use-cases.md`](use-cases.md#caching--data-when-supabase-is-configured), [`reminders.md`](reminders.md).

---

## 7. Integrations

**Summary:** Pluggable providers for LINE, LLM, STT, TTS, drug data, storage, and background jobs.

**User value:** Deploy with different vendors or full mocks for development and CI.

**Capabilities**

| Integration | Role |
|-------------|------|
| LINE | Webhook + push (reply and reminder worker). |
| LLM | `LLM_PROVIDER` selects `GeminiLLM` (`google-genai`, default `gemini-2.5-flash`) or `OpenAILLM` (Chat Completions, default `gpt-4.1-mini`). Same `LLMPort` for classify, compose, extraction. |
| Whisper HTTP | STT for LINE voice. |
| edge-tts | TTS for voice replies. |
| OpenFDA HTTP | Drug label snippets for grounding and reference cache. |
| TFDA | Placeholder — `fetch_tfda_snippet` returns `None` until a real client exists. |
| Local public storage | Short-lived audio files for LINE when `public_base_url` is configured. |
| Redis + arq | Deferred `send_reminder_for_dose` jobs when `REDIS_URL` is set and `[reminders]` is installed. |

**Configuration**

- `MEDBUDDY_INTEGRATION`, `MOCK_EXTERNAL_SERVICES`, and per-env tokens drive `build_app_services` in `container.py`. On Render (`RENDER=true`), production-safe defaults force real integrations.

---

## 8. LINE dose reminders (prototype)

**Summary:** After medication list changes, schedule future `dose_events` and push LINE reminders at configured local times.

**User value:** Lightweight adherence nudges without requiring the user to open the app.

**Capabilities**

| Topic | Behavior |
|-------|----------|
| Trigger | Successful `add_medication` or `remove_medication` via `try_medication_intents` (any channel using that handler). |
| Scheduling | `UserDataPort.sync_upcoming_dose_events` replaces future `dose_events`: one local time per day (`MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME`, default `09:00`) in `users.timezone` (IANA). Horizon `MEDBUDDY_REMINDER_HORIZON_DAYS` (default 14, cap 90). Free-text `schedule` on the med does **not** expand to multiple daily times in v1 (may still appear in copy). |
| Delivery | With Redis, `enqueue_reminder_jobs` schedules arq `send_reminder_for_dose` with `_defer_until = scheduled_at`. Worker runs `deliver_dose_reminder` → LINE `push_message`, then `reminder_sent_at`. |
| Copy | Locale key `reminder.line_push` (`zh-TW`, `en`). |
| Scope | LINE push only for LINE `userId` keys; no local notifications for standalone HTTP-app users in this slice. No Flex cards or “mark taken” postback in v1. `dose_events.taken_at` exists for future adherence use. |
| Reconcile | `POST /internal/reminders/reconcile` with `X-Cron-Secret`. |

**Limitations**

- LINE-only users keep default timezone until changed in DB; standalone onboarding sets `timezone`.

**Related:** [`reminders.md`](reminders.md).

---

## 9. Reference mobile client (Expo) — future product

**Summary:** The monorepo includes an **Expo (React Native)** app under `apps/frontend/` as a **reference implementation** and **candidate future product**.

**User value:** (Future) native iOS/Android UX on top of `/v1/app`; offline-first mocks for development.

**Scope in this catalog**

- **Not** listed alongside LINE or backend features above — see the dedicated reference: **[`frontend-expo.md`](frontend-expo.md)** for screens, env vars, mock vs API, voice limitations, and relationship to dose reminders.
- Day-to-day commands: [`apps/frontend/README.md`](../apps/frontend/README.md).

---

## 10. Observability and quality

**Summary:** Structured logging for operations without logging raw user content; Makefile and automation for dev workflow.

**User value:** Safer logs in shared environments; repeatable local and CI workflows.

**Capabilities**

| Topic | Behavior |
|-------|----------|
| Logging | `LOG_LEVEL` (default `INFO`) for `medbuddy.*` and `uvicorn.error`. Webhook/orchestrator logs structured INFO (event types, steps, reply sizes) without raw user message text. |
| Assistant turn logs | `run_assistant_text_turn` logs `user_key`, `med_count`, per-medication flat lines (`id`, name, dosage, schedule, `instructions_zh`). |
| Repo automation | Root Makefile (`be-*`, `fe-*`), pre-commit, `CHANGELOG.md` for notable changes. |

---

## 11. Extensibility

**Summary:** Intent hooks can short-circuit with a string before medication handlers and `compose_reply`.

**User value:** Pilot features (e.g. doctor-facing summaries) without forking LINE routing.

**Capabilities**

- Registered hooks may return a string before medication handlers and `compose_reply`. See `extensibility/intent_hooks.py`.

---

## 12. Explicit non-goals (current codebase)

| Non-goal | Notes |
|----------|--------|
| Clinical diagnosis | Prompts push back; not a substitute for professionals. |
| Full TFDA API in production HTTP | Stub returns empty; mocks may fake TFDA. |
| Reference Expo hold-to-talk → backend STT | Not wired; see [`frontend-expo.md`](frontend-expo.md). LINE voice + Whisper HTTP are the supported voice path in the primary product. |
| Rich LINE reminder UI | No multi-time-per-day scheduling from free-text in reminder v1. |

---

## Document map

Index: [`../README.md`](../README#documentation). Design: [`architecture.md`](architecture.md). Flows: [`use-cases.md`](use-cases.md). LINE dose pushes: [`reminders.md`](reminders.md). PII: [`privacy.md`](privacy.md). **Reference mobile (Expo):** [`frontend-expo.md`](frontend-expo.md). Backend: [`../apps/backend/README.md`](../apps/backend/README.md). Frontend dev: [`../apps/frontend/README.md`](../apps/frontend/README.md).
