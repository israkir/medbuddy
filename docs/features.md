# MedBuddy — Features

This document lists **implemented product features** and how they behave in the codebase. For narrated flows and example utterances, see **[`use-cases.md`](use-cases.md)**. For reminder plumbing only, **[`reminders.md`](reminders.md)**. For PII and LLM boundaries, **[`privacy.md`](privacy.md)**.

**Disclaimer:** MedBuddy is a software prototype. It is **not** a substitute for professional medical advice, diagnosis, or treatment.

---

## 1. Delivery channels

### 1.1 LINE Messaging API

| Feature | Detail |
|--------|--------|
| **Webhook** | `POST /v1/line/webhook` — body verified with **`X-Line-Signature`** when **`LINE_CHANNEL_SECRET`** is set; in mock mode without a secret, verification can be skipped (see backend README). |
| **New follower (`follow`)** | Ensures a user row exists (`get_or_create_user`), then sends a **fixed welcome** from i18n — **not** a full `run_assistant_text_turn`. Welcome copy (en / 简体中文 examples) invites a one-line profile (name, optional age, family contact, allergies / conditions); see [`use-cases.md`](use-cases.md). |
| **Text messages** | Parsed events → LINE `userId` as `user_key` → **`run_assistant_text_turn(user_key, user_text)`** → reply as LINE text (or batch with audio; see voice). |
| **Voice messages** | Audio fetched from LINE → **STT** (Whisper HTTP service or mock) → same assistant pipeline on the transcript. If the path requests audio back: **TTS** (edge-tts or mock) writes a **short-lived public URL** under **`/internal-media/...`**; LINE may receive a **batch** of audio + text; temp storage deletes after TTL. |
| **Client library** | `line-bot-sdk` — `WebhookParser` / `SignatureValidator`, `AsyncMessagingApi` / `AsyncMessagingApiBlob` for replies and content download. |

### 1.2 Standalone app HTTP API (`/v1/app`)

All routes below use **`X-App-User-Id`** (stable id per install or account, 4–128 chars). When **`MEDBUDDY_MOBILE_BEARER_TOKEN`** is set and mocks are not forcing open access, clients send **`Authorization: Bearer <token>`**.

| Endpoint | Feature |
|----------|---------|
| **`GET /v1/app/health`** | JSON health for mobile clients. |
| **`GET /v1/app/info`** | Public service metadata (non-secret). |
| **`GET /v1/app/me`** | Returns **`app_user_id`** and profile: **`preferred_name`**, **`age_years`**, **`gender`**, **`emergency_contact`**, **`health_notes`**, **`timezone`** (IANA, default **`Asia/Taipei`**), **`onboarding_completed_at`**. |
| **`POST /v1/app/onboarding`** | Body: **`preferred_name`** (required), optional **`age_years`**, **`gender`** (`female` \| `male` \| `non_binary` \| `prefer_not_say` \| `other`), **`emergency_contact`**, **`health_notes`**, **`timezone`** (optional IANA name; omitted → **`Asia/Taipei`**). The Expo client sends the **device zone** (`Intl…resolvedOptions().timeZone`) via **`companionApi`**. Persists via **`UserDataPort.save_onboarding_profile`**; response mirrors **`GET /me`**. |
| **`POST /v1/app/messages`** | Body: **`text`** (1–8000 chars). Resolves auth → **`run_assistant_text_turn(user_key=app_user_id, user_text)`** → **`{"reply":"…"}`**. |
| **`GET /v1/app/summary`** | Returns a structured doctor-ready health summary (main concern, symptoms, optional vitals, med changes, questions, carer note). Backed by `GenerateHealthSummaryTool` via the agent; the Expo app also stores a local draft in AsyncStorage. |

### 1.3 Global / ops routes

