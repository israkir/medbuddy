# Production readiness — TODO

Future hardening checklists for **backend** (`apps/backend`) and **mobile** (`apps/frontend`, Expo).

**Implemented today:** Shared **`run_assistant_text_turn`** for LINE and **`/v1/app`**; **Supabase** when `SUPABASE_*` is set (**`UserDataPort`**, conversation store, drug caches, **`dose_events`**); **Redis + arq** for LINE dose reminders when **`REDIS_URL`** is set. **Expo** uses **`companionApi`** for **`POST /v1/app/onboarding`**, **`POST /v1/app/messages`**, **`GET /v1/app/summary`** when **`EXPO_PUBLIC_USE_MOCK_DATA=false`**.

---

## Backend

### Architecture

- [x] **`channels/mobile/`** REST for the standalone app; **`channels/line/`** for LINE; shared **`application/assistant_turn`**.

- [ ] If the mobile client needs different **CORS** or **gateway** rules than the LINE webhook, configure at the edge or in FastAPI middleware scoped to **`/v1/app`**.

- [ ] Optional: **JWT / session** or platform attestation instead of static Bearer when product requirements solidify.

### Configuration and secrets

- [ ] Production: **`MEDBUDDY_INTEGRATION=real`** (or **`MOCK_EXTERNAL_SERVICES=false`**); never run mocks in prod.

- [ ] Set **`MEDBUDDY_MOBILE_BEARER_TOKEN`** for **`/v1/app`** protected routes when not in mock dev.

- [ ] **LINE:** **`LINE_CHANNEL_SECRET`**, **`LINE_CHANNEL_ACCESS_TOKEN`**; keep signature verification on in prod.

- [ ] **`PUBLIC_BASE_URL`** — HTTPS origin LINE uses for TTS fetch URLs.

- [ ] LLM: **`GEMINI_*`** or **`OPENAI_*`** per **`LLM_PROVIDER`**; optional Whisper, etc.

- [ ] Secrets from a managed store; document rotation.

### Persistence and media

- [ ] **Supabase** (or other DB) is wired — ensure **`schema.sql`** is applied and migrations are tracked for your deployment process.

- [ ] Replace **`LocalPublicObjectStorage`** with **durable object storage** if you run multiple API instances or need survival across restarts.

### Drug caches (`drug_reference_cache`, `drug_personalization_cache`)

- [ ] **Semantic cache keys for drug-related questions:** Today **`personalization_fingerprint`** and **`drug_reference_cache.query_key`** use **normalized exact user text** (see **`medbuddy/drug_cache_keys.py`**), so paraphrases (“What is metformin for?” vs “Explain metformin”) rarely hit cache. Explore **embedding- or entity-based keys** (e.g. resolved drug name / NDC / canonical query from a small classifier) so **semantically equivalent** questions share **`drug_personalization_cache`** and **`drug_reference_cache`** rows without colliding unrelated intents. Consider privacy (fingerprints on redacted text), TTL, and invalidation when the user’s medication list changes.

### Container and runtime

- [ ] Tune **`Dockerfile`** / extras for your production stack.

- [ ] **Uvicorn** workers / process manager; **`--proxy-headers`** behind a reverse proxy.

### Networking and clients

- [ ] **TLS** at load balancer; LINE **webhook** registered and verified.

- [ ] Mobile **`EXPO_PUBLIC_API_BASE_URL`** matches deployed **`PUBLIC_BASE_URL`** host.

### Observability

- [ ] Optional: JSON logs, correlation IDs; readiness vs liveness; metrics/alerts (LINE vs **`/v1/app`**, LLM/STT failures).

### Security and resilience

- [ ] Timeouts/retries on outbound HTTP; rate limiting on public surfaces; review **`/internal-media`** when storage is shared.

### Quality

- [ ] CI running **`make be-check`** (or equivalent) on PRs; deployment runbook and rollback.

**References:** [`apps/backend/.env.example`](apps/backend/.env.example), [`apps/backend/README.md`](apps/backend/README.md), [`compose.yaml`](compose.yaml).

---

## Frontend (Expo)

### Configuration

- [ ] Production builds: **`EXPO_PUBLIC_USE_MOCK_DATA=false`**; **`EXPO_PUBLIC_API_BASE_URL`** = production HTTPS API.

- [ ] Per-environment EAS / env discipline so preview and production bundles do not mix.

- [ ] Versioning in [`apps/frontend/app.json`](apps/frontend/app.json) per release policy.

### Builds

- [ ] **EAS Build** (or equivalent) for store releases; credentials outside the repo.

- [ ] Simulator/emulator smoke tests (**`make fe-run-ios`**, **`make fe-run-android`**) and real devices before release.

### Integration (largely done)

- [x] **`companionApi`** → **`/v1/app/onboarding`**, **`/messages`**, **`/summary`** when mock is off.

- [ ] Harden **loading / error / offline** UX consistently across screens.

- [ ] **Auth** beyond shared Bearer if the product requires per-user tokens.

### Security and privacy

- [ ] No private keys in the JS bundle (**`EXPO_PUBLIC_*`** only where intentional).

- [ ] Store listings, privacy policy, permission rationale (mic, etc.).

### Observability

- [ ] Optional: crash reporting / analytics with privacy review.

### Quality

- [ ] CI: **`make fe-check`** on PRs.

**References:** [`apps/frontend/.env.example`](apps/frontend/.env.example), [`apps/frontend/README.md`](apps/frontend/README.md).
