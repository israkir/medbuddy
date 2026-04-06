# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`drug_personalization_cache`**: `save_personalized_reply` now stores **`medication_id`** when exactly
  one list medication name matches the user message (normalized substring), and **`reference_cache_id`**
  when a TFDA/OpenFDA grounding row exists in **`drug_reference_cache`** (OpenFDA preferred if both).
  **`llm_meta.source`** is **`openfda`** / **`tfda`** when that registry grounding was present, otherwise
  the **Gemini model id** from settings (or **`mock_llm`** when mocks are on), marking model-only replies.
- **`drug_reference_cache`**: OpenFDA fetches now persist **`indications_and_usage`**, **`dosage_and_administration`**,
  **`warnings`**, and **`raw_payload`** (`{"label": <fda label object>}`) via **`DrugGrounding`** and
  **`CachingDrugData`**. **`HttpDrugData.fetch_tfda_snippet`** returns **`None`** (no live TFDA client), so
  **`source=tfda`** rows are not created from placeholder copy; only real adapters (e.g. OpenFDA) populate the cache until TFDA is implemented.

### Added

- **LINE dose reminders (prototype)**: Supabase **`dose_events`** sync after add/remove medication;
  **`reminder_sent_at`** and **`users.timezone`**; **arq** + **`REDIS_URL`** for deferred
  **`send_reminder_for_dose`** jobs; **LINE `push_message`**; **`POST /internal/reminders/reconcile`**
  with **`MEDBUDDY_CRON_SECRET`**; settings **`MEDBUDDY_REMINDER_*`** / **`MEDBUDDY_CRON_SECRET`** /
  **`REDIS_URL`**. Docker image installs **`[reminders]`** extra.
- **Deploy**: repo-root **`Dockerfile.reminder-worker`** for the arq worker; **`render.yaml`** adds **`medbuddy-reminder-worker`** (Render **Background Worker**, **`starter`** plan) alongside **`medbuddy-api`**; Compose **`reminders`** profile for local Redis + worker.
- **Documentation**: **`docs/reminders.md`** — LINE dose reminders (data model, arq/Redis, Render, Compose, reconcile); linked from root **`README.md`**, **`docs/use-cases.md`**, and backend **`README.md`**.
- **Onboarding / profile**: optional **`gender`** (self-reported category: female, male, non-binary, prefer not to say, other)
  on **`users`**, mobile **`POST /v1/app/onboarding`** and **`GET /v1/app/me`**, persona gaps/signals, and conservative
  **`parse_profile_patch_from_text`** patterns for chat profile updates.
- **Documentation**: **`docs/privacy.md`** — how PII is limited for LLM calls, redaction, local profile parsing,
  and operational caveats.
- **Profile in chat (LINE + app)**: **`Intent.UPDATE_PROFILE`** with **`UserDataPort.patch_user_profile`** and
  **local parsing** (**`parse_profile_patch_from_text`**) so profile fields are **not** sent to LLM extractors.
- **LLM privacy boundary**: **`redact_pii_text`** / **`redact_conversation_turns_for_llm`** mask emails, typical
  phone shapes, and long digit runs before **`classify_intent`**, **`compose_reply`**, and medication extract/remove
  calls; **`build_patient_context_for_llm`** sends only **coarse profile signals** (plus medication list), while
  **`build_patient_context_for_chat_display`** keeps full text for **user-facing** list replies. Persona / reply
  instructions state the model must not invent names or raw health/contact details.
- **Supabase `drug_reference_cache`**: global table to cache drug usage / label text
  (`source`, `query_key`, `title`, `usage_text`, optional indication/dosing/warning fields,
  `raw_payload`, `fetched_at`, `expires_at`) with RLS for `anon`, matching other MedBuddy tables.
- **Supabase `drug_personalization_cache`**: per-user cache for **LLM-personalized** explanations
  (`user_id`, optional `medication_id`, optional `reference_cache_id`, `query_fingerprint`,
  `intent`, `personalized_text`, `locale`, `llm_meta`, timestamps, `expires_at`) with unique
  `(user_id, query_fingerprint)` and RLS for `anon`.
- **Drug cache wiring**: With Supabase configured, **`CachingDrugData`** backs
  **`drug_reference_cache`** (read-through for TFDA/OpenFDA snippets; TTL
  **`MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS`**). **`run_assistant_text_turn`** uses
  **`SupabaseDrugCaches`** for **`drug_personalization_cache`**: cache hit short-circuits before
  remote drug fetch / LLM compose; after compose, replies are saved (fingerprint includes
  medication-list snapshot via **`personalization_fingerprint`**; TTL
  **`MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS`**).
