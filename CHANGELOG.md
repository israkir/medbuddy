# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`POST /v1/app/messages/voice`** (standalone HTTP): multipart audio upload → Speech-to-Text (profile **`locale`**) → same assistant turn as text → JSON **`reply`** + **`transcript`**. Expo uses **expo-speech** for playback on the client.
- **LINE voice replies**: After the assistant generates text, optional **Google Cloud Text-to-Speech** (MP3 → **m4a** via **ffmpeg**) plus ephemeral **`GET /v1/line/media/audio/{id}`** URLs let LINE receive **text + audio** in one reply batch. Toggle with **`MEDBUDDY_LINE_VOICE_REPLIES`** (`audio_inbound` default, `always`, or `off`). Requires **`PUBLIC_BASE_URL`** as **HTTPS** reachable by LINE, **`GOOGLE_SPEECH_PROJECT_ID`** (shared with STT / ADC), and **ffmpeg** on the server (included in the repo **Dockerfile**).
- **Upcoming dose schedule intent**: New `Intent.upcoming_doses` with `ListUpcomingDosesTool` answers “what’s next / today / soon” from materialized `dose_events` (not guessed frequency text). `UserDataPort.list_upcoming_dose_events` and shared window/formatting in `reminders/upcoming_display.py`. Patient context for external LLMs now includes the same authoritative schedule block via `application/patient_llm_context.patient_context_for_llm` (used by explain, interaction, side effects, health summary, fallback `compose_reply`, and post-add compose when reminders are already synced).
- **GitHub Actions CI**: Workflow runs backend Black + Ruff + pytest and frontend ESLint + TypeScript on pushes to `main` and on pull requests.
- **Emergency and side-effect intents**: Added `Intent.emergency` (fixed localized emergency reply, no LLM body generation) and `Intent.report_side_effects` with `ReportSideEffectsTool`.
- **Medication update + richer adherence flows**: Added `UpdateMedicationTool`, `ReportMissedDoseTool`, `LogVitalTool`, and side-effect-aware follow-up handling in conversation flows.
- **Medication-add confirmation state**: Added pending confirmation storage for incomplete medication drafts so users can confirm/cancel before save.
- **LINE reminders nudges**: Added optional follow-up nudges via `MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES`.
- **Multi-time daily reminder preferences**: Added structured reminder extraction and persistence for `daily_reminder_local_hhmm_list`.

### Changed

- **Turn interpretation contract**: Replaced `classify_intent` with `interpret_user_turn` returning `TurnInterpretation` (`intent`, `record_pending_dose_as_taken`, `dose_adherence_note`), and wired `ConfirmDoseTool` to those structured fields.
- **Per-user locale behavior**: Standardized locale-aware responses across compose, interaction, medication-added responses, health summary labels, LINE welcome, and reminder pushes.
- **Integration/runtime wiring**: Improved container and app wiring (shared HTTP clients in real mode, safer logging defaults, stricter timezone validation).
- **Google Cloud Speech-to-Text**: Replaced REST + `GOOGLE_SPEECH_API_KEY` usage with the official `google-cloud-speech` v2 client (Application Default Credentials). `SpeechToTextPort.transcribe_m4a` accepts optional per-request `language_code`; LINE passes the user's effective locale for transcription.
- **Locale change detection**: Language-switch requests use structured `extract_locale_intent` first (fallback to profile patch), run early in `MedicationAgent`, and intent classification steers phrasing to `update_profile` where appropriate.
- **Supabase naming and schema alignment**: Consolidated profile storage around `patients`/`patient_id` and updated persistence adapters accordingly.
- **Integration package structure**: Reorganized backend adapters into `integrations/llm/`, `integrations/stt/`, and `integrations/persistence/`, and updated imports/tests/docs to match.

### Fixed

- **Backend locale JSON stability**: Corrected invalid smart-quoted keys/strings in
  `apps/backend/src/medbuddy/locales/en.json` that could break JSON parsing and fail
  backend tests at startup/load time.
