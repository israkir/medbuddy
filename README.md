# MedBuddy

MedBuddy is a **patient-facing medication companion** built around a **FastAPI** backend. **Primary product:** **LINE Messaging** (chat, voice, dose reminder push) plus shared assistant logic, persistence, and drug lookup. **Secondary:** an **HTTP API** (`/v1/app/*`) for the same core without LINE.

The monorepo also includes an **Expo (React Native)** app under `apps/frontend/` as a **reference and future mobile client** — documented separately so it is not mixed with LINE/backend features: **[`docs/frontend-expo.md`](docs/frontend-expo.md)**.

See the per-app READMEs for day-to-day development details.

> **Disclaimer:** MedBuddy is a software prototype. It is **not** a substitute for professional medical advice, diagnosis, or treatment.

---

## Architecture at a glance

```
┌──────────────────┐   ┌────────────────────────────┐
│  LINE Messaging  │   │  HTTP clients (optional    │
│  (webhook, push) │   │  reference mobile app)     │
└────────┬─────────┘   └─────────────┬──────────────┘
         │                           │
         ▼                           ▼
┌──────────────────────────────────────────────┐
│             FastAPI backend                  │
│  /v1/line/...        /v1/app/...             │
│                                              │
│   channels/line    channels/mobile           │
│           ↓               ↓                  │
│      application/assistant_turn()            │
│              ↓                               │
│         agents/MedicationAgent               │
│    (interpret turn → tools)                  │
│              ↓                               │
│   protocols/ports (hexagonal boundary)       │
│      ↓           ↓          ↓                │
│  integrations/  integrations/ integrations/  |
│  gemini_llm    supabase_stores drugs_http    │
└──────────────────────────────────────────────┘
         ↓              ↓
    Supabase (Postgres)  Gemini or OpenAI (LLM)
    Redis + arq          OpenFDA / TFDA
```

The backend follows **hexagonal architecture** (ports & adapters) with an **agent-dispatch** pattern. See [`docs/architecture.md`](docs/architecture.md) for the full technical design.

---

## Prerequisites

