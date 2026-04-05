# MedBuddy backend

FastAPI LINE webhook server with protocol-based integrations and **mock adapters** for tests and local work.

Paths below are relative to **`apps/backend/`**.

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

Code loads copy with **`medbuddy.i18n.t`**, for example `t("orchestrator.consent_accepted", locale=svc.settings.locale)`. Keys use dotted paths; values may use `{name}`-style placeholders for `.format()`.

**Settings**

| Variable | Meaning |
|----------|---------|
| `MEDBUDDY_LOCALE` or `locale` | BCP 47 tag (`zh-TW`, `en`, …). Default: **`zh-TW`**. |

Copy [`.env.example`](.env.example) to `apps/backend/.env` or the repo root `.env` and set `MEDBUDDY_LOCALE` as needed. The same `locale` is passed into integrations from [`container.py`](src/medbuddy/container.py) so replies, prompts, and LINE UI strings stay consistent.

If a key is missing in the active locale, lookup falls back to **`zh-TW`**. For tests that replace locale files, call **`clear_i18n_cache()`** from `medbuddy.i18n`.

## Integrations

Wiring is centralized in [`src/medbuddy/container.py`](src/medbuddy/container.py): **`build_app_services(settings)`** chooses mock vs real implementations.

| Port | Mock (`MEDBUDDY_INTEGRATION=mock` or `MOCK_EXTERNAL_SERVICES=true`) | Real (`MEDBUDDY_INTEGRATION=real` or `MOCK_EXTERNAL_SERVICES=false`) |
|------|----------------------------------------|------------------|
| **LINE** | [`integrations/mocks/line.py`](src/medbuddy/integrations/mocks/line.py) — records replies | [`integrations/real/line_client.py`](src/medbuddy/integrations/real/line_client.py) — needs `LINE_CHANNEL_ACCESS_TOKEN` |
| **LLM** | [`integrations/mocks/llm.py`](src/medbuddy/integrations/mocks/llm.py) | [`integrations/real/gemini_llm.py`](src/medbuddy/integrations/real/gemini_llm.py) — needs `GEMINI_API_KEY` (install with `pip install 'medbuddy-api[llm]'`) |
| **STT** | [`integrations/mocks/stt.py`](src/medbuddy/integrations/mocks/stt.py) | [`integrations/real/stt_whisper.py`](src/medbuddy/integrations/real/stt_whisper.py) — needs `WHISPER_SERVICE_URL` |
| **TTS** | [`integrations/mocks/tts.py`](src/medbuddy/integrations/mocks/tts.py) | [`integrations/real/edge_tts_service.py`](src/medbuddy/integrations/real/edge_tts_service.py) — optional `edge-tts` extra |
| **Drugs** | [`integrations/mocks/drugs.py`](src/medbuddy/integrations/mocks/drugs.py) | [`integrations/real/drugs_http.py`](src/medbuddy/integrations/real/drugs_http.py) — OpenFDA HTTP + TFDA stub |
| **Object storage** | In-memory mock | [`integrations/real/local_public_storage.py`](src/medbuddy/integrations/real/local_public_storage.py) when `public_base_url` is set |
| **Users / conversations** | In-memory mocks | Same in current prototype; Supabase fields exist in settings for future use |

**Environment (see [`.env.example`](.env.example))**

- **`MOCK_EXTERNAL_SERVICES`** — `true` for local dev and tests; `false` to hit real LINE and optional cloud services.
- **`LINE_CHANNEL_SECRET`**, **`LINE_CHANNEL_ACCESS_TOKEN`** — required for real LINE when mocks are off.
- **`PUBLIC_BASE_URL`** — HTTPS base for audio URLs LINE can fetch.
- **`GEMINI_API_KEY`**, **`WHISPER_SERVICE_URL`** — optional real LLM/STT when not using mocks.

With `MOCK_EXTERNAL_SERVICES=true`, HMAC verification is skipped if `LINE_CHANNEL_SECRET` is empty. Set real LINE secrets and `MOCK_EXTERNAL_SERVICES=false` for integration against LINE APIs.

Protocol definitions: [`src/medbuddy/protocols/ports.py`](src/medbuddy/protocols/ports.py).  
Intent overrides without changing routing: [`src/medbuddy/extensibility/intent_hooks.py`](src/medbuddy/extensibility/intent_hooks.py).

## Quick start (Podman)

From the **repository root**:

```bash
make be-compose
```

Or:

```bash
podman compose up --build
```

Health: `GET http://localhost:8000/health`  
Webhook: `POST http://localhost:8000/v1/line/webhook`

## Development (without Make)

```bash
cd apps/backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export MOCK_EXTERNAL_SERVICES=true
uvicorn medbuddy.main:app --reload --host 0.0.0.0 --port 8000
pytest -q
```
