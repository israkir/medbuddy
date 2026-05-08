# MedBuddy backend

FastAPI service with **two delivery channels** sharing a single assistant core: **LINE** (`/v1/line/...`) and the **standalone mobile client** (`/v1/app/...`). The backend follows **hexagonal architecture** (ports & adapters) with an **LLM tool-orchestration** pattern: **`LLMPort.interpret_user_turn`** yields **`TurnInterpretation`** for fast routing (emergency, off_topic, classifier logging), then **`run_tool_agent_loop`** drives **`LLMPort.complete_chat_with_tools`** so the model selects **registered tools** over multiple steps as needed.

Paths below are relative to **`apps/backend/`**.

---

## Architecture overview

```
channels/line/   channels/api/
      ↓                 ↓
   application/assistant_turn.py    ← single entry point for both channels
          ↓
   agents/MedicationAgent           ← routing gates (locale/pending/emergency/contact/hooks/off_topic)
          ↓
   agents/orchestrator.py           ← run_tool_agent_loop → complete_chat_with_tools
          ↓
   agents/tools/                    ← medication CRUD, drug lookup, interactions, summary, vitals, …
          ↓
  protocols/                       ← abstract interfaces (hexagonal boundary)
    ↓           ↓         ↓
integrations/  integrations/ integrations/
gemini_llm    supabase_stores  drugs_http
(or mocks)    (or in-memory)  (or mock)
```

**Hexagonal principle:** `agents/` and `application/` never import from `integrations/` directly — they call `protocols/` interfaces. `container.py` wires concrete adapters at startup.

---

## Package layout

| Area | Path | Role |
|------|------|------|
| **Channels** | `channels/line/` | LINE webhook, HMAC signature verification, event pipeline |
| | `channels/api/` | App REST API: auth (`Bearer` + `X-App-User-Id`), schemas, routes |
| **Application** | `application/assistant_turn.py` | `run_assistant_text_turn()` — entry point shared by LINE and mobile |
| | `application/patient_llm_context.py` | `patient_context_for_llm()` — de-identified context plus materialized upcoming `dose_events` for LLM prompts |
| | `application/vital_log_build.py` | Parses BP / glucose / etc. into payloads for `HealthIssueEventRecord` |
| | `application/pending/` | Early-turn resolvers that short-circuit before the orchestrator (`locale_intents`, `medication_add_confirm_resolve`, `dose_clarification_resolve`, `reminder_horizon_resolve`) |
| | `application/health_events/` | `health_issue_event_log` (classifier-intent allowlist policy) and `health_issue_events_format` (chronological block for the doctor-summary prompt) |
| | `application/profile/` | `profile_intents.apply_profile_update_from_extracted_patch` (orchestrator `update_profile`), `emergency_contact_resolve` (capture TW-mobile contact lines pre-orchestrator), `profile_completion_nudge` (optional onboarding reminder footer) |
| **Agents** | `agents/medication_agent.py` | `MedicationAgent` — fast routing (`interpret_user_turn`) + pending/locale/emergency/contact gates, then `run_tool_agent_loop` |
| | `agents/orchestrator.py` | `run_tool_agent_loop` — `LLMPort.complete_chat_with_tools` with prior-thread injection and registered tool execution |
| | `agents/base.py` | `AgentTool` base class, `ToolResult` dataclass |
| | `agents/tools/medication_crud.py` | `ListMedicationsTool`, `AddMedicationTool`, `UpdateMedicationTool`, `RemoveMedicationTool` |
| | `agents/tools/upcoming_doses.py` | `ListUpcomingDosesTool` (`upcoming_doses` intent) |
| | `agents/tools/drug_lookup.py` | `ExplainMedicationTool` (grounding + LLM compose + cache) |
| | `agents/tools/interaction_check.py` | `InteractionCheckTool` |
| | `agents/tools/health_summary.py` | `GenerateHealthSummaryTool` (doctor-ready output) |
| **Models** | `models/domain.py` | `Intent`, `TurnInterpretation`, `MedicationDraft`, `MedicationRecord`, `ConversationTurn` |
| **Protocols** | `protocols/` | Abstract interfaces: `LLMPort`, `UserDataPort`, `LineMessagingPort`, etc. (one file per port) |
| | `protocols/drug_caches.py` | `DrugCachesPort` |
| **Services** | `services.py` | `AppServices` dataclass — DI container |
| **Container** | `container.py` | `build_app_services(settings)` — wires mock vs real adapters |
| **Integrations** | `integrations/llm/gemini_llm.py`, `integrations/llm/openai_llm.py` | LLM adapters (`LLM_PROVIDER` selects which runs) |
| | `integrations/line_client.py` | LINE Messaging API SDK |
| | `integrations/persistence/supabase_stores.py` | Supabase Postgres (patients, meds, turns, dose events) |
| | `integrations/drugs_http.py` | OpenFDA HTTP + TFDA stub |
| | `integrations/caching_drugs.py` | `CachingDrugData` wrapper with TTL |
| | `integrations/persistence/supabase_drug_caches.py` | `SupabaseDrugCaches` (personalization cache) |
| | `integrations/stt/stt_google.py` | Google Cloud Speech-to-Text V2 |
| | `integrations/mocks/` | In-memory mock adapters for all ports |
| **Privacy** | `privacy/redact.py` | `redact_pii_text()` — emails, phone patterns, digit runs |
| **Prompts** | `llm/prompts/persona.py` | `get_system_persona()`, LLM-safe vs display patient context |
| **Reminders** | `reminders/` | arq worker, dose scheduling, LINE push delivery, reconcile |
| **Shared routes** | `channels/internal/routes.py` | `/health`, `/internal/reminders/reconcile` |
| **i18n** | `core/i18n.py` | `t()` — key lookup with zh-TW fallback |
| **Config** | `config.py` | Settings dataclass + env loading; loads `apps/backend/.env` then repo-root `.env` |