- **[GNU Make](https://www.gnu.org/software/make/)** — task runner (`make` / `make help`).
- **Backend:** Python **3.11+** (virtualenv created automatically by `make be-install`).
- **Frontend:** [Node.js](https://nodejs.org/) 18+ and npm.

---

## Quick start

**Backend** (mock integrations — no external API keys needed):

```bash
make be-install       # create .venv + install all backend extras
make be-dev-mock      # API with hot-reload, all external calls mocked
make be-test          # pytest suite
```

**Frontend:**

```bash
make fe-install       # npm install in apps/frontend
make fe-dev           # Expo dev server (mock data, no backend needed)
make fe-check         # ESLint + TypeScript
```

Run **`make`** or **`make help`** for all targets (`be-*` = backend, `fe-*` = frontend).

**Docker (mock, no secrets needed):**

```bash
make be-compose       # podman/docker compose up --build
# API at http://localhost:8000
```

**Switch to real integrations:** see [Mock vs real](apps/backend/README.md#mock-vs-real-integrations) and copy [`.env.example`](apps/backend/.env.example).

---

## Repository layout

| Path | Role |
|------|------|
| [`apps/backend/`](apps/backend/) | FastAPI service — LINE webhooks, mobile REST API, agent core |
| [`apps/frontend/`](apps/frontend/) | Expo (iOS & Android) — **reference / future** client; see [`docs/frontend-expo.md`](docs/frontend-expo.md) |
| [`Dockerfile`](Dockerfile) | Repo-root image (API + optional arq worker) |
| [`compose.yaml`](compose.yaml) | Local container orchestration |
| [`render.yaml`](render.yaml) | [Render](https://render.com/) blueprint — see [Deploy on Render](apps/backend/README.md#deploy-on-render) |
| [`Makefile`](Makefile) | Root task runner |

---

## API endpoints (overview)

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Plain-text liveness (load balancers) |
| `POST /v1/line/webhook` | LINE Messaging API webhook |
| `GET /v1/app/health` | JSON health for mobile clients |
| `GET /v1/app/info` | Public service metadata |
| `GET /v1/app/me` | User profile (incl. IANA **`timezone`**) |
| `POST /v1/app/onboarding` | First-run profile save (optional **`timezone`**) |
| `POST /v1/app/messages` | Chat turn (returns `{"reply":"…"}`) |
| `GET /v1/app/summary` | Doctor-ready health summary |
| `POST /internal/reminders/reconcile` | Cron safety net for dose reminders |

Full API reference: [`docs/architecture.md#api-reference`](docs/architecture.md#api-reference).

---

## Documentation

| Resource | What you'll find |
|----------|------------------|
| [`docs/architecture.md`](docs/architecture.md) | **Technical design document** — architecture, data model, API reference, integrations, security |
| [`docs/prd.md`](docs/prd.md) | **Product requirements** — vision, goals, personas, functional/non-functional requirements, roadmap hints |
| [`docs/features.md`](docs/features.md) | Product features at a glance (LINE, HTTP API, assistant, caching, reminders) |
| [`docs/use-cases.md`](docs/use-cases.md) | Narrated flows, example utterances, channels, intents |
| [`docs/frontend-expo.md`](docs/frontend-expo.md) | **Reference / future:** Expo app only (not mixed with primary LINE + backend docs) |
| [`docs/reminders.md`](docs/reminders.md) | LINE dose reminders: schema, arq/Redis, Compose, Render, reconcile |
| [`docs/privacy.md`](docs/privacy.md) | PII handling, LLM redaction, profile parsing, compliance notes |
| [`apps/backend/README.md`](apps/backend/README.md) | Package layout, env vars, mock vs real, LINE testing, deploy |
| [`apps/frontend/README.md`](apps/frontend/README.md) | Expo workflow, mock vs API, i18n, simulator targets |
| [`CHANGELOG.md`](CHANGELOG.md) | [Keep a Changelog](https://keepachangelog.com/) history |

---

## Integrations (summary)

| Service | Role | Required for real mode |
|---------|------|----------------------|
| **LINE Messaging API** | Webhook + push reminders | `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN` |
| **LLM** (Gemini or OpenAI) | Intent classification, reply composition, extraction | `LLM_PROVIDER=gemini` → `GEMINI_API_KEY`; `LLM_PROVIDER=openai` → `OPENAI_API_KEY` (defaults: `gemini-2.5-flash`, `gpt-4.1-mini`) |
| **Supabase (Postgres)** | Users, medications, conversations, drug caches, dose events | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` |
| **Redis + arq** | Deferred dose reminder jobs | `REDIS_URL` |
| **OpenFDA HTTP** | Drug label grounding | automatic (HTTP) |
| **Google Speech-to-Text** | Speech-to-text for LINE voice | `GOOGLE_SPEECH_API_KEY`, `GOOGLE_SPEECH_PROJECT_ID` |
| **edge-tts** | Text-to-speech for LINE voice replies | installed via `[tts]` extra |

All integrations have **mock adapters** — run the full stack locally with `MEDBUDDY_INTEGRATION=mock`.

---

## Localization

- **Backend:** `apps/backend/src/medbuddy/locales/` — `zh-TW.json` (primary) and `en.json`; server locale via `MEDBUDDY_LOCALE` (default `zh-TW`).
- **Frontend:** `apps/frontend/locales/` — same language pair; user overrides saved in AsyncStorage.

---

## Contributing and quality

1. Install hooks after backend setup: **`make pre-commit-install`**.
2. Backend: **`make be-check`** (lint + format + tests). Frontend: **`make fe-check`** (ESLint + TypeScript).
3. Behavior changes → add an entry in [`CHANGELOG.md`](CHANGELOG.md).
4. Keep secrets in `.env` files (see each app's `.env.example`).

Pull requests are welcome.
