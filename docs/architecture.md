# MedBuddy — Technical Design Document

This document describes the system architecture, data model, API contract, integration design, security model, and deployment topology for MedBuddy.

> **Audience:** Backend and mobile engineers, platform engineers, and security reviewers.
>
> **Disclaimer:** MedBuddy is a software prototype and is not a substitute for professional medical advice.

---

## Table of contents

1. [System overview](#1-system-overview)
2. [Architecture principles](#2-architecture-principles)
3. [Backend component map](#3-backend-component-map)
4. [Request flows](#4-request-flows)
5. [Agent layer](#5-agent-layer)
6. [Data model](#6-data-model)
7. [API reference](#7-api-reference)
8. [LLM integration](#8-llm-integration)
9. [Caching strategy](#9-caching-strategy)
10. [Privacy and security](#10-privacy-and-security)
11. [Observability](#11-observability)
12. [Deployment topology](#12-deployment-topology)
13. [Configuration reference](#13-configuration-reference)
14. [Extension points](#14-extension-points)
15. [Non-goals and known limitations](#15-non-goals-and-known-limitations)

---

## 1. System overview

MedBuddy helps patients manage medications and ask medication-related questions. It delivers this through two channels that share a single assistant core:

| Channel | Entry point | Primary use case |
|---------|-------------|-----------------|
| **LINE Messaging API** | `POST /v1/line/webhook` | Chat on the LINE platform; voice notes; dose reminder push |
| **Standalone mobile app** | `POST /v1/app/messages` + companion screens | Expo (React Native) iOS/Android app |

```
┌────────────────────────────────────────────────────────────────┐
│                      Client layer                              │
│                                                                │
│   LINE platform        Expo app (iOS/Android)                  │
│   (webhook push)       (HTTP REST + local mock)                │
└──────────┬──────────────────────────┬──────────────────────────┘
           │                          │
           ▼                          ▼
┌────────────────────────────────────────────────────────────────┐
│                    FastAPI backend                             │
│                                                                │
│  /v1/line/webhook        /v1/app/*                             │
│  channels/line/          channels/mobile/                      │
│         │                       │                              │
│         └──────────┬────────────┘                              │
│                    ▼                                           │
│          application/assistant_turn.py                         │
│                    │                                           │
│                    ▼                                           │
│          agents/MedicationAgent                                │
│          (intent → tool dispatch)                              │
│                    │                                           │
│         ┌──────────┼──────────────┐                            │
│         ▼          ▼              ▼                            │
│    medication   drug lookup   health summary                   │
│       tools        tools          tools                        │
│         │          │              │                            │
│         └──────────┴──────────────┘                            │
│                    │                                           │
│            protocols/ports.py   ← hexagonal boundary          │
│         ┌──────────┼──────────────┐                            │
│         ▼          ▼              ▼                            │
│    Gemini LLM   Supabase    OpenFDA HTTP                       │
│    (or mock)  (or in-mem)   (or mock)                          │
└────────────────────────────────────────────────────────────────┘
           │                          │
           ▼                          ▼
      Redis + arq                 LINE push API
   (dose reminders)               (reminder delivery)
```

---

## 2. Architecture principles

### 2.1 Hexagonal architecture (ports & adapters)

Business logic lives in `application/` and `agents/`. These layers never import from `integrations/` directly — they depend only on `protocols/` interfaces (Python `Protocol` classes). `container.py` wires concrete adapters at startup based on environment settings.

```
application/  ──► protocols/ports.py  ◄──  integrations/
agents/             (abstract)               (concrete or mock)
```

This means:
- Tests inject mock adapters without patching or monkey-patching.
- Swapping Gemini for another LLM requires only a new adapter implementing `LLMPort`.
- Adding a new channel (e.g. WhatsApp) requires implementing `run_assistant_text_turn` with the new channel's auth, without touching agent or tool code.

### 2.2 Agent-dispatch pattern

`MedicationAgent` maps each classified intent to a typed `AgentTool` subclass and calls `tool.execute(context)`. Tools are responsible for a single operation (list meds, add med, explain med, etc.) and return a `ToolResult`. This keeps `application/assistant_turn.py` thin — it classifies intent, builds context, delegates to the agent, and persists the turn.

### 2.3 Mock-first development

Every external dependency has a mock adapter registered in `integrations/mocks/`. The default local dev mode (`MEDBUDDY_INTEGRATION=mock`) uses all mocks — no API keys, no running databases required. The test suite exercises real application logic against these mocks.

---

## 3. Backend component map

```
apps/backend/src/medbuddy/
│
├── main.py                     # FastAPI app; mounts routers; lifespan setup
├── config.py                   # Pydantic Settings; .env loading; Render safety
├── container.py                # build_app_services() — wires all adapters
├── deps.py                     # FastAPI get_services() dependency
├── exceptions.py               # MedBuddyError, LLMParseError
├── i18n.py                     # t() — key lookup with zh-TW fallback
├── logging_config.py           # configure_logging()
│
├── channels/
│   ├── line/
│   │   ├── routes.py           # POST /v1/line/webhook
│   │   ├── orchestrator.py     # handle_line_event() — event dispatch
│   │   └── signature.py        # X-Line-Signature HMAC verification
│   └── mobile/
│       ├── routes.py           # GET/POST /v1/app/*
│       ├── auth.py             # MobileAuthContext, require_mobile_auth()
│       └── schemas.py          # Pydantic I/O models
│
├── application/
│   ├── assistant_turn.py       # run_assistant_text_turn() — main entry point
│   ├── medication_intents.py   # try_medication_intents() — list/add/remove
│   └── profile_intents.py      # try_profile_intent_reply() — local update
│
├── agents/
│   ├── medication_agent.py     # MedicationAgent — intent→tool dispatch
│   ├── base.py                 # AgentTool base, ToolResult
│   └── tools/
│       ├── medication_crud.py  # List/Add/RemoveMedicationTool
│       ├── drug_lookup.py      # ExplainMedicationTool
│       ├── interaction_check.py# InteractionCheckTool
│       └── health_summary.py   # GenerateHealthSummaryTool
│
├── models/
│   └── domain.py               # Intent enum, MedicationDraft/Record, ConversationTurn
│
├── protocols/
│   ├── ports.py                # LLMPort, UserDataPort, LineMessagingPort, etc.
│   └── drug_caches.py          # DrugCachesPort
│
├── engine/
│   └── types.py                # AppServices dataclass (DI container)
│
├── integrations/
│   ├── gemini_llm.py           # GeminiLLM (google-genai)
│   ├── line_client.py          # LineHttpClient (line-bot-sdk)
│   ├── supabase_stores.py      # SupabaseUserData, SupabaseConversationStore
│   ├── supabase_drug_caches.py # SupabaseDrugCaches
│   ├── drugs_http.py           # HttpDrugData (OpenFDA + TFDA stub)
│   ├── caching_drugs.py        # CachingDrugData (reference cache wrapper)
│   ├── stt_whisper.py          # WhisperHttpSTT
│   ├── edge_tts_service.py     # EdgeTtsService
│   ├── local_public_storage.py # LocalPublicObjectStorage (temp audio)
│   └── mocks/                  # MockLLM, MockLineClient, MockUserData, etc.
│
├── privacy/
│   ├── redact.py               # redact_pii_text(), redact_conversation_turns_for_llm()
│   └── profile_parse.py        # parse_profile_patch_from_text() (local, no LLM)
│
├── prompts/
│   └── persona.py              # get_system_persona(), build_patient_context_for_llm()
│
├── llm/
│   └── schemas.py              # Pydantic models for structured LLM outputs
│
├── reminders/
│   ├── worker.py               # arq WorkerSettings
│   ├── deliver.py              # deliver_dose_reminder() → LINE push
│   ├── enqueue.py              # enqueue_reminder_jobs()
│   ├── dose_schedule.py        # gen_dose_events() — local time → UTC instants
│   └── lifecycle.py            # sync_and_enqueue_reminders() — called after add/remove
│
├── extensibility/
│   └── intent_hooks.py         # try_intent_hooks() — pilot feature hooks
│
├── http/
│   └── shared_routes.py        # /health, /internal-media/{id}, /internal/reminders/reconcile
│
└── locales/
    ├── zh-TW.json              # Primary locale (Traditional Chinese, Taiwan)
    └── en.json                 # English
```

---

## 4. Request flows

### 4.1 LINE text message

```
LINE platform
    │ POST /v1/line/webhook
    │ X-Line-Signature: <hmac>
    ▼
channels/line/routes.py
    │ verify_signature()
    │ parse_event()
    ▼
channels/line/orchestrator.py
    │ handle_line_event(event, services)
    ▼
application/assistant_turn.py
    │ run_assistant_text_turn(user_key=line_user_id, user_text)
    │   1. get_or_create_user()
    │   2. redact_pii_text(user_text)           # privacy boundary
    │   3. llm.classify_intent(redacted_text)
    │   4. try_intent_hooks()                   # extensibility
    │   5. try_profile_intent_reply()           # if UPDATE_PROFILE
    │   6. try_medication_intents()             # if list/add/remove
    │   7. MedicationAgent.run()                # explain/interaction/summary/general
    │   8. store_conversation_turn(user, reply)
    ▼
channels/line/orchestrator.py
    │ line_client.reply_message(reply_token, reply_text)
    ▼
LINE platform (reply)
```

### 4.2 Mobile app chat message

```
Expo app
    │ POST /v1/app/messages
    │ Authorization: Bearer <token>
    │ X-App-User-Id: <stable-id>
    │ Body: {"text": "..."}
    ▼
channels/mobile/routes.py
    │ require_mobile_auth()        # verify Bearer + extract user_id
    ▼
application/assistant_turn.py
    │ run_assistant_text_turn(user_key=app_user_id, user_text)
    │   (same 8-step pipeline as LINE text)
    ▼
channels/mobile/routes.py
    │ return {"reply": reply_text}
    ▼
Expo app
```

### 4.3 LINE voice message

```
LINE platform
    │ POST /v1/line/webhook  (audio message event)
    ▼
channels/line/orchestrator.py
    │ download_message_content(message_id)     # LINE blob API
    │ stt.transcribe(audio_bytes)              # Whisper HTTP or mock
    │ run_assistant_text_turn(user_key, transcript)
    │ [if voice reply requested]
    │   tts.synthesize(reply_text) → audio_bytes
    │   storage.save(audio_bytes) → public_url
    │ line_client.reply_message_batch([audio_msg, text_msg])
    ▼
LINE platform (batch reply)
```

### 4.4 Dose reminder delivery (background)

```
medication add/remove intent
    │ try_medication_intents() success
    ▼
reminders/lifecycle.py
    │ sync_upcoming_dose_events(user_id, medications)
    │   DELETE future dose_events for user
    │   INSERT new rows (one per med per day in horizon)
    ▼
reminders/enqueue.py
    │ enqueue_reminder_jobs(dose_events)
    │   arq.enqueue("send_reminder_for_dose", dose_id, _defer_until=scheduled_at)
    ▼
Redis job queue

[at scheduled_at UTC]
    ▼
reminders/worker.py (arq consumer)
    │ send_reminder_for_dose(ctx, dose_id)
    ▼
reminders/deliver.py
    │ get_dose_event_for_reminder(dose_id)  # check not already sent
    │ line_client.push_message(line_user_id, reminder_text)
    │ try_mark_reminder_sent(dose_id)        # idempotency
```

---

## 5. Agent layer

`MedicationAgent` (`agents/medication_agent.py`) implements the agent-dispatch pattern. Given a classified intent and execution context, it selects and runs the appropriate `AgentTool`.

### 5.1 Tool registry

| Tool | Intent | Key operations |
|------|--------|---------------|
| `ListMedicationsTool` | `list_medications` | `UserDataPort.list_medications()` → i18n formatted list |
| `AddMedicationTool` | `add_medication` | LLM extract → `add_medication()` → drug grounding → `compose_medication_added_reply()` → reminder sync |
| `RemoveMedicationTool` | `remove_medication` | LLM resolve → `delete_medication()` → i18n confirm → reminder sync |
| `ExplainMedicationTool` | `explain_medication` | Personalization cache check → `DrugDataPort` reference fetch → `compose_reply()` → cache save |
| `InteractionCheckTool` | `interaction_check` | Same as explain with interaction-focused system prompt |
| `GenerateHealthSummaryTool` | `request_summary` | Aggregate patient context + history → structured LLM output |

### 5.2 Tool interface

```python
class AgentTool:
    async def execute(self, context: AgentContext) -> ToolResult:
        ...

@dataclass
class ToolResult:
    reply: str
    metadata: dict = field(default_factory=dict)
```

`AgentContext` carries `AppServices`, the user record, medication list, conversation history, classified intent, and the (redacted) user message.

### 5.3 Intent classification flow

```
user_text
    │
    ▼ redact_pii_text()
redacted_text
    │
    ▼ LLMPort.classify_intent(redacted_text)
Intent enum value
    │
    ├── UPDATE_PROFILE    → profile_intents.try_profile_intent_reply()
    ├── list_medications  → ListMedicationsTool
    ├── add_medication    → AddMedicationTool
    ├── remove_medication → RemoveMedicationTool
    ├── explain_medication → ExplainMedicationTool
    ├── interaction_check → InteractionCheckTool
    ├── request_summary   → GenerateHealthSummaryTool
    └── confirm_dose / log_vital / general_question → compose_reply() generic
```

---

## 6. Data model

Schema is in `apps/backend/supabase/schema.sql`. All tables use UUIDs, Supabase RLS for the `anon` role, and UTC timestamps.

### 6.1 Entity-relationship overview

```
users (1) ─────────────── (many) medications
  │                                │
  │ (many)                         │ (many)
  ▼                                ▼
conversation_turns             dose_events
                                    │
                               (many)
                                    ▼
                         drug_personalization_cache ── (optional FK) ── drug_reference_cache
```

### 6.2 Table definitions

#### `users`

| Column | Type | Description |
|--------|------|-------------|
| `id` | `uuid` PK | Internal ID |
| `external_user_id` | `text` UNIQUE | LINE userId or mobile app user ID |
| `preferred_name` | `text` | Patient's preferred name (display only) |
| `age_years` | `int` | Optional |
| `gender` | `text` | `female` / `male` / `non_binary` / `prefer_not_say` / `other` |
| `emergency_contact` | `text` | Free text (not sent to LLM) |
| `health_notes` | `text` | Patient-entered notes (not sent to LLM) |
| `timezone` | `text` | IANA timezone (default `Asia/Taipei`) |
| `onboarding_completed_at` | `timestamptz` | Set when onboarding is saved |
| `created_at` | `timestamptz` | Row creation |
| `updated_at` | `timestamptz` | Last update |

#### `medications`

| Column | Type | Description |
|--------|------|-------------|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `users` | |
| `name` | `text` | Drug name (as user entered / LLM extracted) |
| `dosage` | `text` | e.g. "100mg" |
| `schedule` | `text` | Free-text schedule (e.g. "after meals daily") |
| `instructions_zh` | `text` | Optional Chinese instructions from LLM grounding |
| `raw_metadata` | `jsonb` | Full structured LLM extraction output |
| `created_at` | `timestamptz` | |
| `updated_at` | `timestamptz` | |

#### `conversation_turns`

| Column | Type | Description |
|--------|------|-------------|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `users` | |
| `role` | `text` | `user` or `assistant` |
| `content` | `text` | Original (un-redacted) message text |
| `created_at` | `timestamptz` | Used for ordering |

> Note: The `content` stored here is the **original** user message, not the LLM-redacted copy. Only the copy passed to the LLM adapter is redacted.

#### `dose_events`

| Column | Type | Description |
|--------|------|-------------|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `users` | |
| `medication_id` | `uuid` FK → `medications` | |
| `scheduled_at` | `timestamptz` | When the dose is due (UTC) |
| `taken_at` | `timestamptz` | Optional adherence tracking (not required by reminder job) |
| `reminder_sent_at` | `timestamptz` | Set after successful LINE push (idempotency) |
| `created_at` | `timestamptz` | |

#### `drug_reference_cache`

Shared across all users. Caches drug label data fetched from OpenFDA / TFDA.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `uuid` PK | |
| `source` | `text` | `openfda` / `tfda` / etc. |
| `query_key` | `text` | Normalized drug name used for lookup |
| `title` | `text` | Drug display name |
| `body_zh` | `text` | Patient-facing Chinese summary |
| `indications` | `text` | Indications and usage |
| `raw_payload` | `jsonb` | `{"label": <full FDA label object>}` |
| `expires_at` | `timestamptz` | TTL (configurable via `MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS`, default 168h) |
| `created_at` | `timestamptz` | |

#### `drug_personalization_cache`

Per-user, per-query cached LLM reply for explain/interaction intents.

| Column | Type | Description |
|--------|------|-------------|
| `id` | `uuid` PK | |
| `user_id` | `uuid` FK → `users` | |
| `medication_id` | `uuid` FK → `medications` | Optional — when reply relates to one med |
| `reference_cache_id` | `uuid` FK → `drug_reference_cache` | Optional — the grounding source |
| `query_fingerprint` | `text` | SHA hash of (redacted query + de-identified med list context) |
| `intent` | `text` | `explain_medication` or `interaction_check` |
| `personalized_text` | `text` | The cached LLM reply |
| `locale` | `text` | `zh-TW` / `en` |
| `llm_meta` | `jsonb` | `{"source": "openfda"/"gemini-2.5-flash"/"mock_llm"}` |
| `expires_at` | `timestamptz` | TTL (configurable via `MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS`, default 72h) |
| `created_at` | `timestamptz` | |

Unique constraint: `(user_id, query_fingerprint)`.

---

## 7. API reference

### 7.1 Shared / ops

#### `GET /health`

Plain-text liveness check. Returns `200 OK` with body `"ok"`. Used by Docker health checks and load balancers.

#### `GET /internal-media/{file_id}`

Serves short-lived TTS audio files generated for LINE voice replies. Requires `PUBLIC_BASE_URL` to be set so LINE can fetch this URL. Files are deleted after TTL by `LocalPublicObjectStorage`.

#### `POST /internal/reminders/reconcile`

**Auth:** `X-Cron-Secret: <MEDBUDDY_CRON_SECRET>` header.

Re-enqueues immediate arq jobs for `dose_events` rows that are due (`scheduled_at <= now()`), `reminder_sent_at IS NULL`, and `taken_at IS NULL`. Safety net after Redis or worker restarts. Recommended cron frequency: every 15–60 minutes.

**Response:** `{"enqueued": <count>}`

---

### 7.2 LINE channel

#### `POST /v1/line/webhook`

**Auth:** `X-Line-Signature` HMAC-SHA256 header (verified with `LINE_CHANNEL_SECRET`). Skipped in mock mode when `LINE_CHANNEL_SECRET` is unset.

**Body:** Standard [LINE webhook event object](https://developers.line.biz/en/reference/messaging-api/#webhook-event-objects).

Supported events:

| Event type | Behavior |
|------------|---------|
| `follow` | Create user record; send welcome message from i18n |
| `message` (text) | Run assistant pipeline; reply with text |
| `message` (audio) | STT → assistant pipeline → optional TTS reply |

**Response:** `200 OK` (empty body — LINE requires a 200 ACK).

---

### 7.3 Mobile app (`/v1/app`)

All authenticated endpoints require:
- `X-App-User-Id: <stable-id>` — 4–128 character string, stable per install or account.
- `Authorization: Bearer <MEDBUDDY_MOBILE_BEARER_TOKEN>` — required in production (`MEDBUDDY_MOBILE_BEARER_TOKEN` set); optional when `MOCK_EXTERNAL_SERVICES=true`.

#### `GET /v1/app/health`

No auth. Returns JSON health.

```json
{"status": "ok", "version": "..."}
```

#### `GET /v1/app/info`

No auth. Returns public service metadata (non-secret).

```json
{"service": "medbuddy-api", "locale": "zh-TW", "features": [...]}
```

#### `GET /v1/app/me`

Auth required. Returns user profile.

```json
{
  "app_user_id": "device-abc123",
  "preferred_name": "...",
  "age_years": 68,
  "gender": "female",
  "emergency_contact": "...",
  "health_notes": "...",
  "onboarding_completed_at": "2026-04-01T10:00:00Z"
}
```

#### `POST /v1/app/onboarding`

Auth required. Saves first-run profile.

**Request body:**
```json
{
  "preferred_name": "...",       // required
  "age_years": 68,               // optional
  "gender": "female",            // optional: female|male|non_binary|prefer_not_say|other
  "emergency_contact": "...",    // optional
  "health_notes": "..."          // optional
}
```

**Response:** same shape as `GET /me`.

#### `POST /v1/app/messages`

Auth required. Single chat turn.

**Request body:**
```json
{"text": "阿斯匹靈可以跟抗凝血藥一起吃嗎？"}
```

`text` must be 1–8000 characters.

**Response:**
```json
{"reply": "..."}
```

#### `GET /v1/app/summary`

Auth required. Returns a structured doctor-ready health summary.

**Response:**
```json
{
  "main_concern": "...",
  "symptoms": "...",
  "vitals": null,
  "medication_changes": "...",
  "questions_for_doctor": "...",
  "carer_note": null
}
```

Generated by `GenerateHealthSummaryTool` using `compose_reply` with a summary-focused prompt. The Expo app also stores a local draft of this in AsyncStorage.

---

## 8. LLM integration

### 8.1 Provider

**Google Gemini** via the `google-genai` SDK (`genai.Client` + `models.generate_content`).

- **Default model:** `gemini-2.5-flash` (configurable via `GEMINI_MODEL`).
- **Install:** `pip install 'medbuddy-api[llm]'` (included in the Docker image).

### 8.2 LLMPort interface

```python
class LLMPort(Protocol):
    async def classify_intent(self, user_text: str, locale: str) -> Intent: ...
    async def compose_reply(
        self, system_persona: str, patient_context: str,
        history: list[ConversationTurn], user_message: str,
        grounding: str | None = None,
        extra_system: str | None = None,
    ) -> str: ...
    async def extract_medication_draft(self, user_text: str, locale: str) -> MedicationDraft: ...
    async def resolve_medication_removal_id(
        self, user_text: str, medications: list[MedicationRecord], locale: str
    ) -> str | None: ...
    async def compose_medication_added_reply(self, ...) -> str: ...
    async def simplify_drug_text_to_patient_zh(self, raw_label: str) -> str: ...
```

### 8.3 Prompt construction

All prompts follow the same pattern:

1. **System persona** (`get_system_persona(locale)`) — locale-specific role description from `locales/*.json` key `prompts.system_persona`. Instructs the model to be helpful but not a substitute for professional advice, and never to invent or echo PII.

2. **Patient context block** (`build_patient_context_for_llm(user, medications)`) — de-identified signals:
   - "preferred name on file" (without the actual name)
   - Age band (e.g. "60s") rather than exact age
   - Medication list lines (name, dosage, schedule)
   - **Not included:** raw `preferred_name`, `health_notes`, `emergency_contact`, exact `age_years`

3. **Drug grounding** (for explain/interaction/add): OpenFDA label snippets (indications, dosage, warnings) or `None`.

4. **Conversation history** (redacted): recent `ConversationTurn` objects.

5. **User message** (redacted): the current turn after `redact_pii_text()`.

6. **Extra system** (for specific intents): e.g. interaction-check companion instructions, summary format instructions.

### 8.4 Structured outputs

For extraction tasks, Gemini is called with structured output schemas (`llm/schemas.py`):

| Schema | Used for |
|--------|---------|
| `IntentClassification` | `classify_intent` — returns `Intent` enum value |
| `MedicationDraftOutput` | `extract_medication_draft` — name, dosage, schedule, instructions_zh |
| `MedicationRemovalOutput` | `resolve_medication_removal_id` — which med ID to delete |
| `HealthSummaryOutput` | `GenerateHealthSummaryTool` — structured doctor summary |

### 8.5 Mock LLM

`integrations/mocks/llm.py` implements `LLMPort` with deterministic rule-based responses:
- Intent classification based on keyword matching.
- `compose_reply` returns fixed i18n strings.
- `extract_medication_draft` parses simple patterns.

This enables running the full stack and all tests without a Gemini API key.

---

## 9. Caching strategy

### 9.1 Drug reference cache (`drug_reference_cache`)

**Purpose:** Avoid repeated OpenFDA HTTP calls for the same drug name.

**Scope:** Shared across all users.

**Key:** `(source, query_key)` where `query_key` is the normalized drug name.

**Storage:** `CachingDrugData` wraps `DrugDataPort`. On cache miss, fetches from OpenFDA, stores full label fields + `raw_payload`, sets `expires_at = now() + MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS` (default 168h / 7 days).

**Without Supabase:** cache is bypassed; every request hits OpenFDA directly.

### 9.2 Drug personalization cache (`drug_personalization_cache`)

**Purpose:** Avoid repeated LLM compose calls for the same patient context + query.

**Scope:** Per user.

**Key:** `query_fingerprint` = SHA-256 hash of:
- Redacted user query text
- De-identified patient context string (medication list snapshot)
- Intent name
- Locale

This means the cache invalidates naturally when the patient's medication list changes (different hash).

**Storage:** `SupabaseDrugCaches`. On cache hit, returns stored `personalized_text` and appends conversation turns. On miss, runs full drug grounding + LLM compose, then upserts the result. TTL: `MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS` (default 72h / 3 days).

**Which intents use it:** `explain_medication` and `interaction_check` only. `add_medication` acknowledgment does not use this cache (each add is unique).

**`llm_meta.source` field values:**
- `"openfda"` — reply was grounded with OpenFDA label data
- `"tfda"` — reply grounded with TFDA data (not yet implemented in HTTP adapter)
- `"gemini-2.5-flash"` (or configured model name) — LLM-only grounding, no registry data
- `"mock_llm"` — returned by mock adapter in tests

---

## 10. Privacy and security

### 10.1 PII handling before LLM calls

| Data | Treatment |
|------|-----------|
| User message (current turn) | `redact_pii_text()` applied before `classify_intent`, `compose_reply`, and extraction calls |
| Conversation history | `redact_conversation_turns_for_llm()` applied — same patterns |
| Profile fields | Sent as coarse signals only (`build_patient_context_for_llm`): no raw name, exact age, health notes, or emergency contact |
| Profile extraction from chat | `parse_profile_patch_from_text()` — local heuristics, **no LLM call** for profile fields |

**Redaction patterns** (`privacy/redact.py`):
- Email addresses (standard RFC 5322-ish pattern)
- Taiwan mobile patterns: `09xx-xxxxxx`, `09xxxxxxxx`, and CJK-adjacent digit runs
- Long digit runs (10+ consecutive digits, e.g. ID numbers, account numbers)

**Replacement:** `[…]` placeholder. The system prompt instructs the model that `[…]` represents masked content and not to invent values for it.

**Limits:** Names, addresses, free-form clinical details in user messages, and many international phone formats are not masked. Treat LLM prompts as containing potentially sensitive free text.

### 10.2 LINE webhook authentication

`channels/line/signature.py` implements HMAC-SHA256 verification of the `X-Line-Signature` header using `LINE_CHANNEL_SECRET`. Verification is skipped only when `LINE_CHANNEL_SECRET` is empty **and** `MOCK_EXTERNAL_SERVICES=true` (local development).

### 10.3 Mobile API authentication

Two-factor check on `/v1/app/*` protected routes:
1. `X-App-User-Id` header — 4–128 character stable string.
2. `Authorization: Bearer <MEDBUDDY_MOBILE_BEARER_TOKEN>` — constant token (shared secret).

When `MEDBUDDY_MOBILE_BEARER_TOKEN` is unset and `MOCK_EXTERNAL_SERVICES=true`, Bearer is optional (development mode only).

**Note:** The mobile auth is a single shared bearer token, not per-user credentials. For a production deployment, consider rotating to per-user tokens or OAuth.

### 10.4 Supabase access

The backend uses **`SUPABASE_PUBLISHABLE_KEY`** (anon key) — never the `service_role` key. All tables have RLS policies restricting `anon` role access. Row-level isolation relies on `external_user_id` matching in application code; Supabase RLS is an additional safety net.

### 10.5 Internal endpoints

`POST /internal/reminders/reconcile` is protected by `X-Cron-Secret` matching `MEDBUDDY_CRON_SECRET`. This endpoint and `/internal-media/{id}` are not intended for public client use.

### 10.6 Production safeguards

When `RENDER=true` (Render web service), `config.py` enforces:
- `MOCK_EXTERNAL_SERVICES = false`
- `DEBUG = false`
- `MEDBUDDY_INTEGRATION` forced to `real` (even if set to `mock` in dashboard)

This prevents accidental mock mode in production.

### 10.7 Logging policy

- Raw user message text is **not** logged (structured INFO logs record user key, intent, med count only).
- Full LLM prompts and tokens are **not** logged by default.
- `LOG_LEVEL=DEBUG` may log additional context — review before enabling in production.

---

## 11. Observability

| Signal | Source | Notes |
|--------|--------|-------|
| **Liveness** | `GET /health` (plain text) | Used by Docker / Render health checks |
| **JSON health** | `GET /v1/app/health` | Used by mobile client |
| **Structured logs** | `configure_logging()` in `logging_config.py` | `medbuddy.*` namespace; level set by `LOG_LEVEL` |
| **Webhook logs** | `channels/line/orchestrator.py` | Event type, step, reply size — no raw text |
| **Turn logs** | `application/assistant_turn.py` | `user_key`, `med_count`, per-med flat line |

The `uvicorn.error` logger is configured at the same `LOG_LEVEL`. Access logs (`uvicorn.access`) can be enabled separately.

No distributed tracing or metrics (Prometheus/OTLP) are implemented in the current codebase. Recommended additions for production: request ID propagation, error rate metrics on intent classification and LLM calls.

---

## 12. Deployment topology

### 12.1 Single-container (default, Render)

The repo-root `Dockerfile` (Python 3.12-slim-bookworm) installs all extras (`[llm,supabase,tts,reminders]`). The entrypoint `docker-entrypoint-web.sh` runs:
- **uvicorn** — always.
- **`arq medbuddy.reminders.worker.WorkerSettings`** — only when `REDIS_URL` is non-empty.

Both processes share the same container and environment. This is the default for Render and `make be-compose`.

```
┌────────────────────────────────────────┐
│  Docker container (medbuddy-api)       │
│                                        │
│   uvicorn (port $PORT)                 │
│   arq worker (when REDIS_URL set)      │
│                                        │
│   shared env: LINE, Gemini, Supabase,  │
│   REDIS_URL                            │
└────────────────────────────────────────┘
         │                  │
         ▼                  ▼
    Supabase           Redis
    (Postgres)         (managed)
```

### 12.2 Split-process (scale-out)

When reminder processing needs to scale independently, run two services from the same image:

```
┌─────────────────────────┐   ┌─────────────────────────┐
│  medbuddy-api (web)     │   │  medbuddy-worker         │
│  CMD: uvicorn           │   │  CMD: arq worker         │
│  (no arq)               │   │  (no uvicorn)            │
└────────────┬────────────┘   └────────────┬────────────┘
             │                             │
             └─────────────┬───────────────┘
                           ▼
                         Redis
```

**Important:** Do not run arq in both containers — it would double-deliver reminders.

### 12.3 Local Docker Compose

```bash
# API only (no Redis/reminders):
podman compose up --build

# API + Redis + arq worker (reminders profile):
REDIS_URL=redis://redis:6379 podman compose --profile reminders up --build
```

Defined in `compose.yaml`. The `reminders` profile adds a Redis service; the API container's entrypoint auto-starts arq when `REDIS_URL` is set.

### 12.4 Render blueprint

`render.yaml` defines `medbuddy-api` as a web service using the repo-root `Dockerfile`. Steps:

1. Dashboard → New → Blueprint → connect repo → apply `render.yaml`.
2. Create Render Key Value → set `REDIS_URL` on `medbuddy-api`.
3. Set environment secrets: `LINE_CHANNEL_*`, `GEMINI_API_KEY`, Supabase keys, `MEDBUDDY_MOBILE_BEARER_TOKEN`, `PUBLIC_BASE_URL`, optionally `MEDBUDDY_CRON_SECRET`.
4. Set LINE webhook URL: `{PUBLIC_BASE_URL}/v1/line/webhook`.

---

## 13. Configuration reference

All settings are in `config.py` (Pydantic `BaseSettings`). Sources, in priority order: `MEDBUDDY_INTEGRATION` env → `apps/backend/.env` → working directory `.env`.

### 13.1 Integration mode

| Variable | Values | Default | Notes |
|----------|--------|---------|-------|
| `MEDBUDDY_INTEGRATION` | `mock` / `real` | (unset) | Overrides `MOCK_EXTERNAL_SERVICES`. Aliases: `local`/`dev` → mock; `live`/`production` → real. |
| `MOCK_EXTERNAL_SERVICES` | `true` / `false` | `false` | Fallback when `MEDBUDDY_INTEGRATION` is unset. |

### 13.2 LINE

| Variable | Required for | Notes |
|----------|-------------|-------|
| `LINE_CHANNEL_SECRET` | Webhook signature verification | Skip verification if unset + mocks enabled |
| `LINE_CHANNEL_ACCESS_TOKEN` | Replies + push | |

### 13.3 LLM

| Variable | Default | Notes |
|----------|---------|-------|
| `GEMINI_API_KEY` | — | Required for real LLM |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Override with any compatible model ID |

### 13.4 Storage and speech

| Variable | Default | Notes |
|----------|---------|-------|
| `PUBLIC_BASE_URL` | `http://localhost:8000` | HTTPS base URL for LINE-accessible audio |
| `WHISPER_SERVICE_URL` | — | HTTP endpoint for external Whisper STT |

### 13.5 Supabase

| Variable | Notes |
|----------|-------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` or `SUPABASE_ANON_KEY` | Anon key only — never service_role |

### 13.6 Reminders

| Variable | Default | Notes |
|----------|---------|-------|
| `REDIS_URL` | — | DSN for arq; enables worker when set |
| `MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME` | `09:00` | `HH:MM` local time for daily reminders |
| `MEDBUDDY_REMINDER_HORIZON_DAYS` | `14` | Days ahead to materialize dose events (max 90) |
| `MEDBUDDY_CRON_SECRET` | — | Header secret for reconcile endpoint |

### 13.7 Caching

| Variable | Default | Notes |
|----------|---------|-------|
| `MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS` | `168` | 7 days; shared drug label cache |
| `MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS` | `72` | 3 days; per-user LLM reply cache |

### 13.8 General

| Variable | Default | Notes |
|----------|---------|-------|
| `MEDBUDDY_LOCALE` | `zh-TW` | Server locale for i18n |
| `MEDBUDDY_MOBILE_BEARER_TOKEN` | — | Bearer token for `/v1/app` protected routes |
| `LOG_LEVEL` | `INFO` | `medbuddy.*` and `uvicorn.error` log level |
| `DEBUG` | `false` | Enable FastAPI debug mode |
| `PORT` | `8000` | Injected by Render at runtime |
| `RENDER` | — | Set by Render; triggers production safety overrides |

---

## 14. Extension points

### 14.1 Intent hooks

`extensibility/intent_hooks.py` allows registering functions that intercept specific intents **before** the medication handlers and `compose_reply`. A hook that returns a non-empty string short-circuits the normal pipeline.

Useful for:
- Pilot features that need to intercept a specific intent without forking channel routing.
- A/B testing reply variants.
- Routing specific intents to specialized downstream services.

### 14.2 Adding a new LLM adapter

1. Implement `LLMPort` in a new file under `integrations/`.
2. Register it in `container.py`'s `build_app_services()` under the appropriate condition.
3. No changes needed in `application/` or `agents/`.

### 14.3 Adding a new delivery channel

1. Implement a channel router under `channels/<name>/`.
2. Mount it in `main.py`.
3. Call `run_assistant_text_turn(user_key, user_text, services)` — same as LINE and mobile.
4. Implement channel-specific auth and reply formatting in the channel module.

### 14.4 Adding a new agent tool

1. Subclass `AgentTool` in `agents/tools/`.
2. Implement `execute(context: AgentContext) -> ToolResult`.
3. Register the tool for the relevant `Intent` values in `MedicationAgent`.

---

## 15. Non-goals and known limitations

| Item | Status |
|------|--------|
| **Clinical diagnosis** | Explicitly out of scope. Prompts instruct the model to defer to clinicians. |
| **Full TFDA API** | `HttpDrugData.fetch_tfda_snippet()` returns `None` until a live TFDA client is implemented. `source=tfda` rows are not created from placeholder data. |
| **NLP on free-text schedule** | Reminder v1 uses a single daily time per user. Free-text schedule is echoed in copy but does not drive multiple reminders per day. |
| **Expo local notifications** | Dose reminders are LINE push only. Expo notifications are not implemented. |
| **Rich LINE Flex messages** | Reminder messages are plain text. No "mark taken" postback in v1. |
| **Per-user bearer tokens** | The mobile API uses a single shared bearer token. Per-user auth would require a user identity system. |
| **Expo hold-to-talk → backend STT** | Prototype only — shows alert after recording. Backend STT is wired for LINE voice; keyboard dictation or LINE are the intended voice paths. |
| **`dose_events.taken_at`** | Column exists for future adherence tracking but is not populated by the current assistant flows. |
| **Full PHI scrubbing** | Redaction is pattern-based (emails, phone numbers, digit runs). Names, addresses, and free-form clinical text in user messages are not masked. |
| **Distributed tracing / metrics** | Not implemented. Recommended for production observability hardening. |

---

*For narrated user flows and example utterances, see [`use-cases.md`](use-cases.md). For PII and LLM boundaries in detail, see [`privacy.md`](privacy.md). For dose reminder architecture, see [`reminders.md`](reminders.md).*