| Endpoint | Feature |
|----------|---------|
| **`GET /health`** | Plain-text liveness (repo root compose / load balancers). |
| **`GET /internal-media/{file_id}`** | Serves generated TTS audio for LINE fetches (**`PUBLIC_BASE_URL`** must point at this host). |
| **`POST /internal/reminders/reconcile`** | When **`MEDBUDDY_CRON_SECRET`** matches header **`X-Cron-Secret`**, re-enqueues reminder jobs for due, unsent, not-taken **`dose_events`** (safety net after Redis/worker issues). |

---

## 2. Agent layer (hexagonal + agent-dispatch)

The backend follows **hexagonal architecture** (ports & adapters): `agents/` and `application/` call `protocols/` interfaces; `container.py` wires concrete adapters (mock or real) at startup so no business logic imports from `integrations/` directly.

`MedicationAgent` (`agents/medication_agent.py`) maps each classified intent to a typed `AgentTool` and executes it:

| Tool class | Intent(s) | Location |
|------------|-----------|----------|
| `ListMedicationsTool` | `list_medications` | `agents/tools/medication_crud.py` |
| `AddMedicationTool` | `add_medication` | `agents/tools/medication_crud.py` |
| `RemoveMedicationTool` | `remove_medication` | `agents/tools/medication_crud.py` |
| `ExplainMedicationTool` | `explain_medication` | `agents/tools/drug_lookup.py` |
| `InteractionCheckTool` | `interaction_check` | `agents/tools/interaction_check.py` |
| `GenerateHealthSummaryTool` | `request_summary` | `agents/tools/health_summary.py` |

Each tool returns a `ToolResult` (text reply + optional metadata) and is fully testable in isolation with mock ports.

---

## 3. Shared assistant pipeline

**`run_assistant_text_turn`** (see `application/assistant_turn.py`) is the **single core** for LINE text/voice (after STT) and **`POST /v1/app/messages`**.

**Intent classification** uses the configured **LLM** (e.g. Gemini) or **mock rules** in tests.

**Order of handling (simplified):** optional **intent hooks** → **profile** intent (`UPDATE_PROFILE`) → **medication** intents (list / add / remove) → **explain / interaction** path with optional caches and drug grounding → **generic `compose_reply`** for other intents.

**Drug snippet prefetch** inside the main turn applies to **`explain_medication`**, **`interaction_check`**, and (after a successful save) **`add_medication`** — not to arbitrary intents.

**Companion wording:** For **`explain_medication`** and **`interaction_check`**, extra locale-specific **companion** instructions bias replies toward purpose, timing rationale, and cautions — without replacing clinician advice.

---

## 4. Assistant intents (full list)

Identifiers match **`Intent`** in `medbuddy.models.domain`.

### 4.1 `list_medications`

- **User goal:** See everything saved on their list (“我的藥清單”, “What’s on my med list?”).
- **Behavior:** **No LLM compose** for the list body. Response built from **`UserDataPort.list_medications`** plus i18n intro / empty state.
- **Display context:** Can use **`build_patient_context_for_chat_display`** so the user sees **full** stored profile lines where the product echoes them; that string is **not** for external LLM APIs (see [`privacy.md`](privacy.md)).

### 4.2 `add_medication`

- **User goal:** Add a drug with dose and schedule in natural language.
- **Extraction:** LLM JSON or mock heuristics → **`MedicationDraft`** (name, dosage, schedule, optional **`instructions_zh`**). If **no drug name** → i18n **`medication.add_incomplete`** (no full compose).
- **Persist:** **`UserDataPort.add_medication`**.
- **Post-save:** Reload list → **patient medication context** → **`DrugDataPort`** snippets for the **new** drug only (**OpenFDA** HTTP; **TFDA** stub returns nothing until integrated; mocks may simulate TFDA). This path does **not** use **`drug_personalization_cache`**.
- **Reply:** **`LLMPort.compose_medication_added_reply`** — restates schedule in plain language, **one–two sentences** of grounded context, safety disclaimer; on failure → i18n **`medication.added`** template.
- **Reminders:** When Supabase + reminder wiring apply, successful add triggers **`sync_upcoming_dose_events`** and optional arq enqueue (see §7).

### 4.3 `remove_medication`