Add new **LINE** behavior in `channels/line/`; extend **app-only** REST in `channels/api/`. Shared assistant logic belongs in **`application/`** or **`agents/`** so channels never duplicate LLM or drug steps.

---

## API endpoints

### Shared / ops

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /health` | None | Plain-text liveness |
| `POST /internal/reminders/reconcile` | `X-Cron-Secret` | Re-enqueues overdue, unsent dose reminder jobs |

### LINE (`/v1/line`)

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /v1/line/webhook` | `X-Line-Signature` HMAC | Text, voice (audio), and follow events |
| `GET /v1/line/media/audio/{id}` | None | Short-lived **m4a** blob for LINE **audio** messages (used when voice replies are enabled); **HTTPS** `PUBLIC_BASE_URL` required in production |

### Mobile app (`/v1/app`)

All protected routes require **`X-App-User-Id`** (4–128 chars) and, in production, **`Authorization: Bearer <MEDBUDDY_MOBILE_BEARER_TOKEN>`**.

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /v1/app/health` | None | JSON health check |
| `GET /v1/app/info` | None | Public service metadata |
| `GET /v1/app/me` | Bearer + User-Id | User profile (name, age, gender, emergency contact, notes, **locale**, **timezone**). Pre-onboarding: optional **`X-MedBuddy-Locale`** or **`Accept-Language`** may update stored **locale**. |
| `POST /v1/app/onboarding` | Bearer + User-Id | First-run profile save (optional **timezone** IANA; default **Asia/Taipei**) |
| `POST /v1/app/messages` | Bearer + User-Id | Chat turn — `{"text":"…"}` → `{"reply":"…"}` |
| `POST /v1/app/messages/voice` | Bearer + User-Id | Multipart **`file`** (audio) → STT (profile **`locale`**) → same assistant as text → `{"reply":"…","transcript":"…"}` |
| `GET /v1/app/summary` | Bearer + User-Id | Doctor-ready structured health summary |

---

## Makefile (from repository root)

The [Makefile](../../Makefile) lives at the repo root. Backend targets use the **`be-`** prefix.

| Area | Commands |
|------|----------|
| Environment | `make be-venv`, `make be-install` |
| Run API | **`make be-dev-mock`** / **`make be-dev`** (reload, mocks), **`make be-dev-real`** (reload, real + `.env`), `make be-run-prod`, optional `PORT=8080` |
| Tests & quality | `make be-test`, `make be-test-verbose`, `make be-test-cov`, `make be-lint`, `make be-fmt`, `make be-check` |
| Containers | `make be-compose`, `make be-build` |
| Cleanup | `make be-clean`, `make be-clean-all` |

Typical flow: `make be-install` → `make be-dev-mock` → `make be-test`.

---

## Mock vs real integrations

Switch without code changes:

| Variable | Values | Notes |
|----------|--------|-------|
| **`MEDBUDDY_INTEGRATION`** | `mock` / `real` | Aliases: `local`/`dev` → mock; `live`/`production` → real. **Overrides** `MOCK_EXTERNAL_SERVICES` when set. |
| **`MOCK_EXTERNAL_SERVICES`** | `true` / `false` | `true` = in-memory adapters for LINE/STT/LLM/drugs/storage/users. Default `false`. |

[`config.py`](src/medbuddy/config.py) loads `apps/backend/.env` first, then a `.env` in the working directory (so a repo-root `.env` overrides). `make be-dev-mock` exports `MEDBUDDY_INTEGRATION=mock`; `make be-dev-real` exports `MEDBUDDY_INTEGRATION=real`.

When **`RENDER=true`** (Render web services), settings force `MOCK_EXTERNAL_SERVICES=false`, `DEBUG=false`, and `MEDBUDDY_INTEGRATION=real` — a mis-set dashboard env cannot re-enable mocks in production.

---

## Integrations

Wiring is centralized in [`src/medbuddy/container.py`](src/medbuddy/container.py): `build_app_services(settings)` chooses mock vs real.

| Port | Mock | Real |
|------|------|------|
| **LINE** | `integrations/mocks/line.py` | `integrations/line_client.py` — needs `LINE_CHANNEL_ACCESS_TOKEN` |
| **LLM** | `integrations/mocks/llm.py` | `integrations/llm/gemini_llm.py` or `integrations/llm/openai_llm.py` — set `LLM_PROVIDER` and `GEMINI_API_KEY` or `OPENAI_API_KEY`; install `[llm]` extra |
| **STT** | `integrations/mocks/stt.py` | `integrations/stt/stt_google.py` — needs `GOOGLE_SPEECH_PROJECT_ID` and Application Default Credentials |
| **TTS (LINE m4a replies)** | `integrations/mocks/tts.py` | `integrations/tts/tts_google.py` — same ADC/project as STT; server needs **ffmpeg** (`Dockerfile` installs it) |
| **Drugs** | `integrations/mocks/drugs.py` | `integrations/drugs_http.py` — OpenFDA HTTP (no key) + TFDA stub |
| **Users / turns** | In-memory mocks | `integrations/persistence/supabase_stores.py` when `SUPABASE_URL` + `SUPABASE_PUBLISHABLE_KEY` are set; install `[supabase]` extra, apply `supabase/schema.sql` |
| **Drug caches** | No-op | `integrations/persistence/supabase_drug_caches.py` + `integrations/caching_drugs.py` (Supabase required) |

**Key environment variables** (see [`.env.example`](.env.example)):

| Variable | Purpose |
|----------|---------|
| `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN` | Real LINE channel |
| `LLM_PROVIDER` | `gemini` (default) or `openai` — see `GEMINI_*` / `OPENAI_*` below |
| `GEMINI_API_KEY` | Google Gemini when `LLM_PROVIDER=gemini` (default model `gemini-2.5-flash`; override via `GEMINI_MODEL`) |
| `OPENAI_API_KEY` | OpenAI when `LLM_PROVIDER=openai` (default model `gpt-4.1-mini`; override via `OPENAI_MODEL`) |
| `GOOGLE_SPEECH_PROJECT_ID` | Google Cloud project id for Speech-to-Text V2 endpoint |
| `GOOGLE_SPEECH_LOCATION` | Speech-to-Text V2 location (`global` default) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service-account JSON for Google client libraries (or use workload identity/metadata credentials) |
| `PUBLIC_BASE_URL` | Public **HTTPS** origin (LINE webhooks, LINE **audio** URLs for TTS; see `config.py`) |
| `MEDBUDDY_LINE_VOICE_REPLIES` | `audio_inbound` (default), `always`, or `off` — text+m4a LINE replies when TTS is available |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | Postgres persistence (use anon key, never service role) |
| `REDIS_URL` | arq job queue for dose reminders |
| `MEDBUDDY_MOBILE_BEARER_TOKEN` | Auth token for `/v1/app` protected routes |
| `MEDBUDDY_CRON_SECRET` | Auth for `POST /internal/reminders/reconcile` |
| `MEDBUDDY_LOCALE` | Server locale (`zh-TW` default) |
| `LOG_LEVEL` | `INFO` (default) or `DEBUG` |
| `CONVERSATION_HISTORY_TURNS` | Max turns loaded from storage for routing context (default `5`) |
| `MEDBUDDY_AGENT_ORCHESTRATOR_HISTORY_TURNS` | Max **prior** user/assistant turns injected into the tool orchestrator LLM per message (default **12**; `0` disables prior-turn injection) |
| `MEDBUDDY_PROFILE_COMPLETION_NUDGE_EVERY_N_USER_TURNS` | When profile gaps remain (name, age, gender, emergency contact, health notes), append a gentle footer every **N** user messages on the main assistant path (default **12**; **`0`** disables) |
| `MEDBUDDY_HEALTH_ISSUE_LOG_INTENTS` | Optional comma-separated **`Intent`** values to persist to **`health_issue_events`**; omit for built-in defaults; **`all_non_off_topic`** logs every non-**`off_topic`** classifier outcome |
| `MEDBUDDY_HEALTH_ISSUE_SUMMARY_EVENTS_LIMIT` | Max **`health_issue_events`** rows formatted into the doctor health-summary prompt (default **60**, max **200**) |

---

## Google Cloud (Speech-to-Text and Text-to-Speech)

For LINE voice messages, the backend can transcribe audio with **Cloud Speech-to-Text API** (V2). For **LINE voice replies** (`MEDBUDDY_LINE_VOICE_REPLIES`), it uses **Cloud Text-to-Speech** in the same project (same service account / ADC).

1. **Project** — In the [Google Cloud console](https://console.cloud.google.com/), select or create a project. Note the **project id** (set `GOOGLE_SPEECH_PROJECT_ID` for Speech-to-Text V2).
2. **Enable APIs** — **APIs & Services → Library**, enable **Cloud Speech-to-Text API**. If you use voice replies, also enable **Cloud Text-to-Speech API**.
3. **Service account** — **IAM & Admin → Service Accounts → Create**. Grant roles that allow Speech-to-Text (for example **Speech Client** `roles/speech.client`) and Text-to-Speech (**Cloud Text-to-Speech User** `roles/texttospeech.user`) when needed.
4. **Key for local/dev** — On the service account, **Keys → Add key → JSON**. Set `GOOGLE_APPLICATION_CREDENTIALS` to the downloaded file path. On **Render** or GCE, prefer **workload identity** / instance metadata instead of a JSON key.

Billing must be enabled on the project for production use of these APIs.

---

## Localization

- **Backend:** JSON under `apps/backend/src/medbuddy/locales/` (`zh-TW`, `en`); server default via `MEDBUDDY_LOCALE` / `.env` (see `apps/backend/.env.example`). Patient-visible tool fallbacks include split medication-update strings (**`medication.updated`** vs **`medication.updated_with_note`**) so empty notes do not read as a dangling “Notes:” line; unknown dose/schedule placeholders use **`medication.unspecified`** (and `medication_draft_build` treats those labels as placeholders when stored).
- **Frontend:** `i18next` + JSON under `apps/frontend/locales/`.

Adding a language: add matching `*.json` in both trees and register in backend settings/loaders and `apps/frontend/i18n/index.ts` (details in the per-app READMEs).

---

## Testing LINE integration

| Layer | What to do |
|-------|-----------|
| **Automated** | `make be-test` runs `tests/test_webhook_pipeline.py`, `test_line_signature.py`, etc. |
| **Local mock** | `make be-dev-mock` → `POST http://127.0.0.1:8000/v1/line/webhook` with a LINE-shaped JSON body. Signature check skipped when `LINE_CHANNEL_SECRET` is unset. |
| **Real LINE (tunnel)** | `make be-dev-real` + set `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`, `PUBLIC_BASE_URL`. Expose via [ngrok](https://ngrok.com/) or Cloudflare Tunnel; set webhook URL in [LINE Developers Console](https://developers.line.biz/) to `{PUBLIC_BASE_URL}/v1/line/webhook`. |
| **Hosted** | After deploy, set same webhook URL in LINE console. |

Protocol definitions: [`src/medbuddy/protocols/`](src/medbuddy/protocols).
Intent overrides: [`src/medbuddy/extensibility/intent_hooks.py`](src/medbuddy/extensibility/intent_hooks.py).

---

## LINE dose reminders (prototype)

When **Supabase** is configured, successful add/remove medication calls `sync_upcoming_dose_events`: future `dose_events` rows are rebuilt (once daily at `MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME`, default `09:00`, in the **`patients.timezone`** IANA column — default **`Asia/Taipei`** at insert; standalone **`POST /v1/app/onboarding`** sets **`timezone`**; **`patch_user_profile`** can update it) for `MEDBUDDY_REMINDER_HORIZON_DAYS` (default 14, max 90). With **`REDIS_URL`** set and `[reminders]` installed, the API enqueues `send_reminder_for_dose` arq jobs.

The repo-root `Dockerfile` runs [`docker-entrypoint-web.sh`](../../docker-entrypoint-web.sh): **uvicorn** + **`arq medbuddy.reminders.worker.WorkerSettings`** when `REDIS_URL` is non-empty.

**Scale-out:** add a second service from the same image with the arq start command; configure the API service to use uvicorn only so arq runs in exactly one process.

**Compose:** `REDIS_URL=redis://redis:6379 podman compose --profile reminders up --build`

**Safety net:** `POST /internal/reminders/reconcile` with `X-Cron-Secret` re-enqueues overdue, unsent rows.

Full reference: [`docs/reminders.md`](../../docs/reminders.md).

---

## Quick start (Docker/Podman)

From the **repository root**:

```bash
make be-compose
# or: podman compose up --build
```

Health checks:
- Plain text: `GET http://localhost:8000/health`
- JSON: `GET http://localhost:8000/v1/app/health`
- LINE webhook: `POST http://localhost:8000/v1/line/webhook`

---

## Deploy on [Render](https://render.com/)

1. **Blueprint** — Dashboard → New → Blueprint → connect repo → apply [`render.yaml`](../../render.yaml). Defines `medbuddy-api` (web, repo-root `Dockerfile`).
2. **Redis** — Create Render Key Value (or Upstash) → set `REDIS_URL` on `medbuddy-api`.
3. **Environment** — Add the keys from [`render.yaml`](../../render.yaml); use Render’s **Secret** type for tokens and credential paths. For **Google Cloud STT**, set `GOOGLE_APPLICATION_CREDENTIALS` and `GOOGLE_SPEECH_PROJECT_ID`. Also set `PUBLIC_BASE_URL`, `LINE_CHANNEL_*`, LLM and Supabase keys, `MEDBUDDY_MOBILE_BEARER_TOKEN`, `REDIS_URL`, and optional `MEDBUDDY_CRON_SECRET`.
4. **LINE** — Webhook URL: `{PUBLIC_BASE_URL}/v1/line/webhook`.
5. **Mobile clients** — Point API calls at `PUBLIC_BASE_URL`.

**Without Docker:** Python runtime, root directory `apps/backend`, build `pip install ".[llm,supabase,reminders]"`, start command running uvicorn (+ arq when `REDIS_URL` is set).

---

## Development (without Make)

```bash
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export MOCK_EXTERNAL_SERVICES=true
uvicorn medbuddy.main:app --reload --host 0.0.0.0 --port 8000
pytest -q
```
