# MedBuddy backend

FastAPI service with **two delivery channels** on the same app: **LINE** (`/v1/line/...`) and the **standalone mobile client** (`/v1/app/...`). Protocol-based integrations and **mock adapters** are shared via [`container.py`](src/medbuddy/container.py).

Paths below are relative to **`apps/backend/`**.

## Package layout

| Area | Role |
|------|------|
| [`channels/line/`](src/medbuddy/channels/line/) | LINE webhook, signature verification, LINE-specific event pipeline |
| [`channels/mobile/`](src/medbuddy/channels/mobile/) | Standalone app JSON API: `auth` (Bearer + `X-App-User-Id`), `schemas`, `routes` (`/me`, `/messages`) |
| [`application/`](src/medbuddy/application/) | Shared use cases: [`assistant_turn.py`](src/medbuddy/application/assistant_turn.py), [`medication_intents.py`](src/medbuddy/application/medication_intents.py) (text add/list/remove meds) |
| [`http/shared_routes.py`](src/medbuddy/http/shared_routes.py) | Ops health and `/internal-media/...` (LINE-accessible audio URLs) |
| [`engine/`](src/medbuddy/engine/) | Shared types (`AppServices`, …) |
| [`integrations/`](src/medbuddy/integrations/), [`protocols/`](src/medbuddy/protocols/) | Adapters and ports — unchanged |

Add new **LINE** behavior under `channels/line/`; extend **app-only** REST under `channels/mobile/`. Shared assistant logic belongs in **`application/`** so LINE and mobile do not duplicate LLM/drug/history steps.

**Standalone app auth:** set **`MEDBUDDY_MOBILE_BEARER_TOKEN`** for protected routes when not in mock mode. Clients send **`Authorization: Bearer <token>`** and **`X-App-User-Id`** (4–128 chars, stable id per install or account). If the token is unset and **`MOCK_EXTERNAL_SERVICES=true`**, Bearer is optional (development only).

## Makefile (from repository root)

The [Makefile](../../Makefile) lives at the repo root. Backend targets use the **`be-`** prefix. Run **`make`** or **`make help`** for a grouped list.

| Area | Commands |
|------|----------|
| Environment | `make be-venv`, `make be-install` |
| Run API | **`make be-dev-mock`** / **`make be-dev`** (reload, mocks), **`make be-dev-real`** (reload, real adapters + `.env`), **`make be-run-prod`**, **`make be-run-prod-real`**, optional `PORT=8080` |
| Tests and quality | `make be-test`, `make be-test-verbose`, `make be-test-cov`, `make be-lint` (Ruff + **Black** `--check`), `make be-fmt` (**Black** format), `make be-check` |
| Containers | `make be-compose`, `make be-build` |
| Cleanup | `make be-clean`, `make be-clean-all` (removes repo-root `.venv`) |

Typical flow: `make be-install` → `make be-dev` → `make be-test`.

## Mock vs real integrations

Switch without code changes:

| Mechanism | Purpose |
|-----------|---------|
| **`MEDBUDDY_INTEGRATION`** | `mock` or `real` (aliases: `local`/`dev` → mock; `live`/`production` → real). When set, **overrides** `MOCK_EXTERNAL_SERVICES`. |
| **`MOCK_EXTERNAL_SERVICES`** | `true` = in-memory LINE/STT/TTS/LLM/drugs/storage; `false` = real clients when keys/URLs are set. |

[`config.py`](src/medbuddy/config.py) loads **`apps/backend/.env`** first, then a **`.env`** in the current working directory (so a repo-root `.env` can override). **`make be-dev-mock`** exports `MEDBUDDY_INTEGRATION=mock` so a stray `real` entry in `.env` does not affect local mock runs. **`make be-dev-real`** exports `MEDBUDDY_INTEGRATION=real`; fill tokens in [`.env.example`](.env.example).

[Podman Compose](../../compose.yaml) defaults to `MEDBUDDY_INTEGRATION=mock`; run with `MEDBUDDY_INTEGRATION=real` (and real secrets) when you are ready to exercise external APIs.

## Localization