- **User goal:** Stop tracking a med (“停藥普拿疼”, “remove Tylenol”).
- **Behavior:** Resolve row (LLM JSON or mock name match) → **`delete_medication`** → i18n confirmation or not-found.
- **Reminders:** Same dose-event rebuild hook as add when configured.

### 4.4 `explain_medication`

- **User goal:** Understand what a drug is for, how to think about timing, etc.
- **Personalization cache (Supabase):** If **`drug_personalization_cache`** has a fresh row for `(user, query_fingerprint)` — fingerprint includes **hash of current medication list (de-identified context)** — return cached text, append conversation turns, **skip** remote fetch and LLM.
- **Else:** **`DrugDataPort`** (+ **`CachingDrugData`** → **`drug_reference_cache`** with TTL **`MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS`**). Reference rows can store indications, dosage/administration, warnings, **`raw_payload`**, etc.
- **Then:** Load history, store user turn; hooks / medication short-circuits if any; else **`compose_reply`** with persona, **LLM-safe patient context**, grounding, history.
- **After compose:** Upsert personalization row; **`llm_meta.source`** is **`openfda`** / **`tfda`** when registry grounding was used, else **model id** (or mock). Optional **`medication_id`** / **`reference_cache_id`** when resolvable.

### 4.5 `interaction_check`

- **User goal:** Drug–drug or combination cautions (“阿斯匹靈可以跟抗凝血藥一起吃嗎？”).
- **Behavior:** Same pipeline as explain: personalization hit → reference cache → **`compose_reply`** with **interaction-focused** system add-on → optional cache save.

### 4.6 `update_profile`

- **User goal:** Change preferred name, age, emergency contact, health notes, gender, etc. via chat.
- **Behavior:** **`UserDataPort.patch_user_profile`** driven by **`parse_profile_patch_from_text`** — **local heuristics**, **no** LLM “extract JSON” for stored PII fields.

### 4.7 `confirm_dose` / `log_vital` / `request_summary` / `general_question`

- **Examples:** Double-dose concern, “blood pressure 130/85”, “summarize in three bullets”, small talk.
- **Behavior:** No automatic drug API prefetch in the main turn (unlike explain/interaction/add ack). Replies via hooks, medication handlers, or **generic `compose_reply`** without the explain/interaction companion add-on **unless** the classified intent is one of those.

---

## 5. Privacy and LLM data shaping

| Feature | Detail |
|--------|--------|
| **Redaction** | Before **`classify_intent`**, **`compose_reply`**, and medication extract/remove LLM calls: **`redact_pii_text`** / **`redact_conversation_turns_for_llm`** — emails, typical **phone** shapes, long digit runs. Pattern-based, not full PHI scrubbing. |
| **Patient context for LLM** | **`build_patient_context_for_llm`** — **coarse signals** (e.g. “preferred name on file” without the name), **age band**, medication lines; **not** raw **`preferred_name`**, **`health_notes`**, **`emergency_contact`**, exact **`age_years`**. |
| **Patient context for display** | **`build_patient_context_for_chat_display`** — full snippet for **user-facing** list replies only. |
| **Storage** | Conversation rows may store **original** user text; only copies sent to the LLM adapter are redacted. |
| **Cache fingerprinting** | Uses de-identified context (and redacted query where applicable); stored personalized text may still be sensitive. |

Full detail: **[`privacy.md`](privacy.md)**.

---

## 6. Persistence and caching (Supabase)

When **`SUPABASE_URL`** and **`SUPABASE_PUBLISHABLE_KEY`** (or **`SUPABASE_ANON_KEY`**) are set and the **`supabase`** extra is installed, **`UserDataPort`** and **`ConversationStorePort`** use Postgres (schema in **`apps/backend/supabase/schema.sql`**, RLS for **`anon`**).