- **Medication add-confirm test alignment**: Updated backend test expectations so
  missing instructions alone no longer force add confirmation when dose/schedule
  are explicit, matching current confirmation policy.
- **Google STT (zh-TW)**: Traditional Chinese Taiwan is not supported as `zh-TW` with model `long` on location `global`. STT now sends `cmn-Hant-TW` with model `chirp` and uses a regional endpoint (default `asia-southeast1` when `GOOGLE_SPEECH_LOCATION` is `global`).
- **Medication dose/schedule copy in user locale**: List replies, reminders, confirm-dose options, add/update fallbacks, and incomplete-draft prompts now map stored English placeholders (e.g. `unspecified`) to the profile locale label (e.g. 未註明 for `zh-TW`). When the list still has missing dose or schedule, a short hint invites the user to send them for an update.
- **Google STT transcription**: Normalize language tags sent to Speech-to-Text v2 (short `en`/`zh` → `en-US`/`zh-TW`, underscore → hyphen) so locale-derived codes match API expectations.
- **Reminder materialization correctness**: Fixed multi-time-per-day expansion so `daily_local_hhmm_list` produces all expected `dose_events`.
- **Dose-note persistence**: Follow-up adherence notes now merge into recent taken dose rows when applicable.
- **Settings parsing**: Fixed startup parsing for comma-separated `MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES`.
- **LLM/output consistency**: Improved locale locking and corrected conflicting English prompt scaffolding.
- **Drug cache resolution**: Improved medication-name matching so personalization cache rows retain `medication_id` and grounding provenance more reliably.
- **LINE audio STT resilience**: Webhook audio handling now catches STT HTTP failures and sends a localized fallback reply instead of returning HTTP 500.

### Removed

- `LLMPort.extract_dose_confirmation_note` and related adapters/schemas after adherence was folded into `interpret_user_turn`.
- Obsolete duplicate assistant flow module `application/medication_intents.py`.

### Documentation

- **PRD layout:** [`docs/prd.md`](docs/prd.md) is the **primary** condensed PRD; the full specification is [`docs/prd-extended.md`](docs/prd-extended.md). Removed `docs/prd-condensed.md` (merged into `prd.md`).
- **TDD layout:** [`docs/tdd.md`](docs/tdd.md) is the **primary** condensed TDD (~2 pages); the full design is [`docs/tdd-extended.md`](docs/tdd-extended.md) (former monolithic `tdd.md`).
- **README screenshots:** LINE and mobile concept images live under [`assets/screenshots/`](assets/screenshots/); root README shows multiple LINE samples and links to the feature catalog.
- Removed stale TTS and `internal-media` references from `apps/backend/README.md`,
  `docs/tdd.md`, `docs/tdd-extended.md`, `docs/prd.md`, `docs/features.md`, `docs/frontend-expo.md`,
  `docs/reminders.md`, `docs/use-cases.md`, and root `README.md`; Dockerfile install
  extras now match `pyproject.toml` (`[llm,supabase,reminders]`).

## [0.0.1] - 2026-04-05

### Added

- MedBuddy monorepo: FastAPI backend (`apps/backend`) with LINE webhook pipeline, mock/real
  integrations, and pytest suite.
- Expo (React Native) app (`apps/frontend`) with medication-focused UI, i18n (en, zh-TW), and
  ESLint + TypeScript checks.
- Container and Compose definitions (repo-root `Dockerfile`, `compose.yaml`).
- Repo automation: root `Makefile`, pre-commit (full backend lint/tests + frontend `npm run check`,
  require `CHANGELOG.md` staged with other changes), helper scripts under `scripts/`.
- Contributor UX: `.cursor/commands` (branch, commit, draft PR), `.cursor/rules` for backend and
  frontend standards, `.github/pull_request_template.md`, `.env.example` files, and `.gitignore`
  tuned for Python, Node, coverage, and local env files.