User-facing strings are **not** hardcoded in Python. They live in JSON files:

- **`src/medbuddy/locales/zh-TW.json`** — primary locale (Taiwan Traditional Chinese).
- **`src/medbuddy/locales/en.json`** — English mirror.

Code loads copy with **`medbuddy.i18n.t`**, for example `t("prompts.system_persona", locale=svc.settings.locale)`. Keys use dotted paths; values may use `{name}`-style placeholders for `.format()`.

**Settings**

| Variable | Meaning |
|----------|---------|
| `MEDBUDDY_LOCALE` or `locale` | BCP 47 tag (`zh-TW`, `en`, …). Default: **`zh-TW`**. |

Copy [`.env.example`](.env.example) to `apps/backend/.env` or the repo root `.env` and set `MEDBUDDY_LOCALE` as needed. The same `locale` is passed into integrations from [`container.py`](src/medbuddy/container.py) so LLM prompts and user-facing strings stay consistent.

If a key is missing in the active locale, lookup falls back to **`zh-TW`**. For tests that replace locale files, call **`clear_i18n_cache()`** from `medbuddy.i18n`.

## Integrations

Wiring is centralized in [`src/medbuddy/container.py`](src/medbuddy/container.py): **`build_app_services(settings)`** chooses mock vs real implementations.

| Port | Mock (`MEDBUDDY_INTEGRATION=mock` or `MOCK_EXTERNAL_SERVICES=true`) | Real (`MEDBUDDY_INTEGRATION=real` or `MOCK_EXTERNAL_SERVICES=false`) |
|------|----------------------------------------|------------------|
| **LINE** | [`integrations/mocks/line.py`](src/medbuddy/integrations/mocks/line.py) — records replies | [`integrations/line_client.py`](src/medbuddy/integrations/line_client.py) — needs `LINE_CHANNEL_ACCESS_TOKEN` |
| **LLM** | [`integrations/mocks/llm.py`](src/medbuddy/integrations/mocks/llm.py) | [`integrations/gemini_llm.py`](src/medbuddy/integrations/gemini_llm.py) — needs `GEMINI_API_KEY` (install with `pip install 'medbuddy-api[llm]'`) |
| **STT** | [`integrations/mocks/stt.py`](src/medbuddy/integrations/mocks/stt.py) | [`integrations/stt_whisper.py`](src/medbuddy/integrations/stt_whisper.py) — needs `WHISPER_SERVICE_URL` |
| **TTS** | [`integrations/mocks/tts.py`](src/medbuddy/integrations/mocks/tts.py) | [`integrations/edge_tts_service.py`](src/medbuddy/integrations/edge_tts_service.py) — optional `edge-tts` extra |
| **Drugs** | [`integrations/mocks/drugs.py`](src/medbuddy/integrations/mocks/drugs.py) | [`integrations/drugs_http.py`](src/medbuddy/integrations/drugs_http.py) — OpenFDA HTTP + TFDA stub |
| **Object storage** | In-memory mock | [`integrations/local_public_storage.py`](src/medbuddy/integrations/local_public_storage.py) when `public_base_url` is set |
| **Users / conversations** | In-memory mocks | [`integrations/supabase_stores.py`](src/medbuddy/integrations/supabase_stores.py) when **`SUPABASE_URL`** and **`SUPABASE_PUBLISHABLE_KEY`** (or **`SUPABASE_ANON_KEY`**) are set — install **`pip install 'medbuddy-api[supabase]'`**, apply [`supabase/schema.sql`](supabase/schema.sql) (RLS for `anon`); otherwise in-memory |

**Environment (see [`.env.example`](.env.example))**

