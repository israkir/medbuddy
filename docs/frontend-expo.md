# MedBuddy — Reference mobile client (Expo)

**Status:** **Future product / reference only.** This document describes the **Expo (React Native)** app under `apps/frontend/` for engineers and product planning. It is **not** part of the primary **LINE Messaging + FastAPI** capability story documented in [`features.md`](features.md), [`use-cases.md`](use-cases.md), and [`tdd.md`](tdd.md).

**Disclaimer:** MedBuddy is a software prototype. It is **not** a substitute for professional medical advice, diagnosis, or treatment.

---

## Purpose

| Topic | Detail |
|-------|--------|
| **What this is** | A **reference client** and **UI prototype** for iOS and Android using the same backend assistant as LINE, via **`/v1/app/*`** when live API mode is enabled. |
| **What this is not** | Not the shipped “MedBuddy product” in docs alongside LINE; not mixed with LINE webhook, push reminders, or backend-only features here. |
| **Relationship to backend** | The **authoritative** contract for chat, onboarding, and profile is the **HTTP API** (`POST /v1/app/messages`, **`POST /v1/app/messages/voice`**, onboarding, etc.). This file only describes **how the Expo app consumes** that API and what exists in the **frontend codebase**. |

**See also:** [`apps/frontend/README.md`](../apps/frontend/README.md) — install, scripts, mock vs API, simulators.

---

## Product vision (future)

The app is positioned as a **potential standalone medication companion**: first-run onboarding, tabbed home experience, in-app “Medication helper” chat, **hold-to-talk → backend STT** (`/v1/app/messages/voice`), **automatic read-aloud** of replies in the user’s profile language (**expo-speech**), manual **read-aloud** on any bubble, and the same **`run_assistant_text_turn`** core as LINE text. **Dose reminders** remain **LINE push only** in the current backend; the Expo app does **not** receive the same proactive reminder pipeline (see [`reminders.md`](reminders.md)).

### Standalone mobile app (concept)

The repo today centers on LINE and the HTTP API; a **dedicated mobile client** is a product direction, not a shipped guarantee. The screens below are **concept-only** mockups to illustrate that idea—not screenshots of a production app.

<p align="center">
  <img src="../assets/screenshots/mobile-1.png" alt="Concept: standalone app home or main screen" width="260">
  &nbsp;
  <img src="../assets/screenshots/mobile-2.png" alt="Concept: standalone app secondary flow" width="260">
  &nbsp;
  <img src="../assets/screenshots/mobile-3.png" alt="Concept: standalone app detail or settings" width="260">
</p>

---

## Stack and layout

