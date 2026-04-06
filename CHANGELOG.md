# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

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

### Added

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
- **Standalone app API** under `/v1/app/`: **`GET /me`**, **`POST /consent`**, **`POST /messages`**
  with Pydantic validation; **Bearer** auth (`MEDBUDDY_MOBILE_BEARER_TOKEN`) and **`X-App-User-Id`**
  header (optional Bearer when `MOCK_EXTERNAL_SERVICES=true` for local dev).

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