- **`MOCK_EXTERNAL_SERVICES`** — default **`false`** (real adapters). Use **`true`** (or **`make be-dev-mock`**) for local dev without LINE tokens; tests set mocks explicitly.
- **`LINE_CHANNEL_SECRET`**, **`LINE_CHANNEL_ACCESS_TOKEN`** — required for real LINE when mocks are off.
- **`PUBLIC_BASE_URL`** — HTTPS base for audio URLs LINE can fetch.
- **`GEMINI_API_KEY`**, **`WHISPER_SERVICE_URL`** — optional real LLM/STT when not using mocks.
- **`SUPABASE_URL`**, **`SUPABASE_PUBLISHABLE_KEY`** (or **`SUPABASE_ANON_KEY`**) — optional Postgres persistence via the low-privilege key; never use **`service_role`** in app code ([API keys](https://supabase.com/docs/guides/api/api-keys)).

With `MOCK_EXTERNAL_SERVICES=true`, HMAC verification is skipped if `LINE_CHANNEL_SECRET` is empty. Set real LINE secrets and `MOCK_EXTERNAL_SERVICES=false` for integration against LINE APIs.

## Testing LINE integration

| Layer | What to do |
|-------|------------|
| **Automated** | From repo root: **`make be-test`**, or **`pytest apps/backend/tests/test_webhook_pipeline.py`** and **`test_line_signature.py`**. These exercise **`POST /v1/line/webhook`** with a valid `X-Line-Signature` (when a secret is set) or skip verification in mock-without-secret mode. |
| **Local + mocks** | **`make be-dev-mock`** (or **`be-dev`**). Send HTTP **`POST`** to `http://127.0.0.1:8000/v1/line/webhook` with a JSON body shaped like LINE’s [webhook event](https://developers.line.biz/en/reference/messaging-api/#webhook-event-objects) list. Without **`LINE_CHANNEL_SECRET`**, signature checks are skipped. The mock LINE client records “replies” in memory (see [`integrations/mocks/line.py`](src/medbuddy/integrations/mocks/line.py)). |
| **Real LINE (tunnel)** | Run **`make be-dev-real`** with **`LINE_CHANNEL_SECRET`**, **`LINE_CHANNEL_ACCESS_TOKEN`**, and **`MEDBUDDY_INTEGRATION=real`**. Expose **`PUBLIC_BASE_URL`** as an HTTPS URL LINE can reach (e.g. [ngrok](https://ngrok.com/) or **Cloudflare Tunnel**). In the [LINE Developers Console](https://developers.line.biz/), set the Messaging API webhook URL to **`{PUBLIC_BASE_URL}/v1/line/webhook`**, enable the webhook, and use “Verify” / send a test event. LINE requires HTTPS for webhooks. |
| **Hosted** | After [deploy on Render](#deploy-on-render) (or similar), set **`PUBLIC_BASE_URL`** to that service’s HTTPS origin and use the same webhook path **`/v1/line/webhook`** in the LINE console. |

Protocol definitions: [`src/medbuddy/protocols/ports.py`](src/medbuddy/protocols/ports.py).
Intent overrides without changing routing: [`src/medbuddy/extensibility/intent_hooks.py`](src/medbuddy/extensibility/intent_hooks.py).

## LINE dose reminders (prototype)

When **Supabase** backs users/medications, **add** and **remove** medication intents call **`sync_upcoming_dose_events`**: future **`dose_events`** are recreated from each medication using a **once-daily local time** (**`MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME`**, default `09:00`) in the user’s **`timezone`** (default `Asia/Taipei`) for **`MEDBUDDY_REMINDER_HORIZON_DAYS`** (default `14`). If **`REDIS_URL`** is set and **arq** is installed (`pip install -e ".[reminders]"`; the [repo-root `Dockerfile`](../../Dockerfile) includes this extra), the API enqueues **`send_reminder_for_dose`** jobs with **`_defer_until = scheduled_at`** (UTC). A **separate worker process** must run:

```bash
# After pip install -e ".[dev,reminders,supabase]" or production equivalents
export REDIS_URL=redis://127.0.0.1:6379
arq medbuddy.reminders.worker.WorkerSettings
```

The worker runs [`deliver_dose_reminder`](src/medbuddy/reminders/deliver.py) (**LINE push**, then **`reminder_sent_at`**). **Push copy** comes from **`reminder.line_push`** in locale JSON.

**Container image:** production worker image is built from the repo-root **[`Dockerfile.reminder-worker`](../../Dockerfile.reminder-worker)** (same Python deps as the API image; **`CMD`** is **`arq medbuddy.reminders.worker.WorkerSettings`**). Local stack: **`podman compose --profile reminders up --build`** (see root [`compose.yaml`](../../compose.yaml)) and set **`REDIS_URL=redis://redis:6379`** for **`medbuddy-api`** when that profile is active so the API can enqueue jobs.

Optional safety net: **`POST /internal/reminders/reconcile`** with header **`X-Cron-Secret`** matching **`MEDBUDDY_CRON_SECRET`** re-enqueues jobs for rows that are due but never marked sent (e.g. after Redis or worker restarts). See [`.env.example`](.env.example).

**Long-form doc:** [`docs/reminders.md`](../../docs/reminders.md) (architecture, schema, operations, code map).

## Quick start (Podman)

From the **repository root**:

```bash
make be-compose
```

Or:

```bash
podman compose up --build
```

Health (plain text): `GET http://localhost:8000/health`
Standalone app (JSON): `GET /v1/app/health` · `GET /v1/app/info` (public) · `GET /v1/app/me` · `POST /v1/app/messages` (authenticated; see above)
LINE webhook: `POST http://localhost:8000/v1/line/webhook`

## Deploy on [Render](https://render.com/)

The repo includes a [**Blueprint**](https://render.com/docs/infrastructure-as-code) at [`render.yaml`](../../render.yaml) and a repo-root **[`Dockerfile`](../../Dockerfile)** — Render’s default **Dockerfile path** is **`./Dockerfile`** relative to the repo root; the **build context** must be the **repository root** (so `COPY apps/backend/...` works). [Render](https://render.com/) injects **`PORT`** at runtime and **`RENDER=true`**; the image listens on **`${PORT:-8000}`** and uses **`GET /health`** for health checks. When **`RENDER`** is set, [`Settings`](src/medbuddy/config.py) **always** uses real integrations (`MOCK_EXTERNAL_SERVICES=false`), turns **`DEBUG`** off, and treats **`MEDBUDDY_INTEGRATION=mock`** as **`real`** so a mis-set dashboard env cannot enable mocks.

1. **Create services** — Render Dashboard → **New** → **Blueprint** → connect the repo and apply [`render.yaml`](../../render.yaml). That defines **`medbuddy-api`** (web, **`Dockerfile`**) and **`medbuddy-reminder-worker`** (background worker, **`Dockerfile.reminder-worker`**). Workers cannot use Render’s **free** instance type; the blueprint uses **`plan: starter`** for the worker.
2. **Redis** — Create **Render Key Value** (or use Upstash) and set the same **`REDIS_URL`** on **both** the web service and the worker so the API can enqueue arq jobs and the worker can consume them.
3. **Environment** — For **each** service, set dashboard secrets (`sync: false` in the blueprint): **`PUBLIC_BASE_URL`**, **`LINE_CHANNEL_*`**, **`GEMINI_API_KEY`**, Supabase keys, **`MEDBUDDY_MOBILE_BEARER_TOKEN`**, **`REDIS_URL`**, optional **`MEDBUDDY_CRON_SECRET`** for **`POST /internal/reminders/reconcile`**, etc. (see [`.env.example`](.env.example)).
4. **LINE** — Webhook URL: `{PUBLIC_BASE_URL}/v1/line/webhook`.
5. **Mobile / clients** — Point API calls at the same **`PUBLIC_BASE_URL`**; use **`GET /v1/app/health`** or **`GET /health`** for checks.

**Without Docker:** use a **Python** runtime with **root directory** `apps/backend`, build command
`pip install --upgrade pip && pip install ".[llm,supabase,tts,reminders]"`, start command
`uvicorn medbuddy.main:app --host 0.0.0.0 --port $PORT`, and a **second** service or task running
`arq medbuddy.reminders.worker.WorkerSettings` with the same env (**`REDIS_URL`**, Supabase keys, **`LINE_CHANNEL_ACCESS_TOKEN`**).

## Development (without Make)

```bash
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export MOCK_EXTERNAL_SERVICES=true
uvicorn medbuddy.main:app --reload --host 0.0.0.0 --port 8000
pytest -q
```
