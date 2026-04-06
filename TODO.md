# Production readiness — TODO

Checklists for MedBuddy **backend** (`apps/backend`) and **mobile app** (`apps/frontend`, Expo).

**Backend — current state:** **LINE** (`channels/line`) vs **standalone app** (`channels/mobile`: public `health`/`info`; authenticated **`GET /me`**, **`POST /consent`**, **`POST /messages`** with Bearer + `X-App-User-Id`; Pydantic validation). Shared assistant turn in **`application/assistant_turn`** (used by LINE text/audio replies and mobile messages). **`http/shared_routes`**, **`container`** wiring; mock vs real integrations; in-memory user/conversation stores; Supabase env vars exist but are not wired.

**Frontend — current state:** Expo Router app with mock vs API toggles (`EXPO_PUBLIC_*`); `apiBaseUrl` exists but **HTTP clients are not wired** to the backend **`/v1/app/...`** surface (or other routes) yet — see [`apps/frontend/README.md`](apps/frontend/README.md#integrations-prototype).

## Backend production readiness

### Channel architecture (extend shared core, not duplicate)

- [x] Baseline **`channels/mobile/`** REST: **`GET /me`**, **`POST /consent`**, **`POST /messages`** with Pydantic models; **Bearer** (`MEDBUDDY_MOBILE_BEARER_TOKEN`) + **`X-App-User-Id`** (optional Bearer in mock dev). Further routes (medications, family, etc.) as the Expo app grows.
- [x] **LINE-only** UX remains in **`channels/line/`**; shared assistant text turn lives in **`application/assistant_turn`** (extend this layer when adding workflows both channels need).
- [ ] If the mobile client needs different **CORS** or **API gateway** rules than the LINE webhook, configure at the edge (reverse proxy) or in FastAPI middleware scoped to **`/v1/app`** routes.
- [ ] Optional: **JWT / session** or platform attestation instead of static Bearer when product requirements solidify.

### Configuration and secrets

- [ ] Set **`MEDBUDDY_INTEGRATION=real`** (or **`MOCK_EXTERNAL_SERVICES=false`**) in the production environment; never run mocks in prod.
- [ ] Set **`MEDBUDDY_MOBILE_BEARER_TOKEN`** for standalone app clients when **`MOCK_EXTERNAL_SERVICES=false`** (Bearer required for **`/v1/app/me`**, **`/consent`**, **`/messages`**).
- [ ] Provide **`LINE_CHANNEL_SECRET`** and **`LINE_CHANNEL_ACCESS_TOKEN`**; ensure signature verification is always on (no “mock without secret” path).
- [ ] Set **`PUBLIC_BASE_URL`** to the public **HTTPS** origin the LINE client will use for audio URLs (must match your deployed host).
- [ ] Configure **`GEMINI_API_KEY`**, **`WHISPER_SERVICE_URL`**, and any other real adapters you rely on; document required vs optional fallbacks.
- [ ] Load secrets from a managed store (e.g. cloud secret manager / platform env), not committed files; document rotation.

### Persistence

- [ ] **Implement Supabase (or another DB)** for users and conversation history — settings include `SUPABASE_URL` / publishable key; when unset, wiring uses **`MockUserData`** and **`InMemoryConversationStore`** (see `container.py`).
- [ ] Add migrations/schema and wire **`UserDataPort`** / conversation store to real implementations.

### Object storage and media URLs

- [ ] Replace **`LocalPublicObjectStorage`** + in-process file map with **durable, shared storage** (object store or Supabase storage) so **multiple app instances** and **restarts** do not lose audio or break LINE URLs.
- [ ] Serve or proxy media via HTTPS with stable URLs; align cleanup/TTL with **`audio_temp_ttl_seconds`**.

### Container and dependencies

- [ ] Tune repo-root **`Dockerfile`** / `pip install` extras if you need different production stacks (**`voice`** / **`pydub`**, etc.) or split images per profile.
- [ ] Run **Uvicorn** appropriately for production (**workers** and/or **process manager**, **`--proxy-headers`** if behind a reverse proxy).

### Networking, LINE, and standalone app

- [ ] Terminate **TLS** at load balancer or reverse proxy; forward only to the app over a private network if possible.
- [ ] Register the LINE **webhook URL** (`POST /v1/line/webhook`) in the LINE console and verify end-to-end delivery.
- [ ] Expose **`GET /v1/app/...`** (and future mobile API) on the same **HTTPS** origin the app uses (`EXPO_PUBLIC_API_BASE_URL`); document which paths are **public** vs **authenticated** once auth ships.

### Observability and operations

- [ ] **Structured logging** (JSON), log level per environment, **request/correlation IDs**; avoid logging bodies or tokens.
- [ ] Strengthen **`/health`** (and optionally **`GET /v1/app/health`**) into **liveness** vs **readiness** (e.g. check critical dependencies when applicable).
- [ ] Metrics/alerts with **route/channel** dimensions (e.g. `/v1/line/*` vs `/v1/app/*`): latency, 4xx/5xx, LINE API errors, LLM/STT failures.

### Security and resilience

- [ ] Timeouts and retries on **HTTP clients** (LINE, Gemini, Whisper, drug APIs); consider circuit breaking for external failures.
- [ ] Rate limiting or abuse controls on **public** endpoints (LINE webhook, unauthenticated **`/v1/app`** routes, **`/internal-media`** once hardened).
- [ ] **`debug=false`** in production; review **`/internal-media/{file_id}`** exposure once storage is shared (auth, TTL, size limits).

### Quality and delivery

- [ ] Add **CI** (e.g. GitHub Actions) to run **`make be-test`** and **`make be-lint`** on every PR.
- [ ] Define a **deployment** procedure (compose/Kubernetes/PaaS), env checklist, and rollback strategy.

## References — backend

- Backend env template: [`apps/backend/.env.example`](apps/backend/.env.example)
- Backend docs and package layout: [`apps/backend/README.md`](apps/backend/README.md)
- Routers: [`channels/line/routes.py`](apps/backend/src/medbuddy/channels/line/routes.py), [`channels/mobile/routes.py`](apps/backend/src/medbuddy/channels/mobile/routes.py), [`http/shared_routes.py`](apps/backend/src/medbuddy/http/shared_routes.py)
- Compose defaults: [`compose.yaml`](compose.yaml)

---

## Frontend production readiness

### Configuration and release builds

- [ ] Set **`EXPO_PUBLIC_USE_MOCK_DATA=false`** (or `0`) for production builds that talk to a real API; keep **`EXPO_PUBLIC_USE_MOCK_DATA=true`** only for demos or internal prototypes.
- [ ] Set **`EXPO_PUBLIC_API_BASE_URL`** to the production backend **HTTPS** origin (no `127.0.0.1`); align with backend **`PUBLIC_BASE_URL`** / deployment hostname.
- [ ] Document **per-environment** `.env` or EAS secrets (preview vs production) so bundle-time values cannot be confused across channels.
- [ ] Bump **`version`** in [`apps/frontend/app.json`](apps/frontend/app.json) (and platform-specific build numbers when using EAS) per store release policy.

### Simulator and emulator builds

- [ ] Generate **native iOS** app binaries for **iOS Simulator** — e.g. `npx expo run:ios` from [`apps/frontend`](apps/frontend) (requires Xcode), or an [EAS](https://docs.expo.dev/build-reference/simulators/) profile that outputs a simulator build.
- [ ] Generate **native Android** app binaries for the **Android Emulator** — e.g. `npx expo run:android` (requires Android SDK + AVD), or a debug/emulator-oriented build via EAS.
- [ ] Document prerequisites (Xcode + Simulator, Android Studio + emulator) and use repo **`make fe-run-ios`** / **`make fe-run-android`** (or equivalent scripts) so simulator builds are repeatable for the team.
- [ ] Validate **native modules** (e.g. `expo-av`, mic permissions) on simulator and emulator, not only **Expo Go**, since behavior can differ.

### API integration and data

- [ ] **Wire HTTP client(s)** to `apiBaseUrl` targeting the **`/v1/app/...`** channel (start with **`GET /v1/app/health`** or **`/v1/app/info`** for connectivity checks; add calls as `channels/mobile` grows) — see [`constants/integration.ts`](apps/frontend/constants/integration.ts).
- [ ] Replace mock data paths with real API responses; handle **loading**, **empty**, and **error** states consistently.
- [ ] Define **authentication/session** if the backend requires it (tokens in **secure** storage, not `EXPO_PUBLIC_*`); align with **`channels/mobile`** auth when implemented.

### Builds, signing, and distribution

- [ ] Set up **[EAS Build](https://docs.expo.dev/build/introduction/)** (or your chosen pipeline) for **iOS** and **Android**; configure credentials, provisioning, and **keystore** handling outside the repo.
- [ ] Confirm **`bundleIdentifier`** / **`package`** ([`app.json`](apps/frontend/app.json)) match your final App Store / Play Console apps and legal entity.
- [ ] Add **store listings**: screenshots, privacy policy URL, support URL, content rating questionnaire, and permission rationale (microphone copy already exists for `expo-av`).

### Security and privacy

- [ ] Ensure **no private API keys** ship in the JS bundle; only use **`EXPO_PUBLIC_*`** for values that are safe to expose ([`apps/frontend/.env.example`](apps/frontend/.env.example)).
- [ ] Privacy policy and in-app disclosure for **microphone**, **speech**, **local storage** (AsyncStorage), and any analytics you add.
- [ ] Optional: **certificate pinning** or strict HTTPS-only API calls if threat model requires it.

### Reliability and UX

- [ ] **Offline / poor network** behavior (retry, user messaging); avoid silent failures when the API is unreachable.
- [ ] **Deep links** / **`medbuddy`** scheme ([`app.json`](apps/frontend/app.json)) — test invite flows, password reset, or marketing links if you rely on them.
- [ ] **Accessibility** pass (labels, contrast, Dynamic Type / font scaling where applicable).

### Observability

- [ ] Optional: **crash reporting** and/or **analytics** (e.g. Sentry, Expo telemetry) with privacy review and opt-in where required.
- [ ] Log/metric strategy that does **not** leak PHI or tokens in production.

### Quality and delivery

- [ ] Add **CI** (e.g. GitHub Actions) to run **`make fe-check`** or `cd apps/frontend && npm run check` on every PR.
- [ ] Smoke-test on **iOS Simulator** and **Android Emulator** (`make fe-run-ios` / `make fe-run-android`), then on **real devices** (iOS + Android) before store submission.

## References — frontend

- Frontend env template: [`apps/frontend/.env.example`](apps/frontend/.env.example)
- Frontend docs: [`apps/frontend/README.md`](apps/frontend/README.md) (includes **`make fe-run-ios`** / **`make fe-run-android`**)
- Integration helpers: [`apps/frontend/constants/integration.ts`](apps/frontend/constants/integration.ts)