| Item | Detail |
|------|--------|
| **Framework** | [Expo](https://docs.expo.dev/) + [expo-router](https://docs.expo.dev/router/introduction/) |
| **Languages** | 繁體中文（台灣） and English (`apps/frontend/locales/`, **i18next**); user override in AsyncStorage. Home (`today.*`) strings are kept in the same calm, conversational register as backend chat copy where they surface together. |
| **Paths** | Relative to **`apps/frontend/`** |

---

## Screens and flows (reference)

| Area | Path / behavior |
|------|-----------------|
| **Onboarding** | `app/onboarding.tsx`, gated in `app/_layout.tsx` — name, age, gender, emergency contact, free-text health notes (mapped to structured **`health_conditions`** on submit); **`lib/companionApi.ts`** calls **`GET /v1/app/me`** with **`X-MedBuddy-Locale`** (device **`languageTag`**) so the backend can align **`patients.locale`** before **`POST /v1/app/onboarding`**, which sends **`health_conditions`**, device IANA **`timezone`** (`Intl.DateTimeFormat().resolvedOptions().timeZone`), and related profile fields. |
| **Today** | `app/(tabs)/index.tsx` — greeting, link to companion, **`PendingDoseCard`** |
| **Medications** | Catalog, **`MedicationListCard`**, visit questions, **`MedicationQuestionsPanel`**, **expo-speech** listen via **`MedicationExplanationContext`** |
| **Family** | Informational copy; placeholder invite (no backend) |
| **Settings** | Language (zh-TW / en), persisted before splash hides |
| **Medication helper (chat)** | `app/companion.tsx` — messages, **hold mic** (expo-av) → **`sendCompanionVoiceMessage`** → backend STT + reply; **auto speak** reply via **expo-speech** (`locale` from **`GET /v1/app/me`** with i18n fallback); tab bar mic **hands off** recording via **AsyncStorage** + navigate to companion; **suggested prompts**, manual **read-aloud** on assistant bubbles |
| **Visit summary** | Doctor-ready draft screen; may call **`GET /v1/app/summary`** when API mode is on; local **AsyncStorage** draft for offline or sharing |

---

## Backend integration

| Mode | Behavior |
|------|----------|
| **`EXPO_PUBLIC_USE_MOCK_DATA=true`** (typical local dev) | No backend required; **`companionApi`** can persist onboarding-shaped data locally; chat returns **i18n-only** mock explanations. |
| **`EXPO_PUBLIC_USE_MOCK_DATA=false`** | **`companionApi`** calls **`GET /v1/app/me`** (with **`X-MedBuddy-Locale`** when the device provides a tag), **`POST /v1/app/onboarding`**, **`POST /v1/app/messages`**, **`POST /v1/app/messages/voice`** (multipart), **`GET /v1/app/summary`** with **`X-App-User-Id`** and optional **`Authorization: Bearer`** per backend config. Chat JSON may include **`metadata`** (e.g. **`simulated_emergency_notification`**); **`app/companion.tsx`** surfaces a banner when present. |

**Commands:** `make fe-dev` / `make fe-dev-mock` vs `make fe-dev-api` (live backend) — see frontend README.

---

## Voice and reminders (limitations vs LINE product)

| Topic | Detail |
|-------|--------|
| **Hold-to-talk → backend** | **expo-av** recording from **Medication helper** or the **tab bar** mic → **`POST /v1/app/messages/voice`** (`lib/companionApi.ts`). **STT** uses the user’s stored **`locale`** (`en` / `zh-TW`). Success path: show **transcript** + reply, then **expo-speech** reads the reply (profile locale, with i18n fallback). **Web:** voice upload not supported; use keyboard. **`useVoiceRecording`:** if **`onRecordingUri`** is set, the generic “saved” alert is skipped (companion / tab bar). |
| **vs LINE** | **LINE:** voice note → STT → assistant → **text** by default, or **text + m4a** when **`MEDBUDDY_LINE_VOICE_REPLIES`** is enabled (see [`features.md`](features.md) §1.1). **Expo:** after **`POST /v1/app/messages/voice`**, the client **reads the reply aloud** with **expo-speech** in the user’s profile language (not server-synthesized audio unless you add it). |
| **Dose reminders** | Backend sends **LINE push** only for LINE `userId` users. **No** Expo local notifications in this codebase slice. |
| **Keyboard / dictation** | Users can still dictate into the chat field via OS keyboard; that text follows **`POST /v1/app/messages`**. |

---

## Observability and ops

Frontend logging and analytics are **not** documented as part of the backend observability model. Backend logs **`run_assistant_text_turn`** for HTTP clients the same as LINE (see [`features.md`](features.md) observability section).

---

## Document map

| Document | Role |
|----------|------|
| [`features.md`](features.md) | Primary feature catalog (LINE + backend HTTP API); short pointer to this file |
| [`use-cases.md`](use-cases.md) | Assistant and LINE scenarios; HTTP one-turn flow without Expo-specific UI |
| [`tdd.md`](tdd.md) | System design; HTTP client shown generically |
| [`apps/frontend/README.md`](../apps/frontend/README.md) | Day-to-day Expo development |
