# MedBuddy — Technical Design Document

> **Disclaimer:** MedBuddy is a software prototype and is not a substitute for professional medical advice.
>
> **Documentation index:** [`docs/index.md`](index.md) — reading paths and quick lookup for all docs.

---

## Table of contents

1. [System overview](#1-system-overview)
2. [Architecture principles and decisions](#2-architecture-principles-and-decisions)
3. [Backend component map](#3-backend-component-map)
4. [Request flows](#4-request-flows)
5. [Agent layer](#5-agent-layer)
6. [Data model](#6-data-model)
7. [API reference](#7-api-reference)
8. [LLM integration](#8-llm-integration)
9. [Caching strategy](#9-caching-strategy)
10. [Privacy and security](#10-privacy-and-security)
11. [Error handling and resilience](#11-error-handling-and-resilience)
12. [Observability](#12-observability)
13. [Testing strategy](#13-testing-strategy)
14. [Deployment topology](#14-deployment-topology)
15. [Configuration reference](#15-configuration-reference)
16. [Extension points](#16-extension-points)
17. [Quality attributes and prototype SLOs](#17-quality-attributes-and-prototype-slos)
18. [Known limitations and future work](#18-known-limitations-and-future-work)

---

## 1. System overview

MedBuddy helps patients manage medications and ask medication-related questions. The **primary product** (this document's focus) is **LINE Messaging** plus the **FastAPI** backend — webhooks, dose reminder push, and an **HTTP API** for integrations and tests. A **reference Expo app** (`apps/frontend/`) exists as a future surface; it is not a co-equal channel in this phase (see [`frontend-expo.md`](frontend-expo.md)).

**Prototype scope:** Text-in, text-out only. LINE audio (STT/TTS) code paths exist for engineering exploration but are not part of prototype product acceptance.

| Channel | Entry point | Role |
|---------|-------------|------|
| **LINE Messaging API** | `POST /v1/line/webhook` | Primary user channel: text chat, dose reminder push |
| **Standalone HTTP API** | `POST /v1/app/*` | Same assistant and persistence; no LINE dependency |
| **Expo app (reference)** | Uses `/v1/app/*` when API mode is on | Future product — see [`frontend-expo.md`](frontend-expo.md) |

### System context diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client layer                             │
│                                                                 │
│   LINE platform           HTTP clients (integrations, tests,    │
│   (webhook, push)         optional reference mobile app)        │
└──────────┬────────────────────────────┬─────────────────────────┘
           │                            │
           ▼                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI backend                            │
│                                                                 │
│  /v1/line/webhook             /v1/app/*                         │
│  channels/line/               channels/mobile/                  │
│        │                            │                           │
│        └──────────────┬─────────────┘                           │
│                       ▼                                         │
│           application/assistant_turn.py                         │
│                       │                                         │
│                       ▼                                         │
│           agents/MedicationAgent                                │
│           (intent → tool dispatch)                              │
│                       │                                         │
│          ┌────────────┼─────────────────┐                       │
│          ▼            ▼                 ▼                       │
│    medication     drug lookup      health summary               │
│    tools          tools            tools                        │
│          │            │                 │                       │
│          └────────────┴─────────────────┘                       │
│                       │                                         │
│              protocols/ports.py  ← hexagonal boundary           │
│          ┌────────────┼─────────────────┐                       │
│          ▼            ▼                 ▼                       │
│   LLM (Gemini/OpenAI) Supabase     OpenFDA HTTP                 │
│   (or mock)           (or in-mem)   (or mock)                   │
└─────────────────────────────────────────────────────────────────┘
           │                            │
           ▼                            ▼
      Redis + arq                  LINE push API
   (dose reminders)                (reminder delivery)
```

---

## 2. Architecture principles and decisions

### 2.1 Hexagonal architecture (ports & adapters)

**Decision:** Business logic lives in `application/` and `agents/`. These layers depend only on `protocols/` interfaces (Python `Protocol` classes). `container.py` wires concrete adapters at startup.

```
application/  ──► protocols/ports.py  ◄──  integrations/
agents/             (abstract)               (concrete or mock)
```

**Rationale:**
- Tests inject mock adapters without monkey-patching.
- Swapping an LLM provider (Gemini → OpenAI) requires only a new adapter implementing `LLMPort`.
- Adding a delivery channel (e.g. WhatsApp) requires a new channel module calling the same `run_assistant_text_turn` entry point — no changes to agent or tool code.

**Trade-off accepted:** Protocol interfaces add a layer of indirection that is extra overhead for simple operations. This cost is accepted because the integrations (LLM, Supabase, LINE, OpenFDA) are the most likely points of change.

### 2.2 Agent-dispatch pattern

**Decision:** `MedicationAgent` maps each classified intent to a typed tool subclass and calls `tool.run(...)`. Tools are responsible for exactly one operation and return a `ToolResult`.

**Rationale:** Keeps `application/assistant_turn.py` thin — it classifies intent, builds context, delegates to the agent, and persists the turn. Each tool can be tested in isolation.

**Trade-off accepted:** A single LLM call classifies intent before tool dispatch, adding ~200–400ms latency per turn. This is preferable to a multi-step chain LLM approach for the prototype's bounded intent set.

### 2.3 Mock-first development

**Decision:** Every external dependency has a mock adapter in `integrations/mocks/`. Default local dev mode (`MEDBUDDY_INTEGRATION=mock`) uses all mocks — no API keys or running databases required.

**Rationale:** CI and local development must be zero-friction. The mock adapters exercise real application logic (not stubs that always succeed), catching integration contract violations before they reach production.

### 2.4 Single-table LLM intent classification

**Decision:** A single structured `interpret_user_turn` call classifies intent and extracts adherence fields per user turn. There is no multi-step "chain of thought" pipeline.

**Rationale:** For a closed intent set (15 intents), single-call classification is cheaper, faster, and easier to test than agentic chains. A future open-domain expansion may revisit this.

### 2.5 Text-only prototype acceptance

**Decision:** Product acceptance is defined on text paths only. Voice (STT/TTS) code paths are present for engineering exploration but are explicitly excluded from prototype acceptance criteria.

**Rationale:** Reduces test surface, makes safety-copy review tractable, and provides a clear ceiling for what "works" before adding voice latency, failure modes, and accessibility expectations.

---

## 3. Backend component map

```
apps/backend/src/medbuddy/
│
├── main.py                      # FastAPI app; mounts routers; lifespan setup
├── config.py                    # Pydantic Settings; .env loading; Render safety overrides
├── container.py                 # build_app_services() — wires all adapters from config
├── deps.py                      # FastAPI get_services() dependency injection
├── exceptions.py                # MedBuddyError, LLMParseError (domain exceptions)
├── i18n.py                      # t() — key lookup with zh-TW fallback
├── logging_config.py            # configure_logging() — structured logging setup
│
├── channels/                    # ← Inbound adapters (Layer: Driving/Primary)
│   ├── line/
│   │   ├── routes.py            # POST /v1/line/webhook
│   │   ├── orchestrator.py      # handle_line_event() — event dispatch and reply
│   │   └── signature.py         # X-Line-Signature HMAC-SHA256 verification
│   └── mobile/
│       ├── routes.py            # GET/POST /v1/app/*
│       ├── auth.py              # MobileAuthContext, require_mobile_auth()
│       └── schemas.py           # Pydantic I/O models
│
├── application/                 # ← Application core (Layer: Use Cases)
│   ├── assistant_turn.py        # run_assistant_text_turn() — main entry point
│   └── profile_intents.py       # Profile update intent handling (LLM profile patch)
│
├── agents/                      # ← Domain logic (Layer: Domain)
│   ├── medication_agent.py      # MedicationAgent — intent→tool dispatch
│   ├── base.py                  # AgentTool base class, ToolResult
│   └── tools/
│       ├── medication_crud.py   # List/Add/Update/RemoveMedicationTool
│       ├── drug_lookup.py       # ExplainMedicationTool
│       ├── interaction_check.py # InteractionCheckTool
│       ├── health_summary.py    # GenerateHealthSummaryTool
│       ├── report_missed_dose.py # ReportMissedDoseTool
│       ├── confirm_dose.py      # ConfirmDoseTool (adherence marking)
│       ├── log_vital.py         # LogVitalTool
│       └── side_effects.py      # ReportSideEffectsTool
│
├── models/
│   └── domain.py                # Intent enum, MedicationDraft/Record, ConversationTurn
│
├── protocols/                   # ← Port interfaces (Layer: Ports)
│   ├── ports.py                 # LLMPort, UserDataPort, LineMessagingPort, DrugDataPort, etc.
│   └── drug_caches.py           # DrugCachesPort
│
├── engine/
│   └── types.py                 # AppServices dataclass — dependency injection container
│
├── integrations/                # ← Outbound adapters (Layer: Driven/Secondary)
│   ├── llm/
│   │   ├── gemini_llm.py        # GeminiLLM (google-genai)
│   │   └── openai_llm.py        # OpenAILLM (Chat Completions)
│   ├── line_client.py           # LineHttpClient (line-bot-sdk)
│   ├── supabase_stores.py       # SupabaseUserData, SupabaseConversationStore
│   ├── supabase_drug_caches.py  # SupabaseDrugCaches
│   ├── drugs_http.py            # HttpDrugData (OpenFDA + TFDA stub)
│   ├── caching_drugs.py         # CachingDrugData (cache wrapper around DrugDataPort)
│   ├── stt_google.py            # GoogleSpeechToText (engineering exploratory, not prototype)
│   ├── edge_tts_service.py      # EdgeTtsService (engineering exploratory, not prototype)
│   ├── local_public_storage.py  # LocalPublicObjectStorage (temp audio)
│   └── mocks/                   # MockLLM, MockLineClient, MockUserData, etc.
│
├── privacy/
│   └── redact.py                # redact_pii_text(), redact_conversation_turns_for_llm()
│
├── prompts/
│   └── persona.py               # get_system_persona(), build_patient_context_for_llm()
│
├── llm/
│   ├── schemas.py               # Pydantic models for structured LLM outputs
│   ├── intent_classification_prompt.py  # Shared intent classification prompt
│   └── turn_interpretation.py   # IntentClassification → TurnInterpretation mapping
│
├── reminders/
│   ├── worker.py                # arq WorkerSettings
│   ├── deliver.py               # deliver_dose_reminder() → LINE push
│   ├── enqueue.py               # enqueue_reminder_jobs()
│   ├── dose_schedule.py         # gen_dose_events() — local time → UTC instants
│   └── lifecycle.py             # sync_and_enqueue_reminders() — called after add/remove
│
├── extensibility/
│   └── intent_hooks.py          # try_intent_hooks() — pilot feature hook registry
│
├── http/
│   └── shared_routes.py         # /health, /internal-media/{id}, /internal/reminders/reconcile
│
└── locales/
    ├── zh-TW.json               # Primary locale (Traditional Chinese, Taiwan)
    └── en.json                  # English
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
    │ verify_signature()  ← 400 if invalid in real mode
    │ parse_event()
    ▼
channels/line/orchestrator.py
    │ handle_line_event(event, services)
    ▼
application/assistant_turn.py
    │ run_assistant_text_turn(user_key=line_user_id, user_text)
    │   1. Load user profile + medication list + recent turns
    │   2. redact_pii_text(user_text)
    │   3. LLMPort.interpret_user_turn(redacted_text, recent_context)
    │      → TurnInterpretation (intent + adherence slots)
    │   4. Persist user turn (original text, not redacted)
    │   5. Dispatch: hooks → off_topic → profile → tool → compose_reply fallback
    │   6. Persist assistant turn
    ▼
channels/line/orchestrator.py
    │ line_client.reply_message(reply_token, reply_text)
    ▼
LINE platform (reply)
```

### 4.2 Standalone HTTP chat message (`POST /v1/app/messages`)

```
HTTP client
    │ POST /v1/app/messages
    │ Authorization: Bearer <token>
    │ X-App-User-Id: <stable-id>
    │ Body: {"text": "..."}
    ▼
channels/mobile/routes.py
    │ require_mobile_auth()  ← 401 if token mismatch or header missing
    │ validate body (1–8000 chars)
    ▼
application/assistant_turn.py
    │ run_assistant_text_turn(user_key=app_user_id, user_text)
    │   (same pipeline as LINE text — §4.1 steps 1–6)
    ▼
channels/mobile/routes.py
    │ return {"reply": reply_text}
    ▼
HTTP client
```

### 4.3 Dose reminder delivery (background)

```
AddMedicationTool / RemoveMedicationTool success
    │ sync_and_enqueue_reminders()
    ▼
reminders/lifecycle.py
    │ sync_upcoming_dose_events(line_user_id)
    │   DELETE future dose_events for patient
    │   INSERT new rows (one per med per scheduled time per day in horizon)
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
    │ get_dose_event_for_reminder(dose_id)  ← skip if already sent or taken
    │ line_client.push_message(line_user_id, reminder_text)
    │ try_mark_reminder_sent(dose_id)        ← idempotency guard
```

**Reconcile safety net:** `POST /internal/reminders/reconcile` (cron-triggered) re-enqueues any `dose_events` where `scheduled_at <= now()`, `reminder_sent_at IS NULL`, and `taken_at IS NULL`. Covers cases where the arq worker was down when the job was due.

### 4.4 LINE audio message (engineering exploratory — not prototype acceptance)

```
LINE platform
    │ POST /v1/line/webhook  (audio message event)
    ▼
channels/line/orchestrator.py
    │ download_message_content(message_id)     # LINE blob API
    │ stt.transcribe(audio_bytes)              # Google Speech-to-Text or mock
    │ run_assistant_text_turn(user_key, transcript)
    │ [if voice reply requested]
    │   tts.synthesize(reply_text) → audio_bytes
    │   storage.save(audio_bytes) → public_url
    │ line_client.reply_message_batch([audio_msg, text_msg])
    ▼
LINE platform (batch reply)
```

> This flow is not part of prototype product acceptance. See `prd.md §2` and `§9 (NG-1)`.

---

## 5. Agent layer

`MedicationAgent` (`agents/medication_agent.py`) implements the agent-dispatch pattern. Given a `TurnInterpretation` from `interpret_user_turn` and execution context, it selects and runs the appropriate `AgentTool`.

### 5.1 Dispatch order

```
TurnInterpretation (intent + adherence slots)
    │
    ├── try_intent_hooks()        → optional short-circuit (pilot feature hooks)
    ├── off_topic                 → fixed i18n refusal string (no LLM compose)
    ├── update_profile            → extract profile patch (LLM) → patch profile
    ├── list_medications          → ListMedicationsTool
    ├── add_medication            → AddMedicationTool
    ├── update_medication         → UpdateMedicationTool
    ├── remove_medication         → RemoveMedicationTool
    ├── report_missed_dose        → ReportMissedDoseTool
    ├── confirm_dose              → if adherence slots set → ConfirmDoseTool; else compose_reply
    ├── explain_medication        → ExplainMedicationTool
    ├── report_side_effects       → ReportSideEffectsTool
    ├── interaction_check         → InteractionCheckTool
    ├── request_summary           → GenerateHealthSummaryTool
    └── log_vital / general_question / unmapped → compose_reply() fallback
```

### 5.2 Tool registry

| Tool | Intent | Key operations |
|------|--------|---------------|
| `ListMedicationsTool` | `list_medications` | Load medication list → i18n formatted reply |
| `AddMedicationTool` | `add_medication` | LLM extract draft → persist → drug grounding → compose acknowledgment → reminder sync |
| `UpdateMedicationTool` | `update_medication` | LLM resolve patch → update → i18n confirm → reminder sync |
| `RemoveMedicationTool` | `remove_medication` | LLM resolve target → delete → i18n confirm → reminder sync |
| `ReportMissedDoseTool` | `report_missed_dose` | Mark latest pending dose window as missed (`missed_at`) |
| `ConfirmDoseTool` | `confirm_dose` | Apply `record_pending_dose_as_taken` / `dose_adherence_note` from interpretation → i18n confirmation |
| `ExplainMedicationTool` | `explain_medication` | Personalization cache check → drug reference fetch → compose → cache save |
| `ReportSideEffectsTool` | `report_side_effects` | Side-effect oriented compose with optional drug grounding |
| `InteractionCheckTool` | `interaction_check` | Drug reference fetch → interaction-focused compose → cache save |
| `LogVitalTool` | `log_vital` | Structured vital extraction → persist vital log → i18n acknowledgment |
| `GenerateHealthSummaryTool` | `request_summary` | Aggregate patient context + history → structured LLM summary output |

### 5.3 Tool interface

```python
# protocols/ports.py (authoritative)
class AgentTool(Protocol):
    name: str
    description: str

    async def run(self, **kwargs: Any) -> ToolResult: ...

@dataclass
class ToolResult:
    reply: str           # Localized reply text sent to user
    structured: Any = None  # Optional structured payload (e.g. summary JSON)
```

Tools receive `AppServices`, `user_key`, `user_text`, `user_row`, `medications`, `history`, `locale`, and intent-specific fields via keyword arguments.

---

## 6. Data model

Schema lives in `apps/backend/supabase/schema.sql`. All tables use UUIDs, UTC timestamps, and Supabase RLS for the `anon` role. Existing deployments need explicit migrations to match schema changes — the SQL file is greenfield DDL only.

### 6.1 Entity-relationship overview

```
patients (1) ──────────────────────── (many) medications
    │                                          │
    │ (many)                                   │ (many)
    ▼                                          ▼
conversation_turns                         dose_events
                                               │
drug_personalization_cache (per-patient)       │ (many)
    │                                          │
    └── (optional FK) ──► drug_reference_cache (shared)
```

### 6.2 Table definitions

#### `patients`

End-user profile rows. `users` is reserved in Supabase; `patients` allows other actor types (staff, caregivers) to be modeled separately in future.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` PK | Internal ID |
| `external_user_id` | `text` UNIQUE | LINE userId or mobile app user ID |
| `preferred_name` | `text` | Display name (not sent raw to LLM) |
| `age_years` | `int` | Optional |
| `gender` | `text` | `female` / `male` / `non_binary` / `prefer_not_say` / `other` |
| `emergency_contact` | `text` | Free text — not sent to LLM |
| `health_notes` | `text` | Patient-entered notes — not sent to LLM |
| `timezone` | `text` | IANA timezone; default `Asia/Taipei`; drives scheduling and push copy |
| `locale` | `text` | `en` or `zh-TW`; default `zh-TW` |
| `onboarding_completed_at` | `timestamptz` | Set when onboarding is saved |
| `created_at` | `timestamptz` | |
| `updated_at` | `timestamptz` | |

#### `medications`

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` PK | |
| `patient_id` | `uuid` FK → `patients` | |
| `name` | `text` | Drug name as user entered / LLM extracted |
| `dosage` | `text` | e.g. "100mg" |
| `schedule` | `text` | Free-text schedule (e.g. "after meals daily") |
| `instructions` | `text` | Optional instructions from LLM extraction |
| `raw_metadata` | `jsonb` | Full structured LLM extraction output (includes reminder prefs) |
| `created_at` | `timestamptz` | |
| `updated_at` | `timestamptz` | |

#### `conversation_turns`

| Column | Type | Notes |
|--------|------|-------|
| `id` | `bigserial` PK | |
| `patient_id` | `uuid` FK → `patients` | |
| `role` | `text` | `user` or `assistant` |
| `content` | `text` | **Original** (un-redacted) message text |
| `created_at` | `timestamptz` | Ordering key |

> Only the copy passed to the LLM adapter is redacted. The stored `content` is the original message.

#### `dose_events`

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` PK | |
| `patient_id` | `uuid` FK → `patients` | |
| `medication_id` | `uuid` FK → `medications` | |
| `scheduled_at` | `timestamptz` | When the dose is due (UTC) |
| `taken_at` | `timestamptz` | Set when user confirms dose taken |
| `missed_at` | `timestamptz` | Set when user reports missed dose |
| `reminder_sent_at` | `timestamptz` | Set after successful LINE push (idempotency guard) |
| `reminder_nudge_count` | `integer` | Follow-up nudge count |
| `last_nudge_at` | `timestamptz` | Last nudge push time (UTC) |
| `notes` | `text` | Optional note when marking taken |
| `created_at` | `timestamptz` | |

#### `drug_reference_cache`

Shared across all users. Caches drug label data from OpenFDA / TFDA.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` PK | |
| `source` | `text` | `openfda` / `tfda` / etc. |
| `query_key` | `text` | Normalized drug name |
| `title` | `text` | Drug display name |
| `usage_text` | `text` | Patient-facing usage summary |
| `indications_and_usage` | `text` | |
| `dosage_and_administration` | `text` | |
| `warnings` | `text` | |
| `raw_payload` | `jsonb` | Full FDA label object |
| `fetched_at` | `timestamptz` | When the row was written |
| `expires_at` | `timestamptz` | TTL — default 168h (7 days) |

#### `drug_personalization_cache`

Per-patient, per-query cached LLM reply for explain/interaction intents.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `uuid` PK | |
| `patient_id` | `uuid` FK → `patients` | |
| `medication_id` | `uuid` FK → `medications` | Optional |
| `reference_cache_id` | `uuid` FK → `drug_reference_cache` | Optional |
| `query_fingerprint` | `text` | SHA-256 of (redacted query + de-identified med context + intent + locale) |
| `intent` | `text` | `explain_medication` or `interaction_check` |
| `personalized_text` | `text` | Cached LLM reply |
| `locale` | `text` | `zh-TW` / `en` |
| `llm_meta` | `jsonb` | `{"source": "openfda"\|"tfda"\|"<model-id>"\|"mock_llm"}` |
| `expires_at` | `timestamptz` | TTL — default 72h (3 days) |
| `created_at` | `timestamptz` | |
| `updated_at` | `timestamptz` | |

Unique constraint: `(patient_id, query_fingerprint)`.

Cache invalidates naturally when the patient's medication list changes, because the fingerprint input changes.

---

## 7. API reference

### 7.1 Shared / operations

#### `GET /health`

Liveness check. No auth required.

**Response:** `200 OK`, body `"ok"` (plain text). Used by Docker health checks and load balancers.

---

#### `GET /internal-media/{file_id}`

Serves short-lived TTS audio files for LINE voice replies. Requires `PUBLIC_BASE_URL` to be set. Files are deleted after TTL by `LocalPublicObjectStorage`.

**Errors:**
- `404 Not Found` — file does not exist or has expired.

---

#### `POST /internal/reminders/reconcile`

**Auth:** `X-Cron-Secret: <MEDBUDDY_CRON_SECRET>` header.

Re-enqueues arq jobs for dose events that are due (`scheduled_at <= now()`), `reminder_sent_at IS NULL`, and `taken_at IS NULL`. Safety net after Redis or worker restarts.

**Recommended cron frequency:** every 15–60 minutes.

**Response:** `200 OK`
```json
{"enqueued": 3}
```

**Errors:**
- `401 Unauthorized` — missing or incorrect `X-Cron-Secret`.

---

### 7.2 LINE channel

#### `POST /v1/line/webhook`

**Auth:** `X-Line-Signature` HMAC-SHA256 header (verified with `LINE_CHANNEL_SECRET`). Skipped in mock mode when `LINE_CHANNEL_SECRET` is unset.

**Body:** Standard LINE webhook event object.

| Event type | Behavior |
|------------|---------|
| `follow` | Create user record; send localized welcome message with disclaimer |
| `message` (text) | Run assistant pipeline; reply with text |
| `message` (audio) | Engineering exploratory only — see §4.4 |

**Response:** `200 OK` (empty body — LINE requires a 200 ACK immediately; reply is sent asynchronously after acknowledgment).

**Errors:**
- `400 Bad Request` — invalid LINE signature in real mode.

---

### 7.3 Mobile app (`/v1/app`)

All authenticated endpoints require:
- `X-App-User-Id: <stable-id>` — 4–128 character string, stable per install or account.
- `Authorization: Bearer <MEDBUDDY_MOBILE_BEARER_TOKEN>` — required in production.

When `MEDBUDDY_MOBILE_BEARER_TOKEN` is unset and `MOCK_EXTERNAL_SERVICES=true`, the Bearer header is optional (development mode only).

**Common error responses:**

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Missing or incorrect Bearer token (in real mode) |
| `400 Bad Request` | Missing `X-App-User-Id`, or request body fails validation |
| `422 Unprocessable Entity` | FastAPI validation failure on request body |
| `500 Internal Server Error` | Unhandled exception — logged with `user_key` and request ID |

---

#### `GET /v1/app/health`

No auth required. JSON liveness check.

```json
{"status": "ok", "version": "..."}
```

---

#### `GET /v1/app/info`

No auth required. Public service metadata.

```json
{"service": "medbuddy-api", "locale": "zh-TW", "features": [...]}
```

---

#### `GET /v1/app/me`

Auth required. Returns the current user's profile.

```json
{
  "app_user_id": "device-abc123",
  "preferred_name": "...",
  "age_years": 68,
  "gender": "female",
  "emergency_contact": "...",
  "health_notes": "...",
  "timezone": "Asia/Taipei",
  "locale": "zh-TW",
  "onboarding_completed_at": "2026-04-01T10:00:00Z"
}
```

---

#### `POST /v1/app/onboarding`

Auth required. Saves first-run profile. Idempotent — safe to call again to update.

**Request body:**
```json
{
  "preferred_name": "...",       // required
  "age_years": 68,               // optional
  "gender": "female",            // optional: female|male|non_binary|prefer_not_say|other
  "emergency_contact": "...",    // optional
  "health_notes": "...",         // optional
  "timezone": "Asia/Taipei"      // optional IANA; omit → Asia/Taipei
}
```

**Response:** same shape as `GET /v1/app/me`.

---

#### `POST /v1/app/messages`

Auth required. Single assistant chat turn.

**Request body:**
```json
{"text": "阿斯匹靈可以跟抗凝血藥一起吃嗎？"}
```

`text` must be 1–8000 characters.

**Response:**
```json
{"reply": "..."}
```

**Errors:**
- `400 Bad Request` — `text` is empty or exceeds 8000 characters.

---

#### `GET /v1/app/summary`

Auth required. Returns a structured doctor-ready health summary.

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

---

## 8. LLM integration

### 8.1 Providers

`container.py` selects an `LLMPort` implementation from `LLM_PROVIDER` (default `gemini`):

| Provider | Implementation | Dependencies |
|----------|----------------|--------------|
| **Gemini** | `integrations/llm/gemini_llm.py` — `google-genai` | `GEMINI_API_KEY`; default model `gemini-2.5-flash` (`GEMINI_MODEL`) |
| **OpenAI** | `integrations/llm/openai_llm.py` — Chat Completions | `OPENAI_API_KEY`; default model `gpt-4.1-mini` (`OPENAI_MODEL`) |
| **Mock** | `integrations/mocks/llm.py` | No keys; CI and local dev |

Both real providers implement the same `LLMPort` contract. Install: `pip install 'medbuddy-api[llm]'` (included in the Docker image).

### 8.2 `LLMPort` interface

Authoritative signatures are in `apps/backend/src/medbuddy/protocols/ports.py`. The contract is:

```python
class LLMPort(Protocol):
    async def interpret_user_turn(
        self,
        user_text: str,
        *,
        recent_context: str | None = None,
    ) -> TurnInterpretation: ...

    async def compose_reply(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        history: list[ConversationTurn],
        user_message: str,
        locale: str,
    ) -> str: ...

    async def extract_medication_draft(
        self, user_text: str, *, locale: str
    ) -> MedicationDraft | None: ...

    async def resolve_medication_removal_id(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> str | None: ...

    async def extract_profile_patch(
        self, user_text: str
    ) -> dict[str, Any]: ...

    async def check_interactions_structured(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        history: list[ConversationTurn],
        user_message: str,
        locale: str,
    ) -> str: ...

    async def compose_medication_added_reply(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        medication_draft: MedicationDraft,
        locale: str,
    ) -> str: ...

    async def generate_health_summary(
        self,
        *,
        system_persona: str,
        patient_context: str,
        history: list[ConversationTurn],
        locale: str,
    ) -> HealthSummaryResult: ...
```

### 8.3 Prompt construction

All LLM calls follow the same layered structure:

| Layer | Source | Privacy treatment |
|-------|--------|------------------|
| **System persona** | `get_system_persona(locale)` — from `locales/*.json` `prompts.system_persona` | No PII; includes non-diagnostic instruction and `[…]` masking instruction |
| **Patient context** | `build_patient_context_for_llm(user, medications)` | De-identified: "preferred name on file" (not the name), age band (e.g. "60s"), medication list |
| **Drug grounding** | OpenFDA label snippets (indications, dosage, warnings) or `None` | Registry data only; no patient PII |
| **Conversation history** | Recent `ConversationTurn` objects | Redacted via `redact_conversation_turns_for_llm()` |
| **User message** | Current turn | Redacted via `redact_pii_text()` |
| **Extra system** | Intent-specific instructions (e.g. interaction-check companion, summary format) | No PII |

**Not included in any LLM call:** raw `preferred_name`, exact `age_years`, `health_notes`, `emergency_contact`.

### 8.4 Structured outputs

| Schema | Used for |
|--------|---------|
| `IntentClassification` | `interpret_user_turn` → `TurnInterpretation` (intent + adherence slots) |
| `MedicationExtraction` | `extract_medication_draft` — name, dosage, schedule, reminder prefs |
| `RemovalResolution` | `resolve_medication_removal_id` — which medication ID to delete |
| `HealthSummaryResult` | `GenerateHealthSummaryTool` — structured doctor summary |

### 8.5 Mock LLM behavior

`integrations/mocks/llm.py` implements `LLMPort` for CI and local development:

- `interpret_user_turn` yields `general_question` by default with adherence fields off.
- Tests pass explicit `intent=`, `record_pending_dose_as_taken`, `dose_adherence_note`, `medication_draft`, `locale_intent`, `removal_medication_id`, etc. to mirror real structured outputs.
- `compose_reply` returns templated i18n strings.
- No external API calls; no API keys required.

---

## 9. Caching strategy

### 9.1 Drug reference cache (`drug_reference_cache`)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Avoid repeated OpenFDA HTTP calls for the same drug name |
| **Scope** | Shared across all users |
| **Key** | `(source, query_key)` where `query_key` is normalized drug name |
| **TTL** | `MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS` — default 168h (7 days) |
| **Fallback** | Cache miss → fetch from OpenFDA → store. Without Supabase, cache is bypassed. |
| **Wrapper** | `CachingDrugData` wraps `DrugDataPort` transparently |

### 9.2 Drug personalization cache (`drug_personalization_cache`)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Avoid repeated LLM compose calls for the same patient context + query |
| **Scope** | Per patient |
| **Key** | SHA-256 of: redacted user query + de-identified med list + intent + locale |
| **TTL** | `MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS` — default 72h (3 days) |
| **Natural invalidation** | Medication list change → different hash → automatic cache miss |
| **Intents using it** | `explain_medication` and `interaction_check` only |

**`llm_meta.source` values:**
- `"openfda"` — reply grounded with OpenFDA label data
- `"tfda"` — reply grounded with TFDA data (not yet implemented)
- Active model ID (e.g. `gemini-2.5-flash`) — LLM-only, no registry data
- `"mock_llm"` — returned by mock adapter in tests

---

## 10. Privacy and security

### 10.1 PII handling before LLM calls

| Data | Treatment |
|------|-----------|
| Current user message | `redact_pii_text()` before `interpret_user_turn`, `compose_reply`, and all extraction calls |
| Conversation history | `redact_conversation_turns_for_llm()` — same patterns applied to all turns |
| Profile fields | Coarse signals only in `build_patient_context_for_llm`: no raw name, no exact age, no health notes, no emergency contact |
| Profile extracted from chat | `extract_profile_patch` structured output; persisted fields go to storage via `patch_user_profile` |

**Redaction patterns** (`privacy/redact.py`):
- Email addresses (RFC 5322-ish pattern)
- Taiwan mobile: `09xx-xxxxxx`, `09xxxxxxxx`, and CJK-adjacent digit runs
- Long digit runs (10+ consecutive digits — ID numbers, account numbers)

**Replacement token:** `[…]`. System prompt instructs the model that `[…]` represents masked content and never to invent values for it.

**Residual risk:** Names, addresses, free-form clinical details in user messages, and most international phone formats are not masked. Treat all LLM prompts as potentially containing sensitive free text. Full PHI scrubbing would require an NER-based approach — documented as future work in §18.

### 10.2 LINE webhook authentication

`channels/line/signature.py` implements HMAC-SHA256 verification of the `X-Line-Signature` header using `LINE_CHANNEL_SECRET`. Verification is bypassed **only** when `LINE_CHANNEL_SECRET` is empty **and** `MOCK_EXTERNAL_SERVICES=true` (local development). In production (`RENDER=true`), mock mode is always forced off.

### 10.3 Mobile API authentication

Two-factor check on `/v1/app/*` protected routes:
1. `X-App-User-Id` header — 4–128 character stable string.
2. `Authorization: Bearer <MEDBUDDY_MOBILE_BEARER_TOKEN>` — shared constant token.

> **Limitation:** This is a single shared bearer token, not per-user credentials. For production beyond a controlled pilot, rotate to per-user tokens or OAuth (tracked in `prd.md §13 OD-2`).

When `MEDBUDDY_MOBILE_BEARER_TOKEN` is unset and `MOCK_EXTERNAL_SERVICES=true`, the Bearer header is optional (development mode only).

### 10.4 Supabase access

The backend uses `SUPABASE_PUBLISHABLE_KEY` (anon key) — never the `service_role` key. All tables have RLS policies restricting anon role access. Row-level isolation relies on `external_user_id` matching in application code; Supabase RLS is an additional defense layer.

### 10.5 Internal endpoints

`POST /internal/reminders/reconcile` is protected by `X-Cron-Secret` matching `MEDBUDDY_CRON_SECRET`. Neither this endpoint nor `/internal-media/{id}` is intended for public client use — expose them on an internal network or behind a gateway in production.

### 10.6 Production safeguards

When `RENDER=true` (Render web service), `config.py` enforces:
- `MOCK_EXTERNAL_SERVICES = false`
- `DEBUG = false`
- `MEDBUDDY_INTEGRATION` forced to `real`

This prevents accidental mock mode in production regardless of dashboard environment variable mistakes.

### 10.7 Logging policy

- Raw user message text is **not** logged. Structured INFO logs record user key, intent, and medication count only.
- Full LLM prompts and response tokens are **not** logged by default.
- `LOG_LEVEL=DEBUG` may log additional diagnostic context — review carefully before enabling in production.

### 10.8 Rate limiting

No rate limiting is implemented in the current codebase. For a public-facing deployment:
- Add per-user rate limiting on `POST /v1/app/messages` (e.g. 60 requests/minute).
- Add IP-based rate limiting on the LINE webhook to prevent replay abuse.
- Render provides DDoS protection at the edge, but application-layer rate limiting remains the application's responsibility.

---

## 11. Error handling and resilience

### 11.1 Error hierarchy

```
MedBuddyError (base)
├── LLMParseError        — structured output could not be parsed; fallback to compose_reply
├── DrugDataError        — OpenFDA fetch failed; reply proceeds without grounding
└── ReminderError        — reminder enqueue failed; medication is still saved
```

Application exceptions are caught at the channel layer and produce user-visible error messages (i18n key `errors.general`) rather than raw stack traces.

### 11.2 LLM failure modes

| Failure | Behavior |
|---------|----------|
| `interpret_user_turn` parse error | Log warning with `user_key`; fall through to `compose_reply` with `general_question` intent |
| `compose_reply` error | Return i18n error string; persist empty assistant turn to maintain history integrity |
| Structured extraction error (add/remove) | Return i18n "couldn't understand" reply; no medication record written |

### 11.3 Drug data failure modes

| Failure | Behavior |
|---------|----------|
| OpenFDA request timeout | `CachingDrugData` returns `None`; tool proceeds with LLM-only reply; `llm_meta.source` records model ID |
| Cache miss + OpenFDA error | Same as above; no cache row written |
| TFDA stub (not implemented) | Always returns `None`; transparent to caller |

### 11.4 Reminder failure modes

| Failure | Behavior |
|---------|----------|
| Redis unavailable at enqueue time | Exception logged; medication save succeeds; reminders will not be scheduled until reconcile runs |
| arq job not delivered (worker down) | Reconcile endpoint re-enqueues on next cron run (15–60 min) |
| LINE push API error during delivery | Exception logged with `dose_id`; `reminder_sent_at` NOT set; reconcile will retry |
| Double-delivery attempt | `reminder_sent_at` already set → deliver.py skips silently (idempotency) |

### 11.5 Supabase failure modes

| Failure | Behavior |
|---------|----------|
| Query error (conversation save) | Logged; turn is still returned to user |
| Profile load error | Exception propagates; user sees i18n error string |
| In-memory mock mode | Full application runs without Supabase; state is lost on restart |

---

## 12. Observability

### 12.1 Current signals

| Signal | Source | Notes |
|--------|--------|-------|
| **Liveness** | `GET /health` (plain text) | Docker / Render health checks |
| **JSON health** | `GET /v1/app/health` | Mobile client and monitoring |
| **Structured logs** | `configure_logging()` in `logging_config.py` | `medbuddy.*` namespace; level from `LOG_LEVEL` |
| **Webhook logs** | `channels/line/orchestrator.py` | Event type, step, reply size — no raw text |
| **Turn logs** | `application/assistant_turn.py` | `user_key`, `intent`, `med_count` |

`uvicorn.error` is configured at the same `LOG_LEVEL`. Access logs (`uvicorn.access`) can be enabled separately.

### 12.2 Recommended additions before production

| Gap | Recommendation |
|-----|---------------|
| No request ID propagation | Add a `X-Request-ID` middleware; include in all log records for correlated tracing |
| No error rate metrics | Instrument `interpret_user_turn` and `compose_reply` call latency and error counts (Prometheus or OTLP) |
| No LLM cost tracking | Log token usage from LLM responses; aggregate per user per day for cost control |
| No reminder delivery metrics | Track `enqueued`, `delivered`, `failed`, `retried` counts in reminder worker |
| No distributed tracing | Add OpenTelemetry instrumentation for cross-service traces (LLM calls, Supabase, LINE) |
| No alerting | Set up alerts on: webhook 4xx/5xx rate, turn error rate, reminder delivery lag |

---

## 13. Testing strategy

### 13.1 Test layers

| Layer | What is tested | Tools | Location |
|-------|---------------|-------|----------|
| **Unit** | Individual tools and domain functions in isolation | pytest + mock adapters | `tests/unit/` |
| **Integration (mock)** | Full `run_assistant_text_turn` pipeline with mock LLM and mock stores | pytest + `MEDBUDDY_INTEGRATION=mock` | `tests/integration/` |
| **Integration (real)** | API against live Supabase and LLM (CI with secrets, or local real mode) | pytest + `MEDBUDDY_INTEGRATION=real` | `tests/integration/real/` |
| **End-to-end** | LINE webhook flow with mock signature + full stack | pytest + TestClient | `tests/e2e/` |

### 13.2 Mock adapter contract

Mock adapters must honor the same `Protocol` contract as their real counterparts. Tests that pass explicit intent overrides to `MockLLM` (e.g. `intent=add_medication`) mirror what structured outputs from real adapters produce — this is the primary mechanism for testing tool dispatch paths.

### 13.3 Test coverage targets (prototype)

- All intent dispatch paths: covered.
- All tool `run()` paths for happy-path inputs: covered.
- All reminder lifecycle paths (add → materialize → enqueue → deliver → idempotency): covered.
- All API endpoints with auth: covered.
- Error handling fallbacks (`LLMParseError`, drug data miss): covered.

### 13.4 CI pipeline

```bash
make test          # pytest with MEDBUDDY_INTEGRATION=mock
make lint          # ruff + mypy
make check         # lint + test (CI gate)
```

---

## 14. Deployment topology

### 14.1 Single-container (default, Render)

`Dockerfile` (Python 3.12-slim-bookworm) installs all extras (`[llm,supabase,tts,reminders]`). `docker-entrypoint-web.sh` starts:
- **uvicorn** — always.
- **arq worker** — only when `REDIS_URL` is non-empty.

Both processes share the same container and environment.

```
┌────────────────────────────────────────┐
│  Docker container (medbuddy-api)       │
│                                        │
│   uvicorn (port $PORT)                 │
│   arq worker (when REDIS_URL set)      │
│                                        │
│   shared env: LINE, LLM, Supabase,     │
│   REDIS_URL                            │
└────────────────────────────────────────┘
         │                    │
         ▼                    ▼
    Supabase               Redis
    (Postgres)             (managed)
```

### 14.2 Split-process (scale-out)

When reminder processing needs independent scaling, run two services from the same image with different CMD overrides. **Do not run arq in both containers** — it would double-deliver reminders.

```
┌─────────────────────────┐   ┌──────────────────────────┐
│  medbuddy-api (web)     │   │  medbuddy-worker          │
│  CMD: uvicorn only      │   │  CMD: arq worker only     │
└────────────┬────────────┘   └────────────┬─────────────┘
             │                             │
             └─────────────┬───────────────┘
                           ▼
                         Redis
```

### 14.3 Local Docker Compose

```bash
# API only (no Redis / reminders):
podman compose up --build

# API + Redis + arq worker:
REDIS_URL=redis://redis:6379 podman compose --profile reminders up --build
```

### 14.4 Render blueprint

`render.yaml` defines `medbuddy-api` as a web service.

**Setup steps:**
1. Dashboard → New → Blueprint → connect repo → apply `render.yaml`.
2. Create Render Key Value → set `REDIS_URL` on `medbuddy-api`.
3. Set environment secrets: `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`, LLM keys (`LLM_PROVIDER`, `GEMINI_API_KEY` or `OPENAI_API_KEY`), `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `MEDBUDDY_MOBILE_BEARER_TOKEN`, `PUBLIC_BASE_URL`, `MEDBUDDY_CRON_SECRET`.
4. Set LINE webhook URL: `{PUBLIC_BASE_URL}/v1/line/webhook`.

---

## 15. Configuration reference

All settings are in `config.py` (Pydantic `BaseSettings`). Priority order: `MEDBUDDY_INTEGRATION` env → `apps/backend/.env` → working directory `.env`.

### 15.1 Integration mode

| Variable | Values | Default | Notes |
|----------|--------|---------|-------|
| `MEDBUDDY_INTEGRATION` | `mock` / `real` | (unset) | Overrides `MOCK_EXTERNAL_SERVICES`. Aliases: `local`/`dev` → mock; `live`/`production` → real. |
| `MOCK_EXTERNAL_SERVICES` | `true` / `false` | `false` | Fallback when `MEDBUDDY_INTEGRATION` is unset. |

### 15.2 LINE

| Variable | Required for | Notes |
|----------|-------------|-------|
| `LINE_CHANNEL_SECRET` | Webhook signature verification | Verification skipped if unset + mocks enabled |
| `LINE_CHANNEL_ACCESS_TOKEN` | Replies + push | |

### 15.3 LLM

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `GEMINI_API_KEY` | — | Required when `LLM_PROVIDER=gemini` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | |
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | `gpt-4.1-mini` | |

### 15.4 Storage and speech

| Variable | Default | Notes |
|----------|---------|-------|
| `PUBLIC_BASE_URL` | `http://localhost:8000` | HTTPS base URL for LINE-accessible audio |
| `GOOGLE_SPEECH_API_KEY` | — | For Google Speech-to-Text (exploratory) |
| `GOOGLE_SPEECH_PROJECT_ID` | — | Google Cloud project ID |
| `GOOGLE_SPEECH_LOCATION` | `global` | Speech-to-Text V2 location |

### 15.5 Supabase

| Variable | Notes |
|----------|-------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_PUBLISHABLE_KEY` or `SUPABASE_ANON_KEY` | Anon key only — never `service_role` |

### 15.6 Reminders

| Variable | Default | Notes |
|----------|---------|-------|
| `REDIS_URL` | — | DSN for arq; enables worker when set |
| `MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME` | `09:00` | `HH:MM` local time for daily reminders — interpreted in `patients.timezone` (per-user), not a global timezone |
| `MEDBUDDY_REMINDER_HORIZON_DAYS` | `14` | Days ahead to materialize dose events (max 90) |
| `MEDBUDDY_CRON_SECRET` | — | Header secret for reconcile endpoint |

### 15.7 Caching

| Variable | Default | Notes |
|----------|---------|-------|
| `MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS` | `168` | 7 days; shared drug label cache |
| `MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS` | `72` | 3 days; per-patient LLM reply cache |

### 15.8 General

| Variable | Default | Notes |
|----------|---------|-------|
| `MEDBUDDY_LOCALE` | `zh-TW` | Server-default locale for i18n |
| `MEDBUDDY_MOBILE_BEARER_TOKEN` | — | Bearer token for `/v1/app` protected routes |
| `LOG_LEVEL` | `INFO` | `medbuddy.*` and `uvicorn.error` log level |
| `DEBUG` | `false` | FastAPI debug mode |
| `PORT` | `8000` | Injected by Render at runtime |
| `RENDER` | — | Set by Render; triggers production safety overrides |

---

## 16. Extension points

### 16.1 Intent hooks

`extensibility/intent_hooks.py` allows registering functions that intercept specific intents **before** tool dispatch. A hook returning a non-empty string short-circuits the normal pipeline.

Use cases:
- Pilot features that need to intercept a specific intent without forking channel routing.
- A/B testing reply variants.
- Routing specific intents to specialized downstream services.

### 16.2 Adding a new LLM adapter

1. Implement `LLMPort` in a new file under `integrations/llm/`.
2. Register in `container.py`'s `build_app_services()` under the appropriate condition.
3. No changes to `application/` or `agents/`.

### 16.3 Adding a new delivery channel

1. Implement a channel module under `channels/<name>/`.
2. Mount it in `main.py`.
3. Call `run_assistant_text_turn(user_key, user_text, services)` — same as LINE and mobile.
4. Implement channel-specific auth and reply formatting in the channel module.

### 16.4 Adding a new agent tool

1. Subclass `AgentTool` in `agents/tools/<name>.py`.
2. Implement `async def run(self, **kwargs: Any) -> ToolResult`.
3. Register the tool for the relevant `Intent` values in `MedicationAgent`.

### 16.5 Adding a new locale

1. Add a `locales/<lang>.json` file following the same key structure as `zh-TW.json`.
2. Add the locale code to the allowed values in `config.py`.
3. Update `i18n.py` fallback chain if needed.

---

## 17. Quality attributes and prototype SLOs

These are best-effort targets for the prototype — not contractual SLAs.

| Attribute | Target | Notes |
|-----------|--------|-------|
| **Assistant turn latency (p90)** | < 5s | LLM interpretation + tool dispatch + compose reply |
| **Reminder delivery lag** | < 5 min from `scheduled_at` | Under normal conditions with arq worker running |
| **Reconcile coverage** | 100% of overdue reminders re-enqueued within 60 min | Assuming 15–60 min cron frequency |
| **Availability** | Best effort; no SLA | Render web service with health check restart |
| **Data durability** | Supabase managed Postgres backup | Row-level data not stored outside Supabase |
| **Test suite** | 100% pass rate required for any merge to `main` | CI gate |

---

## 18. Known limitations and future work

### 18.1 Prototype limitations (scope decisions)

| Item | Status | Notes |
|------|--------|-------|
| Voice (STT/TTS) as product feature | Out of prototype scope | Code paths exist; not validated. See `prd.md §2`. |
| Rich LINE Flex messages / "mark taken" postback | Not implemented | Reminders are plain text. |
| Local push notifications for HTTP-only users | Not implemented | LINE push is the only reminder delivery channel. |
| TFDA live API integration | Stub | `fetch_tfda_snippet()` returns `None`; `source=tfda` rows are never created. |

### 18.2 Technical debt and known gaps

| Item | Status | Recommended path |
|------|--------|-----------------|
| Per-user bearer tokens | Single shared token | OAuth or per-user JWT for Growth phase — see `prd.md OD-2`. |
| Free-text reminder schedule parsing | Not implemented | `schedule` field is stored and echoed; does not drive multiple reminders per day. Requires NLP schedule parser. |
| Full PHI scrubbing | Pattern-based only | Names, addresses, and clinical text are not masked. NER-based redaction recommended before wider deployment. |
| Distributed tracing / metrics | Not implemented | Add OpenTelemetry before production. See §12.2. |
| Rate limiting | Not implemented | Add per-user and per-IP limits before public-facing deploy. See §10.8. |
| API versioning strategy | No versioning | Add `Accept: application/vnd.medbuddy.v1+json` or path versioning before any breaking change. |
| `dose_events.taken_at` vs `missed_at` | `taken_at` exists; `missed_at` added for `ReportMissedDoseTool` | Adherence reporting UI or export not yet implemented. |
| Expo reference app STT wiring | Not wired to backend | See [`frontend-expo.md`](frontend-expo.md). |
