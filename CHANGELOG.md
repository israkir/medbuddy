# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Google Cloud Text-to-Speech**: Optional LINE TTS backend (`MEDBUDDY_TTS_PROVIDER=google`) via `GoogleTextToSpeech`, sharing Application Default Credentials with Speech-to-Text. Env: `GOOGLE_TTS_LANGUAGE_CODE`, `GOOGLE_TTS_VOICE_NAME`; `MEDBUDDY_LINE_VOICE_REPLY_FOR_TEXT` sends audio+text when the user messages with text too.
- **LINE TTS locale**: Voice synthesis uses the user's profile locale (`en` / `zh-TW`) on LINE via `TextToSpeechPort.synthesize_to_m4a_url(..., language_code=...)`. `GOOGLE_TTS_LANGUAGE_CODE` optionally pins one language for all users; Edge TTS picks a voice from the same per-request locale.
- **GitHub Actions CI**: Workflow runs backend Black + Ruff + pytest and frontend ESLint + TypeScript on pushes to `main` and on pull requests.
- **Emergency and side-effect intents**: Added `Intent.emergency` (fixed localized emergency reply, no LLM body generation) and `Intent.report_side_effects` with `ReportSideEffectsTool`.
- **Medication update + richer adherence flows**: Added `UpdateMedicationTool`, `ReportMissedDoseTool`, `LogVitalTool`, and side-effect-aware follow-up handling in conversation flows.
- **Medication-add confirmation state**: Added pending confirmation storage for incomplete medication drafts so users can confirm/cancel before save.
- **LINE reminders nudges**: Added optional follow-up nudges via `MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES`.
- **Multi-time daily reminder preferences**: Added structured reminder extraction and persistence for `daily_reminder_local_hhmm_list`.

### Changed

- **Render blueprint**: Google STT and TTS env vars are grouped with `GOOGLE_APPLICATION_CREDENTIALS`; `GOOGLE_SPEECH_LOCATION` defaults to `global` in the blueprint; TTS keys remain dashboard-filled like STT.
- **Google TTS credentials**: Optional `GOOGLE_TTS_APPLICATION_CREDENTIALS` points to a dedicated service-account JSON for Text-to-Speech (e.g. `gcp-tts.json`); when unset, TTS uses default ADC / `GOOGLE_APPLICATION_CREDENTIALS`.
- **Turn interpretation contract**: Replaced `classify_intent` with `interpret_user_turn` returning `TurnInterpretation` (`intent`, `record_pending_dose_as_taken`, `dose_adherence_note`), and wired `ConfirmDoseTool` to those structured fields.
- **Per-user locale behavior**: Standardized locale-aware responses across compose, interaction, medication-added responses, health summary labels, LINE welcome, and reminder pushes.
- **Integration/runtime wiring**: Improved container and app wiring (`InternalMediaPort`, shared HTTP clients in real mode, safer logging defaults, stricter timezone validation).
- **Google Cloud Speech-to-Text**: Replaced REST + `GOOGLE_SPEECH_API_KEY` usage with the official `google-cloud-speech` v2 client (Application Default Credentials). `SpeechToTextPort.transcribe_m4a` accepts optional per-request `language_code`; LINE passes the user's effective locale for transcription.
- **Locale change detection**: Language-switch requests use structured `extract_locale_intent` first (fallback to profile patch), run early in `MedicationAgent`, and intent classification steers phrasing to `update_profile` where appropriate.
- **Supabase naming and schema alignment**: Consolidated profile storage around `patients`/`patient_id` and updated persistence adapters accordingly.
- **Integration package structure**: Reorganized backend adapters into `integrations/llm/`, `integrations/stt/`, and `integrations/persistence/`, and updated imports/tests/docs to match.

### Fixed

- **LINE outbound audio**: Voice replies require publicly reachable **HTTPS** media URLs. If `PUBLIC_BASE_URL` is `http://` or otherwise invalid for LINE, the webhook now falls back to a text-only reply instead of failing the request with `messages[0].originalContentUrl` validation errors.
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

- Refreshed technical and product docs to align with current APIs and assistant behavior:
  `README.md`, `apps/backend/README.md`, `docs/tdd.md`, `docs/features.md`,
  `docs/use-cases.md`, `docs/reminders.md`, `docs/privacy.md`, `docs/llm-context.md`,
  and `docs/prd.md`.

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
