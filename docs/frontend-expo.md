# MedBuddy — Reference mobile client (Expo)

**Status:** **Future product / reference only.** This document describes the **Expo (React Native)** app under `apps/frontend/` for engineers and product planning. It is **not** part of the primary **LINE Messaging + FastAPI** capability story documented in [`features.md`](features.md), [`use-cases.md`](use-cases.md), and [`architecture.md`](architecture.md).

**Disclaimer:** MedBuddy is a software prototype. It is **not** a substitute for professional medical advice, diagnosis, or treatment.

---

## Purpose

| Topic | Detail |
|-------|--------|
| **What this is** | A **reference client** and **UI prototype** for iOS and Android using the same backend assistant as LINE, via **`/v1/app/*`** when live API mode is enabled. |
| **What this is not** | Not the shipped “MedBuddy product” in docs alongside LINE; not mixed with LINE webhook, push reminders, or backend-only features here. |
| **Relationship to backend** | The **authoritative** contract for chat, onboarding, and profile is the **HTTP API** (`POST /v1/app/messages`, onboarding, etc.). This file only describes **how the Expo app consumes** that API and what exists in the **frontend codebase**. |

**See also:** [`apps/frontend/README.md`](../apps/frontend/README.md) — install, scripts, mock vs API, simulators.

---

## Product vision (future)

The app is positioned as a **potential standalone medication companion**: first-run onboarding, tabbed home experience, in-app “Medication helper” chat, optional read-aloud, and (when wired) the same **`run_assistant_text_turn`** behavior as LINE text. **Dose reminders** remain **LINE push only** in the current backend; the Expo app does **not** receive the same proactive reminder pipeline (see [`reminders.md`](reminders.md)).

---

## Stack and layout

| Item | Detail |
|------|--------|
| **Framework** | [Expo](https://docs.expo.dev/) + [expo-router](https://docs.expo.dev/router/introduction/) |
| **Languages** | 繁體中文（台灣） and English (`apps/frontend/locales/`, **i18next**); user override in AsyncStorage |
| **Paths** | Relative to **`apps/frontend/`** |

---

## Screens and flows (reference)

| Area | Path / behavior |
|------|-----------------|
| **Onboarding** | `app/onboarding.tsx`, gated in `app/_layout.tsx` — name, age, gender, emergency contact, health notes; **`lib/companionApi.ts`** submits **`POST /v1/app/onboarding`** including device IANA **`timezone`** (`Intl.DateTimeFormat().resolvedOptions().timeZone`). |
| **Today** | `app/(tabs)/index.tsx` — greeting, link to companion, **`PendingDoseCard`** |
| **Medications** | Catalog, **`MedicationListCard`**, visit questions, **`MedicationQuestionsPanel`**, **expo-speech** listen via **`MedicationExplanationContext`** |
| **Family** | Informational copy; placeholder invite (no backend) |
| **Settings** | Language (zh-TW / en), persisted before splash hides |
| **Medication helper (chat)** | `app/companion.tsx` — messages, **suggested prompts**, **read-aloud** (on-device TTS), rotating chips / prompts toward meds and visit prep (see app for current UX) |
| **Visit summary** | Doctor-ready draft screen; may call **`GET /v1/app/summary`** when API mode is on; local **AsyncStorage** draft for offline or sharing |

---

## Backend integration

| Mode | Behavior |
|------|----------|
| **`EXPO_PUBLIC_USE_MOCK_DATA=true`** (typical local dev) | No backend required; **`companionApi`** can persist onboarding-shaped data locally; chat returns **i18n-only** mock explanations. |
| **`EXPO_PUBLIC_USE_MOCK_DATA=false`** | **`companionApi`** calls **`POST /v1/app/onboarding`**, **`POST /v1/app/messages`**, **`GET /v1/app/summary`** with **`X-App-User-Id`** and optional **`Authorization: Bearer`** per backend config. |

**Commands:** `make fe-dev` / `make fe-dev-mock` vs `make fe-dev-api` (live backend) — see frontend README.

---

## Voice and reminders (limitations vs LINE product)

| Topic | Detail |
|-------|--------|
| **Hold-to-talk prototype** | May use **expo-av**; baseline shows an alert after recording — **not** wired to backend STT. **LINE voice** + Whisper HTTP is the supported voice path in the primary product docs. |
| **Dose reminders** | Backend sends **LINE push** only for LINE `userId` users. **No** Expo local notifications in this codebase slice. |
| **Keyboard / dictation** | Users can still dictate into the chat field via OS keyboard; that text follows the normal **`/v1/app/messages`** path. |

---

## Observability and ops

Frontend logging and analytics are **not** documented as part of the backend observability model. Backend logs **`run_assistant_text_turn`** for HTTP clients the same as LINE (see [`features.md`](features.md) observability section).

---

## Document map

| Document | Role |
|----------|------|
| [`features.md`](features.md) | Primary feature catalog (LINE + backend HTTP API); short pointer to this file |
| [`use-cases.md`](use-cases.md) | Assistant and LINE scenarios; HTTP one-turn flow without Expo-specific UI |
| [`architecture.md`](architecture.md) | System design; HTTP client shown generically |
| [`apps/frontend/README.md`](../apps/frontend/README.md) | Day-to-day Expo development |
