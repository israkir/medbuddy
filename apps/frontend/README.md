# MedBuddy mobile app (Expo)

React Native client for **iOS** and **Android** built with [Expo](https://docs.expo.dev/) and [expo-router](https://docs.expo.dev/router/introduction/). Supports **繁體中文（台灣）** and English.

Paths below are relative to **`apps/frontend/`**.

---

## Screen map

| Screen | File | Description |
|--------|------|-------------|
| **Onboarding** | `app/onboarding.tsx` | First-run form — name, age, gender, emergency contact, health notes. Gated in `app/_layout.tsx` until completed. |
| **Today** | `app/(tabs)/index.tsx` | Greeting, pending dose card, link to companion |
| **Medications** | `app/(tabs)/medications.tsx` | Medication catalog, "Listen" (expo-speech), visit questions panel, hold-to-talk (expo-av) |
| **Family** | `app/(tabs)/family.tsx` | Informational copy + "invite" placeholder |
| **Settings** | `app/(tabs)/settings.tsx` | Language picker (zh-TW / English), profile view |
| **Companion** | `app/companion.tsx` | Chat UI — messages, suggested prompts, read-aloud, rotating starter chips |
| **Doctor summary** | `app/doctor-summary.tsx` | Structured doctor-ready draft — main concern, symptoms, med changes, questions; Share as plain text; backed by AsyncStorage draft |

---

## Makefile (from repository root)

| Make target | What it runs |
|-------------|--------------|
| `make fe-install` | `npm install` in `apps/frontend` |
| `make fe-dev` / `make fe-dev-mock` | Expo dev server, mock data (default) |
| `make fe-dev-api` | `EXPO_PUBLIC_USE_MOCK_DATA=false` — uses live backend |
| `make fe-build` | `tsc --noEmit` (TypeScript check only) |
| `make fe-run-ios` | `npx expo run:ios` — native iOS Simulator (requires Xcode) |
| `make fe-run-android` | `npx expo run:android` — native Android Emulator (requires SDK + AVD) |
| `make fe-lint` / `make fe-check` | ESLint + TypeScript (same as `npm run check`) |

You can also run scripts directly from `apps/frontend/`: `npm run lint`, `npm run typecheck`, `npm run check`, `npm run lint:fix`.

---

## Mock vs real API

Copy [`.env.example`](.env.example) to `.env` here. Flags are read at bundle time via `EXPO_PUBLIC_*`:

| Variable | Default | Meaning |
|----------|---------|---------|
| `EXPO_PUBLIC_USE_MOCK_DATA` | `true` | Use local mock responses (no backend needed). |
| `EXPO_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | Backend base URL when not in mock mode. |

Runtime helpers: [`constants/integration.ts`](constants/integration.ts).

When `EXPO_PUBLIC_USE_MOCK_DATA=false`, the companion and doctor-summary screens call the backend:
- `POST /v1/app/messages` — chat turns
- `GET /v1/app/summary` — doctor-ready health summary

Both require `X-App-User-Id` header (stable per-install ID) and optionally `Authorization: Bearer <token>`.

---

## Language in the UI

The **Settings** tab lets users choose **繁體中文（台灣）** or **English**. The preference is stored in AsyncStorage (`i18n/languageStorage.ts`) and applied before the splash screen hides. Device locale seeds the **first** run; after that, the saved value wins.

---

## Localization

UI strings live in JSON files, not in components:

- `locales/zh-TW.json` — Traditional Chinese (Taiwan), default fallback.
- `locales/en.json` — English.

The app uses **i18next** + **react-i18next**. In screens: `useTranslation()` + `t('section.key')`. Initial language from `expo-localization`: Chinese tags → `zh-TW`, English → `en`, else `zh-TW`. See [`i18n/index.ts`](i18n/index.ts).

To add a language: add `locales/<lang>.json`, import it in `i18n/index.ts`, add to `resources` map and `resolveInitialLanguage()`.

---

## Integrations

| Feature | Status | Notes |
|---------|--------|-------|
| **expo-speech** | Implemented | "Listen" for medication explanations (zh-TW / en-US follows app language) |
| **expo-av** | Prototype | Hold-to-talk recording; shows alert after recording — not wired to backend STT (LINE voice is the primary voice path) |
| **AsyncStorage** | Implemented | Language preference, visit notes draft, doctor summary draft |
| **Backend API** | Conditional | Enabled when `EXPO_PUBLIC_USE_MOCK_DATA=false`; uses `companionApi.ts` |

---

## Native builds

**Simulator (development):**

```bash
make fe-run-ios      # or: npx expo run:ios
make fe-run-android  # or: npx expo run:android
```

**Production / TestFlight / Play internal tracks:** use [EAS Build](https://docs.expo.dev/build/introduction/).

App config: [`app.json`](app.json) (iOS bundle ID: `com.medbuddy.app`, Android package: `com.medbuddy.app`).