- **Medication comprehension prototype (Expo)**: Home links to **Medication helper** (`app/companion.tsx`) — chat with **Read aloud**, large type, suggested questions, and optional **`POST /v1/app/messages`** when `EXPO_PUBLIC_USE_MOCK_DATA` is false (headers `X-App-User-Id`, optional bearer). Offline mode uses i18n mock explanations (purpose / timing / interactions).
- **Assistant prompts**: For `explain_medication` and `interaction_check` intents, `run_assistant_text_turn` appends locale-specific **companion** instructions so replies emphasize purpose, timing rationale, and interaction cautions without replacing clinical advice.
- **`docs/use-cases.md`**: Documents implemented channels, assistant intents (including drug-cache behavior and **add-medication** grounding), Supabase layers, and Expo companion notes.
- **Supabase `dose_events`**: `user_id`, `medication_id`, `scheduled_at`, optional `taken_at`, with RLS
  policy for `anon` (see `apps/backend/supabase/schema.sql`).
- **Text medication management** in the assistant (`list_medications`, `add_medication`, `remove_medication` intents): parse fields via LLM (Gemini JSON) or mock heuristics, persist with **`UserDataPort.add_medication` / `delete_medication`** (in-memory mock + Supabase). Wired in **`application/medication_intents.py`** for LINE and **`POST /v1/app/messages`**.
- **Add-medication acknowledgment**: After save, reload patient list, fetch **`DrugDataPort`** snippets for the new drug name, and call **`LLMPort.compose_medication_added_reply`** (Gemini + i18n task strings; mocks use **`mocks.llm.medication_added`**) so the reply restates schedule, adds brief grounded context, and falls back to **`medication.added`** if compose fails. Does **not** use **`drug_personalization_cache`** (that remains for explain/interaction only).
- **Observability**: `LOG_LEVEL` (default `INFO`) configures `medbuddy.*` and `uvicorn.error`
  log verbosity; LINE webhook and orchestrator emit structured INFO logs (event types, flow steps,
  reply sizes) without logging raw message text. Render blueprint sets `LOG_LEVEL=INFO`.
- **Assistant turn logs**: each `run_assistant_text_turn` logs `user_key`, `med_count`, and one flat
  line per saved medication (`id`, name, dosage, schedule, `instructions_zh`).
- Dependency **`line-bot-sdk==3.22.0`**; LINE channel uses **`WebhookParser`** / **`SignatureValidator`**
  on **`POST /v1/line/webhook`**, and **`LineHttpClient`** uses **`AsyncMessagingApi`** /
  **`AsyncMessagingApiBlob`** for replies and message content download.