| Layer | Tables / behavior | Role |
|--------|-------------------|------|
| **Users & profile** | **`users`** | **`external_user_id`**, onboarding fields, **`gender`**, **`timezone`**, **`onboarding_completed_at`**, etc. |
| **Medications** | **`medications`** | Per-user list for assistant and reminders. |
| **Conversation** | **`conversation_turns`** | Recent dialogue; **`created_at`** maps to turn time. |
| **Drug reference** | **`drug_reference_cache`** | Shared snippets: `source`, `query_key`, label fields, TTL **`expires_at`**. |
| **Personalization** | **`drug_personalization_cache`** | Per-user cached explain/interaction replies; unique **`(user_id, query_fingerprint)`**; TTL **`MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS`**. |
| **Dose reminders** | **`dose_events`** | Scheduled instants, optional **`taken_at`**, **`reminder_sent_at`**. |

**Without Supabase:** in-memory **`MockUserData`** / mock conversation store; **`CachingDrugData`** and **`SupabaseDrugCaches`** are not wired.

---

## 7. Integrations (configurable)

| Integration | Role |
|-------------|------|
| **LINE** | Webhook + push (reply and reminder worker). |
| **Gemini** (`google-genai`) | Intent classification, **`compose_reply`**, **`compose_medication_added_reply`**, extraction. Default model **`gemini-2.5-flash`**; override **`GEMINI_MODEL`**. |
| **Whisper HTTP** | STT for LINE voice. |
| **edge-tts** | TTS for voice replies. |
| **OpenFDA HTTP** | Drug label snippets for grounding and reference cache. |
| **TFDA** | Placeholder in code — **`fetch_tfda_snippet`** returns **`None`** until a real client exists. |
| **Local public storage** | Short-lived audio files for LINE when **`public_base_url`** is configured. |
| **Redis + arq** | Deferred **`send_reminder_for_dose`** jobs when **`REDIS_URL`** is set and **`[reminders]`** is installed. |

**Mock vs real:** **`MEDBUDDY_INTEGRATION`**, **`MOCK_EXTERNAL_SERVICES`**, and per-env tokens drive **`build_app_services`** in **`container.py`**. On **Render** (`RENDER=true`), production-safe defaults force real integrations.

---

## 8. LINE dose reminders (prototype)

| Feature | Detail |
|--------|--------|
| **Trigger** | Successful **`add_medication`** or **`remove_medication`** via **`try_medication_intents`** (any channel using that handler). |
| **Scheduling** | **`UserDataPort.sync_upcoming_dose_events`** replaces **future** **`dose_events`** for the user: **one local time per day** (**`MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME`**, default `09:00`) in **`users.timezone`** (IANA). **Source:** DB default **`Asia/Taipei`** at user creation; standalone **`POST /v1/app/onboarding`** sets **`timezone`**; **`patch_user_profile`** can update **`timezone`** (e.g. travel). LINE-only users keep the default until changed in DB. Horizon: **`MEDBUDDY_REMINDER_HORIZON_DAYS`** (default **14**, cap **90**). **Free-text `schedule` on the med does not** expand to multiple daily times in v1 (it may still appear in copy). |
| **Delivery** | With **Redis**, **`enqueue_reminder_jobs`** schedules **arq** **`send_reminder_for_dose`** with **`_defer_until = scheduled_at`**. Worker runs **`deliver_dose_reminder`** → **LINE `push_message`**, then **`reminder_sent_at`** for idempotency. |
| **Copy** | Locale key **`reminder.line_push`** (`zh-TW`, `en`). |
| **Scope** | **LINE push only** for users whose key is a LINE `userId`; **no** Expo local notifications in this slice. **No** Flex cards or “mark taken” postback in v1. **`dose_events.taken_at`** exists for future adherence use but is not required for the push job. |
| **Reconcile** | **`POST /internal/reminders/reconcile`** with **`X-Cron-Secret`** (see §1.3). |

Architecture, Compose **`reminders`** profile, and **Render** single web service (**API + arq** when **`REDIS_URL`** is set; optional extra worker from same image): **[`reminders.md`](reminders.md)**.

---

## 9. Expo (React Native) app features

Paths relative to **`apps/frontend/`**.

