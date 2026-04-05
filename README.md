# MedBuddy

Monorepo layout:

| Path | Role |
|------|------|
| [`apps/backend/`](apps/backend/) | FastAPI LINE webhook API (`medbuddy` package) |
| [`apps/frontend/`](apps/frontend/) | Expo (React Native) app for **iOS & Android** — patient UI prototype |

End users may interact through **LINE** and/or the mobile app; the backend receives webhooks and can drive STT, LLM, and TTS.

## Integrations (overview)

| Layer | Role |
|------|------|
| **LINE Messaging API** | Webhook at `POST /v1/line/webhook`; replies, quick-reply consent, audio messages |
| **LLM** | Mock (tests) or **Google Gemini** when `GEMINI_API_KEY` is set and mocks are off |
| **STT** | Mock or **Whisper HTTP** service when `WHISPER_SERVICE_URL` is set |
| **TTS** | **edge-tts** with local temp URLs, or mock |
| **Drug data** | Mock snippets or **OpenFDA** HTTP + TFDA placeholder |
| **Storage** | Mock object store or local public URLs for LINE-accessible audio |

Details, environment variables, and mock vs real wiring: [`apps/backend/README.md`](apps/backend/README.md).

## Mock vs real data

| App | Quick switch |
|-----|----------------|
| **Backend** | **`MEDBUDDY_INTEGRATION=mock`** or **`real`** (overrides `MOCK_EXTERNAL_SERVICES`), or Makefile: **`make be-dev-mock`** / **`make be-dev-real`**. See [`apps/backend/README.md`](apps/backend/README.md#mock-vs-real-integrations). |
| **Mobile** | **`EXPO_PUBLIC_USE_MOCK_DATA`** (see [`apps/frontend/.env.example`](apps/frontend/.env.example)); Makefile: **`make fe-dev-mock`** / **`make fe-dev-api`**. Helpers: [`constants/integration.ts`](apps/frontend/constants/integration.ts). |

## Localization

| App | Mechanism | Defaults |
|-----|-----------|----------|
| **Backend** | JSON bundles under `apps/backend/src/medbuddy/locales/` (`zh-TW`, `en`); `t("key.subkey", locale=...)` in [`medbuddy/i18n.py`](apps/backend/src/medbuddy/i18n.py) | Server locale: `MEDBUDDY_LOCALE` or `locale` in `.env` (see [`apps/backend/.env.example`](apps/backend/.env.example)), fallback `zh-TW` |
| **Mobile** | `i18next` + [`expo-localization`](https://docs.expo.dev/guides/localization/); JSON under `apps/frontend/locales/` | Device language → `zh-TW` or `en`; `fallbackLng: 'zh-TW'` |

Adding a new language: add a matching `*.json` file in each app’s `locales/` folder, register it in the backend `Settings`/loader and in the frontend `i18n/index.ts` resources.

Details: backend [Localization](apps/backend/README.md#localization) · frontend [README](apps/frontend/README.md).

## Makefile (repo root)

From the repository root, [GNU Make](https://www.gnu.org/software/make/) targets are separated by app:

- **Backend** — `be-*` (for example `make be-install`, `make be-dev`, `make be-test`, `make be-compose`).
- **Frontend** — `fe-install`, `fe-dev` / `fe-dev-mock`, `fe-dev-api`, `fe-build` (TypeScript only), **`fe-lint`** / **`fe-check`** (ESLint + TypeScript via `npm run check` in `apps/frontend/`), `fe-test` (placeholder).

Run **`make`** or **`make help`** for grouped targets.

Typical backend flow: `make be-install` → `make be-dev` → `make be-test`.

Typical frontend flow: `make fe-install` → `make fe-dev` → `make fe-lint` (before committing: ESLint + TypeScript).

Details: [`apps/backend/README.md`](apps/backend/README.md) · [`apps/frontend/README.md`](apps/frontend/README.md).