- **Render** deploy: root [`render.yaml`](render.yaml) Blueprint and repo-root [`Dockerfile`](Dockerfile)
  (default path for [Render](https://render.com/) Docker services, context **`.`**) with **`llm`**,
  **`supabase`**, **`tts`** extras and **`PORT`** for production hosts.
- **Supabase** optional persistence in real integration mode: when `SUPABASE_URL` and
  **`SUPABASE_PUBLISHABLE_KEY`** / **`SUPABASE_ANON_KEY`** are set and `medbuddy-api` is installed
  with the **`supabase`** extra, **`UserDataPort`** and **`ConversationStorePort`** use Postgres
  tables in **`apps/backend/supabase/schema.sql`** (RLS policies for the `anon` role; see
  [Supabase API keys](https://supabase.com/docs/guides/api/api-keys)).
- **`application/assistant_turn`**: shared assistant text turn (intent, grounding, LLM) used by
  LINE and **`POST /v1/app/messages`**.
- **Standalone app API** under `/v1/app/`: **`GET /me`**, **`POST /messages`**
  with Pydantic validation; **Bearer** auth (`MEDBUDDY_MOBILE_BEARER_TOKEN`) and **`X-App-User-Id`**
  header (optional Bearer when `MOCK_EXTERNAL_SERVICES=true` for local dev).
- **Standalone app onboarding**: First-launch screen (`app/onboarding.tsx`, gate in `app/_layout.tsx`)
  with large-type fields; **`GET /v1/app/me`** returns profile fields; **`POST /v1/app/onboarding`**
  saves **`preferred_name`**, optional **`age_years`**, **`emergency_contact`**, **`health_notes`**,
  and **`onboarding_completed_at`**. **`UserDataPort.save_onboarding_profile`** (Supabase +
  **`MockUserData`**). Supabase **`users`** gains matching columns with idempotent **`ALTER`** in
  **`schema.sql`**. Expo mock mode persists the same shape via AsyncStorage (**`companionApi`**).
- **Assistant patient context**: **`build_patient_context_for_llm`** prepends onboarding demographics
  to the medication list for **`run_assistant_text_turn`**, medication intents, and drug-cache
  fingerprinting; **`prompts.system_persona`** / **`gemini.reply_instruction`** tell the model to
  address users by preferred name and weigh stated allergies or health notes in safety guidance.

### Changed

- **`GeminiLLM`** default model is **`gemini-2.5-flash`** ( **`gemini-1.5-flash`** often returns **404** on current **`generate_content` / v1beta**). Override with **`GEMINI_MODEL`**.
- **`GeminiLLM`** now uses the **`google-genai`** SDK (`genai.Client` and **`models.generate_content`**) instead of the legacy **`google.generativeai`** package, matching the **`medbuddy-api[llm]`** extra.
- **Render production lock**: when host env **`RENDER`** is true (Render web services), settings force **`MOCK_EXTERNAL_SERVICES=false`**, **`DEBUG=false`**, and **`MEDBUDDY_INTEGRATION=real`** if it was mock. Blueprint sets **`DEBUG=false`** explicitly; see [`render.yaml`](render.yaml).
- **Backend default integrations**: `MOCK_EXTERNAL_SERVICES` now defaults to **`false`** (real LINE/STT/TTS/LLM/drugs when configured). Local mock runs: `make be-dev` / `make be-dev-mock` or set `MOCK_EXTERNAL_SERVICES=true` / `MEDBUDDY_INTEGRATION=mock`.
- **LINE / Supabase**: removed **`users.consent_accepted`** and the consent quick-reply gate; **follow** sends a plain welcome (**`line.follow_welcome`**). Existing DBs: **`alter table public.users drop column if exists consent_accepted;`**
- **Supabase schema trim**: dropped unused **`created_at`** from **`public.users`** and **`public.medications`** (listing meds orders by **`id`**). See migration comments at the top of **`apps/backend/supabase/schema.sql`**.
- **`public.conversation_turns`**: timestamps are **`created_at`** only (append-only turns; no **`updated_at`**). **`SupabaseConversationStore`** maps **`created_at`** to **`ConversationTurn.at`**. Upgrade SQL is commented in **`schema.sql`**.
- **Docker image**: one repo-root **`Dockerfile`** (build context `.`) for Render’s default
  **`./Dockerfile`** path, **`compose.yaml`**, and **`make be-build`**; removed **`apps/backend/Containerfile`**.
- **Supabase env**: `SUPABASE_SERVICE_ROLE_KEY` removed in favor of **`SUPABASE_PUBLISHABLE_KEY`**
  (or **`SUPABASE_ANON_KEY`**) so the backend uses the low-privilege key per
  [Supabase API keys](https://supabase.com/docs/guides/api/api-keys); `supabase/schema.sql` adds
  RLS policies for role `anon`.
- **Integrations layout**: concrete adapters (`line_client`, `gemini_llm`, `supabase_stores`, …)
  live next to **`integrations/mocks/`** (no **`integrations/real/`** subpackage); imports use
  **`medbuddy.integrations.<module>`**.
- Backend package layout: **delivery channels** (`channels/line`, `channels/mobile`), shared HTTP
  infrastructure (`http/shared_routes.py`), and `deps.get_services`; LINE pipeline moved out of
  `engine/` into `channels/line/`. New JSON endpoints `GET /v1/app/health` and `GET /v1/app/info`
  for the standalone app.

## [0.0.1] - 2026-04-05

### Added

- MedBuddy monorepo: FastAPI backend (`apps/backend`) with LINE webhook pipeline, mock/real
  integrations, and pytest suite.
- Expo (React Native) app (`apps/frontend`) with medication-focused UI, i18n (en, zh-TW), and
  ESLint + TypeScript checks.
- Container and Compose definitions (repo-root `Dockerfile`, `compose.yaml`).
- Repo automation: root `Makefile`, pre-commit (full backend lint/tests + frontend `npm run check`,
  require `CHANGELOG.md` staged with other changes), helper scripts under `scripts/`.
- Contributor UX: `.cursor/commands` (branch, commit, draft PR), `.cursor/rules` for backend and
  frontend standards, `.github/pull_request_template.md`, `.env.example` files, and `.gitignore`
  tuned for Python, Node, coverage, and local env files.
