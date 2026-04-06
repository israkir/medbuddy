# MedBuddy

MedBuddy is a **patient-facing medication companion**: a FastAPI backend plus an **Expo (React Native)** app. People can interact through **LINE** and/or the **standalone mobile client**; both channels share the same assistant, drug lookup, and persistence logic.

This repository is a **monorepo**. Use the docs linked below for day-to-day development; the backend and frontend READMEs hold environment variables, mocks, and deployment detail.

## Prerequisites

- **[GNU Make](https://www.gnu.org/software/make/)** — task runner at the repo root (`make` / `make help`).
- **Backend:** Python **3.11+** (virtualenv created via `make be-install`).
- **Frontend:** [Node.js](https://nodejs.org/) and npm (see `apps/frontend/`).

## Quick start

**Backend** (from the repository root):

```bash
make be-install   # create .venv + install backend deps
make be-dev       # API with reload (mock integrations by default)
make be-test      # pytest
```

**Frontend:**

```bash
make fe-install   # npm install in apps/frontend
make fe-dev       # Expo dev server (mock data by default)
make fe-check     # ESLint + TypeScript
```

Run **`make`** or **`make help`** for all targets (`be-*` backend, `fe-*` frontend).

Switching **mock vs real** integrations (env and Make aliases): [`apps/backend/README.md`](apps/backend/README.md#mock-vs-real-integrations) · mobile flags: [`apps/frontend/.env.example`](apps/frontend/.env.example) and **`make fe-dev-api`**.

## Repository layout

| Path | Role |
|------|------|
| [`apps/backend/`](apps/backend/) | FastAPI: LINE webhooks (`/v1/line/...`) and app JSON (`/v1/app/...`); shared `medbuddy` package |
| [`apps/frontend/`](apps/frontend/) | Expo app (iOS & Android) — patient UI prototype |
| [`compose.yaml`](compose.yaml) | Container orchestration (with repo-root `Dockerfile`) |
| [`render.yaml`](render.yaml) | [**Render**](https://render.com/) blueprint — see [Deploy on Render](apps/backend/README.md#deploy-on-render) |

## Documentation

| Resource | What you’ll find |
|----------|------------------|
| [`docs/use-cases.md`](docs/use-cases.md) | Product flows, example utterances, channels, intents, caches |
| [`apps/backend/README.md`](apps/backend/README.md) | Package layout, env vars, mocks, LINE/mobile auth, localization, deploy |
| [`apps/frontend/README.md`](apps/frontend/README.md) | Expo workflow, mock vs API, i18n, simulator targets |
| [`CHANGELOG.md`](CHANGELOG.md) | [Keep a Changelog](https://keepachangelog.com/) history and notable behavior changes |

## Integrations (overview)

The backend can use **mock** adapters or real services: **LINE Messaging API**, **Google Gemini**, **Whisper** (HTTP STT), **edge-tts**, **OpenFDA** / TFDA placeholders, and optional **Supabase** — all driven by environment variables. For tables, defaults, and wiring, see **`apps/backend/README.md`**.

## Localization

- **Backend:** JSON under `apps/backend/src/medbuddy/locales/` (`zh-TW`, `en`); server default via `MEDBUDDY_LOCALE` / `.env` (see `apps/backend/.env.example`).
- **Frontend:** `i18next` + JSON under `apps/frontend/locales/`.

Adding a language: add matching `*.json` in both trees and register in backend settings/loaders and `apps/frontend/i18n/index.ts` (details in the per-app READMEs).

## Contributing and quality

- Install hooks after backend setup: **`make pre-commit-install`**. Run **`make pre-commit-run`** before a large change-set.
- Backend: **`make be-lint`**, **`make be-fmt`**, **`make be-check`**. Frontend: **`make fe-lint`** / **`make fe-check`**.
- User-visible or behavior changes should be reflected in [`CHANGELOG.md`](CHANGELOG.md) per repo convention.

Pull requests are welcome. Keep secrets out of git; use `.env` files from each app’s `.env.example`.

## Disclaimer

MedBuddy is a software prototype. It is **not** a substitute for professional medical advice, diagnosis, or treatment.