| Feature | Detail |
|--------|--------|
| **Onboarding** | First-run screen **`app/onboarding.tsx`**, gated in **`app/_layout.tsx`**. Large-type fields align with **`POST /v1/app/onboarding`**; **`lib/companionApi.ts`** submits the device IANA **`timezone`** with the profile (see **`submitOnboarding`**). In **`EXPO_PUBLIC_USE_MOCK_DATA=true`**, AsyncStorage-backed mock (**`companionApi`**) can persist the same shape locally. |
| **Tabs** | **Today** (`(tabs)/index.tsx`) — greeting, link to companion, **`PendingDoseCard`**, accessibility-minded typography. **Medications** — catalog **`MEDICATION_LIST`**, **`MedicationListCard`**, visit questions, **`MedicationQuestionsPanel`**, quick jump, **expo-speech** “listen” via **`MedicationExplanationContext`**. **Family** — informational copy + placeholder “invite” alert (no backend). **Settings** — language (**繁體中文（台灣）** / **English**), persisted in AsyncStorage, applied before splash hides. |
| **Medication helper** | **`app/companion.tsx`** — chat UI, **suggested prompts**, **read aloud** (on-device TTS). With **`EXPO_PUBLIC_USE_MOCK_DATA=false`**, **`POST /v1/app/messages`** with **`X-App-User-Id`** and optional bearer; mock mode returns i18n-only explanations. |
| **Voice prototype** | Tab / medications flow may use **expo-av** hold-to-talk; baseline shows an alert after recording — **not** wired to backend STT (LINE voice is the primary voice path). |
| **i18n** | **`locales/zh-TW.json`**, **`locales/en.json`** via **i18next**; device locale seeds first run until user overrides in Settings. |

**`make fe-dev-api`** / **`EXPO_PUBLIC_USE_MOCK_DATA=false`** targets a live backend; see **[`apps/frontend/README.md`](../apps/frontend/README.md)**.

---

## 10. Observability and quality

| Feature | Detail |
|--------|--------|
| **Logging** | **`LOG_LEVEL`** (default `INFO`) for `medbuddy.*` and `uvicorn.error`. Webhook/orchestrator log structured INFO (event types, steps, reply sizes) **without** logging raw user message text. |
| **Assistant turn logs** | **`run_assistant_text_turn`** logs **`user_key`**, **`med_count`**, and per-medication flat lines (`id`, name, dosage, schedule, **`instructions_zh`**). |
| **Repo automation** | Root **Makefile** (`be-*`, `fe-*`), **pre-commit**, **`CHANGELOG.md`** for notable changes. |

---

## 11. Extensibility

| Feature | Detail |
|--------|--------|
| **Intent hooks** | Registered hooks may return a string **before** medication handlers and **`compose_reply`** — useful for pilot features (e.g. doctor-facing summaries) without forking LINE routing. See **`extensibility/intent_hooks.py`**. |

---

## 12. Explicit non-goals (current codebase)

- **Clinical diagnosis** or replacing pharmacist/doctor judgment (prompts push back).
- **Full TFDA API** in production HTTP path (stub returns empty; mocks may fake TFDA).
- **Expo hold-to-talk → automatic STT** to MedBuddy backend (keyboard dictation / LINE voice are intended).
- **Rich LINE reminder UI** or in-app scheduling tied to free-text **multiple times per day** in reminder v1.

---

## Document map

| Doc | Focus |
|-----|--------|
| [`architecture.md`](architecture.md) | **Technical design** — architecture, data model, API reference, security |
| [`use-cases.md`](use-cases.md) | Narrated flows, utterances, channel specifics |
| [`reminders.md`](reminders.md) | Dose events, arq, Redis, worker, reconcile |
| [`privacy.md`](privacy.md) | Redaction, LLM boundaries, profile parsing |
| [`../apps/backend/README.md`](../apps/backend/README.md) | Env vars, integrations, LINE testing, deploy |
| [`../apps/frontend/README.md`](../apps/frontend/README.md) | Expo, mock vs API, i18n |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Version history and behavior notes |
