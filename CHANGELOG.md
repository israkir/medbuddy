# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Text medication management** in the assistant (`list_medications`, `add_medication`, `remove_medication` intents): parse fields via LLM (Gemini JSON) or mock heuristics, persist with **`UserDataPort.add_medication` / `delete_medication`** (in-memory mock + Supabase). Wired in **`application/medication_intents.py`** for LINE and **`POST /v1/app/messages`**.
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

### Changed

- **`GeminiLLM`** now uses the **`google-genai`** SDK (`genai.Client` and **`models.generate_content`**) instead of the legacy **`google.generativeai`** package, matching the **`medbuddy-api[llm]`** extra.
- **Render production lock**: when host env **`RENDER`** is true (Render web services), settings force **`MOCK_EXTERNAL_SERVICES=false`**, **`DEBUG=false`**, and **`MEDBUDDY_INTEGRATION=real`** if it was mock. Blueprint sets **`DEBUG=false`** explicitly; see [`render.yaml`](render.yaml).
- **Backend default integrations**: `MOCK_EXTERNAL_SERVICES` now defaults to **`false`** (real LINE/STT/TTS/LLM/drugs when configured). Local mock runs: `make be-dev` / `make be-dev-mock` or set `MOCK_EXTERNAL_SERVICES=true` / `MEDBUDDY_INTEGRATION=mock`.
- **Consent flow removed**: LINE users can message the bot immediately (no follow-up quick-reply consent); **`POST /v1/app/consent`** and **`consent_accepted`** on **`GET /v1/app/me`** are gone. Supabase **`public.users`** no longer includes **`consent_accepted`** (existing DBs: drop the column or recreate from **`schema.sql`**).
- **Supabase schema trim**: dropped unused **`created_at`** from **`public.users`** and **`public.medications`** (listing meds orders by **`id`**). See migration comments at the top of **`apps/backend/supabase/schema.sql`**.
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
