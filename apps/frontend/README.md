# MedBuddy mobile app (Expo)

React Native client for **iOS** and **Android**, built with [Expo](https://docs.expo.dev/) and [expo-router](https://docs.expo.dev/router/introduction/).

Paths below are relative to **`apps/frontend/`**.

## Makefile (from repository root)

From the repo root: **`make fe-install`** → **`make fe-dev`** or **`make fe-dev-mock`** (mock data, default) / **`make fe-dev-api`** (`EXPO_PUBLIC_USE_MOCK_DATA=false` for a future live API).

| Make target | What it runs |
|-------------|----------------|
| **`make fe-build`** | `npm run typecheck` (`tsc --noEmit`) only |
| **`make fe-lint`** / **`make fe-check`** | `npm run check` → **ESLint** + **TypeScript** (same as `cd apps/frontend && npm run check`) |

In this directory you can also run **`npm run lint`** (ESLint with `eslint-config-expo`), **`npm run typecheck`**, or **`npm run check`** (both). **`npm run lint:fix`** applies ESLint auto-fixes.

## Mock vs real API

Copy [`.env.example`](.env.example) to **`.env`** here. Flags are read at bundle time via **`EXPO_PUBLIC_*`**:

| Variable | Default | Meaning |
|----------|---------|---------|
| `EXPO_PUBLIC_USE_MOCK_DATA` | `true` | Prototype uses local/mock data until HTTP clients are wired. |
| `EXPO_PUBLIC_API_BASE_URL` | `http://127.0.0.1:8000` | Backend base URL for future requests. |

Runtime helpers: [`constants/integration.ts`](constants/integration.ts) (`useMockData`, `apiBaseUrl`).

## Language in the UI

The **設定 / Settings** tab lets users choose **繁體中文（台灣）** or **English**. The choice is stored with **`@react-native-async-storage/async-storage`** (`i18n/languageStorage.ts`) and applied on launch before the splash screen hides. Device locale still sets the **first** run until the user picks a language (then the saved value wins).

## Localization

UI strings live in JSON files, not in components:

- **`locales/zh-TW.json`** — Traditional Chinese (Taiwan), default fallback.
- **`locales/en.json`** — English.

The app uses **i18next** + **react-i18next**. In screens, use **`useTranslation()`** and **`t('section.key')`**. Initial language comes from **`expo-localization`** (`getLocales()`): Chinese tags map to **`zh-TW`**, English to **`en`**, otherwise **`zh-TW`**. See [`i18n/index.ts`](i18n/index.ts).

To add a language: add `locales/<lang>.json`, import it in `i18n/index.ts`, and add it to the `resources` map and to `resolveInitialLanguage()` if it should auto-select from the device.

## Integrations (prototype)

| Feature | Notes |
|---------|--------|
| **expo-speech** | “Listen” explanations for sample medications (`zh-TW` / `en-US` TTS; follows app language from Settings / device). |
| **expo-av** | Hold-to-talk recording (tab bar mic; medication “visit questions” panel). Prototype flow shows an alert after recording. |
| **AsyncStorage** | App language preference (`i18n/languageStorage.ts`); optional text + voice timestamp for medication visit notes (`storage/medicationQuestionNotes.ts`). |
| **Backend / LINE** | HTTP client not wired in this baseline; copy in `locales` describes LINE + future family invite. |

Native builds: from this directory, **`npx expo run:ios`** / **`run:android`** (Xcode / Android SDK required). Production builds typically use [EAS Build](https://docs.expo.dev/build/introduction/).
