# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Backend structure & ops (standards alignment)**: **`LLMPort.drug_cache_provenance_id`** replaces **`isinstance(..., MockLLM)`** in agent tools for drug-cache provenance; **`InternalMediaPort`** + **`AppServices.internal_media`** serves **`GET /internal-media/{id}`** without HTTP routes importing storage globals; real mode reuses shared **`httpx.AsyncClient`** instances for OpenFDA (**`HttpDrugData`**) and STT (**`WhisperHttpSTT`**) with teardown in **`lifespan`**. Logging trims health-adjacent and webhook detail (medication names, full LINE events, raw drug-query strings in DEBUG). IANA timezone validation narrows exceptions to **`ZoneInfoNotFoundError`** / **`OSError`**.
- **Turn interpretation (LLM)**: Replaced **`LLMPort.classify_intent`** with **`interpret_user_turn`**, returning **`TurnInterpretation`** (`intent` + **`record_pending_dose_as_taken`** + **`dose_adherence_note`**). **`IntentClassification`** is a single structured output; **`MedicationAgent`** runs **`ConfirmDoseTool`** only when an adherence slot is set, and the tool applies those fields directly (no second-pass dose-note extraction). Prompt/schema describe when to set adherence flags so ambiguous symptom/reply lines do not record **`taken_at`** by accident.

### Documentation

- **`docs/PRD.md`**: Prototype alignment — **text-only** conversational scope, bounded feature set, explicit non-commitment language; **MVP (~3mo)**, **Growth (~1yr)**, **Global (post-1yr)** phased goals; voice/STT/TTS called out as out of prototype product acceptance. Linked from root **`README.md`** documentation table. (Also updated for **`interpret_user_turn`** / adherence slots in this pass.)
- **Docs sweep (API)**: **`docs/architecture.md`**, **`docs/features.md`**, **`docs/use-cases.md`**, **`docs/privacy.md`**, **`docs/llm-context.md`**, **`docs/PRD.md`**, root **`README.md`**, **`apps/backend/README.md`** — describe **`LLMPort.interpret_user_turn`**, **`TurnInterpretation`**, and structured adherence fields; **`classify_intent`** is not documented as the current entrypoint.

### Fixed

- **Multi-daily reminders**: `dose_events` materialization only scheduled **one** local time per day (`iter_scheduled_dose_times_utc`), so “three times daily after meals for N days” produced **N** rows instead of **3×N**. Reminder metadata now supports **`daily_local_hhmm_list`**, structured extraction adds **`daily_reminder_local_hhmm_list`**, and **`iter_dose_instants_for_medication`** fans out each local time across the horizon (times still converted with **`patients.timezone`**).
- **Dose notes after “I took it”**: If the user confirms a dose and later sends a side-effect / doctor note in a **follow-up** message, **`ConfirmDoseTool`** now merges that text into **`dose_events.notes`** on the most recent taken dose (within 48h). Previously, **`mark_pending_doses_taken`** only updated rows with **`taken_at` null**, so the note never persisted. Prompt/schema now steer **`confirm_dose`** and adherence fields for these follow-ups (**superseded path:** notes now come from **`interpret_user_turn`** — see **`### Changed`** above).
- **`Settings`**: **`MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES`** as comma-separated minutes (per **`.env.example`**) no longer crashes startup — **`pydantic-settings`** was JSON-decoding **`list[int]`** before validators, and values like **`15,30,60`** are not valid JSON for a list.

### Removed

- **`LLMPort.extract_dose_confirmation_note`**, OpenAI/Gemini adapters’ implementations, **`DoseConfirmationNoteExtraction`**, and **`MockLLM`**’s stub for that call — dose-row text is **`IntentClassification.dose_adherence_note`** only (same structured call as **`intent`**, via **`interpret_user_turn`**).
- **`application/medication_intents.py`**: Unused duplicate of **`MedicationAgent`** tool flows (LINE and mobile already use **`run_assistant_text_turn`** → **`MedicationAgent`**).

### Added

- **Add-medication confirmation**: When extracted **dose**, **schedule**, or **instructions** are missing or placeholder (per locale **`medication.unspecified`** and common “unknown” tokens), **`AddMedicationTool`** stores a pending draft in **`patients.pending_agent_clarification`** (**`MedicationAddConfirmationPending`**, same TTL as dose disambiguation) and asks the user to confirm or cancel before saving. **`try_resolve_pending_medication_add_confirmation`** runs before dose clarification in **`MedicationAgent`**. Locales **`medication.add_confirm_*`** (**`en`**, **`zh-TW`**).
- **Profile LLM extraction**: **`LLMPort.extract_profile_patch`** (structured outputs on OpenAI and Gemini). Chat profile updates no longer use regex **`parse_profile_patch_from_text`** (removed). *(Later **removed:** standalone **`extract_dose_confirmation_note`** — dose notes use **`interpret_user_turn`** only; see **[Unreleased] → Removed**.)* Shared **`map_intent_label`** lives in **`medbuddy/llm/intent_map.py`**. Locale switches from chat use **`extract_locale_intent`** only when intent is **`update_locale`** (regex fast path removed from **`try_locale_change_reply`**).
- **Gemini intent classification**: Gemini adapter exposed **`classify_intent`** using structured **`IntentClassification`** (same contract as OpenAI) instead of free-text label parsing (**superseded** by **`interpret_user_turn`** — see **[Unreleased]**).
- **LINE dose reminders — nudges**: Optional follow-up pushes after the primary reminder, chained via deferred **arq** jobs (**`send_reminder_nudge`**). Intervals are configured with **`MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES`** (comma-separated minutes between consecutive pushes). **`dose_events`** gains **`reminder_nudge_count`** and **`last_nudge_at`**; nudges stop after the last interval, when the user marks doses taken, or at end of the local calendar day of the scheduled dose. Locale keys **`reminder.line_push_nudge`** (**`en`**, **`zh-TW`**).
- **Adherence — chat confirmation**: **`Intent.confirm_dose`** is handled by **`ConfirmDoseTool`**, which sets **`taken_at`** on the user’s most recent past pending dose instant (all medications scheduled at that time). Copy via **`medication.confirm_dose_recorded`** / **`medication.confirm_dose_none`**. **`MockLLM`** pins **`confirm_dose`** (+ adherence defaults) for tests. (**Superseded:** tool inputs are structured adherence fields from **`interpret_user_turn`** — see **[Unreleased]**.)
- **Assistant**: **`Intent.off_topic`** — the routing model labels clearly non-medical chit-chat; **`MedicationAgent`** returns a localized refusal (**`agent.off_topic`**) without **`compose_reply`**.
- **User locale**: Supabase **`users.locale`** (`en` | `zh-TW`, default **`zh-TW`**); **`medbuddy.user_locale`** helpers; **`POST /v1/app/onboarding`** accepts **`locale`**; **`GET /v1/app/me`** returns **`locale`**. Standalone app onboarding includes a language choice (syncs with **`setAppLanguage`**); **`patch_user_profile`** may update **`locale`**.
- **User timezone**: Shared helpers in **`medbuddy.user_timezone`** (default **`Asia/Taipei`**); **`POST /v1/app/onboarding`** accepts optional **`timezone`** (validated IANA); **`GET /v1/app/me`** returns **`timezone`**. Supabase **`users.timezone`** column comment documents reminder use (existing default **`Asia/Taipei`**).
- **LINE reminders**: Medication extraction now returns structured **reminder preferences** (first reminder in N minutes, whether to materialize daily rows, explicit horizon days 1–90, whether to ask the user for horizon, optional daily HH:MM). Values are stored in **`medications.raw_metadata.reminder`** and drive **`dose_events`** materialization (e.g. “in 5 minutes” → a single upcoming event ~5 minutes ahead without fanning 14 days). The **compose** prompt receives appendix text so the model can confirm one-off timing or ask how many days of daily reminders the user wants. **`MEDBUDDY_REMINDER_*`** env defaults apply when the LLM leaves fields unset; updating prefs from a follow-up user message is not implemented yet.
- **OpenAI**: optional Chat Completions LLM adapter (`OpenAILLM`, default model `gpt-4.1-mini`) implementing the same `LLMPort` contract as Gemini. Set **`LLM_PROVIDER=openai`**, **`OPENAI_API_KEY`**, and optionally **`OPENAI_MODEL`**; **`Settings.active_llm_model_id`** supplies drug-cache provenance. The **`llm`** optional dependency group now includes **`openai`**.
- **Chat vitals, missed doses, medication edits**: Supabase **`vital_logs`** + **`UserDataPort.add_vital_log`**; **`Intent.log_vital`** / **`LogVitalTool`** with **`LLMPort.extract_vital_log`** and **`application/vital_log_build`**. **`dose_events.missed_at`**, **`mark_pending_doses_missed`**, **`Intent.report_missed_dose`** / **`ReportMissedDoseTool`**; pending-dose selection ignores **`missed_at`** rows. **`UpdateMedicationTool`** with **`LLMPort.resolve_medication_update`** and **`UserDataPort.patch_medication`** (reminder materialization re-synced after patch). Locales (**`vital.logged`**, **`medication.missed_dose_*`**, **`medication.update_*`**). Docs: **`docs/use-cases.md`**, **`docs/architecture.md`**, **`docs/llm-context.md`**, **`docs/privacy.md`**.

### Changed

- **Assistant**: LLM patient background now includes the user’s stored **preferred form of address** so replies can greet them by name; system persona and locale strings were updated accordingly (other profile text remains de-identified as before).
- **Mock LLM (tests only)**: **`MockLLM`** no longer infers intent from keywords or parses medication/locale/removal text with regex. Tests pass explicit **`intent=`** and optional **`medication_draft`**, **`locale_intent`**, **`removal_medication_id`** to mirror structured LLM outputs. Production routing **used** **`classify_intent`** + tool extractions on OpenAI/Gemini only (**now** **`interpret_user_turn`** — see **[Unreleased] → Changed**).
- **User locale**: Removed **`parse_locale_request_from_text`** (regex UI-locale detection). Reply language changes rely on **`update_locale`** + **`extract_locale_intent`**.
- **Copy (en / zh-TW)**: Softer **`agent.off_topic`**, **`agent.generic_error`**, **`medication.*`**, **`locale.unclear`**, and **`profile.update_unclear`** strings; intent-classification intro text is slightly warmer.
- **Intent classification**: Shared prompt **`medbuddy/llm/intent_classification_prompt.py`** (`INTENT_CLASSIFICATION_INSTRUCTIONS` + **`format_intent_classification_prompt`**) replaces duplicated OpenAI/Gemini strings. It documents intent→tool behavior, disambiguation (add vs explain vs general_question), and follow-up/off_topic rules in one place. **`IntentClassification`** schema text is shortened to stay in sync via that prompt body.
- **Supabase**: End-user profile table **`public.users`** → **`public.patients`** (room for other user kinds later). Child tables use **`patient_id`** instead of **`user_id`** (`medications`, `conversation_turns`, `dose_events`, `drug_personalization_cache`). Policy **`medbuddy_patients_anon_rw`**; **`SupabaseUserData`** / **`SupabaseDrugCaches`** target the new names.
- **Schema**: Medications column and domain field **`instructions`** replace **`instructions_zh`** (same meaning: optional user notes from extraction). **`apps/backend/supabase/schema.sql`** is a **greenfield** definition (new projects); upgrading existing databases requires separate migrations.
- **Assistant locale**: Replies, tool copy, and LLM prompts use **`users.locale`** (`effective_user_locale`) instead of the global **`MEDBUDDY_LOCALE`** default alone. Users can switch reply language from chat when classification returns **`update_locale`** and **`extract_locale_intent`** (structured LLM) resolves **`en`** vs **`zh-TW`**, with a clarifying message when still ambiguous. **`MedicationAgent`** persists **`locale`** via **`patch_user_profile`** and acknowledges in the new language. LINE **`follow`** welcome and LINE **dose reminder** pushes use the user’s stored locale. **`GET /v1/app/summary`** uses the same per-user locale for the health-summary tool.
- **Profile / reminders**: **`users.timezone`** (IANA, default **`Asia/Taipei`** in Supabase) is set on **`POST /v1/app/onboarding`** (optional **`timezone`**; standalone app sends the device zone) and drives **`dose_events`** scheduling and LINE reminder clock text. **`GET /v1/app/me`** includes **`timezone`**. **`MEDBUDDY_REMINDER_TIMEZONE`** was removed; use per-user **`users.timezone`** (and **`patch_user_profile`** / **`timezone`**) for travel.
- **Deploy**: **`render.yaml`** blueprint default **`LLM_PROVIDER`** is **`openai`** (set **`OPENAI_API_KEY`** in Render secrets; use **`gemini`** here if the service should use **`GEMINI_API_KEY`** instead).
- **Deploy**: Repo-root **`Dockerfile`** runs **uvicorn** and the **arq** reminder worker in one container when **`REDIS_URL`** is set ([`docker-entrypoint-web.sh`](docker-entrypoint-web.sh)). **`render.yaml`** defines **`medbuddy-api`** only. Compose **`reminders`** profile: **Redis** + **`medbuddy-api`** only. Removed duplicate **`Dockerfile.reminder-worker`**; optional scale-out uses the **same** image with **`arq medbuddy.reminders.worker.WorkerSettings`** start command and **uvicorn-only** on the API (never run arq in both).

### Fixed

- **`drug_personalization_cache.medication_id`**: **`resolve_medication_id_for_personalization`** now matches user text against **base names** (text before `(`) and the **first token** of multi-word Latin names, so stored labels like **`阿斯匹靈 (81mg)`** or **`Metformin HCl`** still resolve when the user only says **`阿斯匹靈`** or **`metformin`**. Explain and interaction tools optionally merge **redacted** text for the same check. **`SupabaseDrugCaches.save_personalized_reply`** was already persisting the field; it was often **`NULL`** because resolution failed on formatted list names.

- **Assistant add-medication**: Requests phrased as “set a reminder for [drug] …” were often classified as **`general_question`**, so **`compose_reply`** ran instead of **`AddMedicationTool`** — no medication row and no **`dose_events`**. Turn interpretation (**`classify_intent`** at the time) structured-output prompts (OpenAI + Gemini) and the **`IntentClassification.intent`** schema description now steer reminder / scheduling / “add to my list” phrasing with a concrete drug or dose to **`add_medication`** (intent is LLM-only; no string heuristics after classification). (**Entry point today:** **`interpret_user_turn`**.)
- **English locale prompts**: **`locales/en.json`** `prompts.system_persona` and **`gemini.reply_instruction`** no longer instruct the model to reply in Traditional Chinese; they now match **`en`** (clear, simple English). This removes a contradiction with task-specific English instructions (e.g. medication-added and reminder appendix copy), which caused Chinese replies after switching away from Chinese.

- **Per-user locale for `compose_reply`**: **`LLMPort.compose_reply`** (and **`simplify_drug_text_to_patient_zh`**) take **`locale`** and use it for scaffold copy (**`gemini.reply_instruction`**, section headers, etc.) instead of only the process default **`MEDBUDDY_LOCALE`**. Callers (**`MedicationAgent`** fallback, explain-medication, interaction fallback) pass the user’s **`effective_user_locale`**. **`interaction.*`** locale strings localize structured interaction replies (severity labels, recommendation prefix). **`gemini.simplify_intro`** for **`en`** targets plain English. Structured interaction analysis prompts include **`gemini.interaction_structured_output_note`** so JSON patient-facing fields match the user’s locale.

- **Intent classification**: **`LLMPort.classify_intent`** (now **`interpret_user_turn`**) accepts optional **recent redacted conversation**; **`MedicationAgent`** supplies it so short follow-ups (e.g. reminder or dosing answers) are less often labeled **`off_topic`**. Provider prompts and **`IntentClassification`** schema text narrow **`off_topic`** to clearly unrelated topics.

- **Supabase**: The PostgREST client is created with an **`httpx.Client` using `http2=False`** (postgrest-py defaults to HTTP/2), avoiding intermittent **`RemoteProtocolError` / `ConnectionTerminated`** during user upserts and LINE webhooks.

- **`drug_personalization_cache`**: `save_personalized_reply` now stores **`medication_id`** when exactly
  one list medication name matches the user message (normalized substring), and **`reference_cache_id`**
  when a TFDA/OpenFDA grounding row exists in **`drug_reference_cache`** (OpenFDA preferred if both).
  **`llm_meta.source`** is **`openfda`** / **`tfda`** when that registry grounding was present, otherwise
  the **Gemini model id** from settings (or **`mock_llm`** when mocks are on), marking model-only replies.
- **`drug_reference_cache`**: OpenFDA fetches now persist **`indications_and_usage`**, **`dosage_and_administration`**,
  **`warnings`**, and **`raw_payload`** (`{"label": <fda label object>}`) via **`DrugGrounding`** and
  **`CachingDrugData`**. **`HttpDrugData.fetch_tfda_snippet`** returns **`None`** (no live TFDA client), so
  **`source=tfda`** rows are not created from placeholder copy; only real adapters (e.g. OpenFDA) populate the cache until TFDA is implemented.

### Added

- **Standalone app**: **Visit summary** screen (`doctor-summary`) — structured doctor-ready draft (main concern, symptoms, optional vitals, med changes, questions, carer note), **Share** as plain text, local **AsyncStorage** draft; companion chat **Visit summary** header link, **rotating starter chips** and **occasional post-reply prompts** toward medications list, drug questions, visit prep, interactions, Mandarin/voice, and family/caregiver topics; mock chat replies for those themes when offline.
- **LINE dose reminders (prototype)**: Supabase **`dose_events`** sync after add/remove medication;
  **`reminder_sent_at`** and **`users.timezone`**; **arq** + **`REDIS_URL`** for deferred
  **`send_reminder_for_dose`** jobs; **LINE `push_message`**; **`POST /internal/reminders/reconcile`**
  with **`MEDBUDDY_CRON_SECRET`**; settings **`MEDBUDDY_REMINDER_*`** / **`MEDBUDDY_CRON_SECRET`** /
  **`REDIS_URL`**. Docker image installs **`[reminders]`** extra.
- **Documentation**: **`docs/reminders.md`** — LINE dose reminders (data model, arq/Redis, Render, Compose, reconcile); linked from root **`README.md`**, **`docs/use-cases.md`**, and backend **`README.md`**.
- **Documentation**: **`docs/features.md`** — product features at a glance; linked from root **`README.md`**.
- **Onboarding / profile**: optional **`gender`** (self-reported category: female, male, non-binary, prefer not to say, other)
  on **`users`**, mobile **`POST /v1/app/onboarding`** and **`GET /v1/app/me`**, persona gaps/signals. (Later: chat profile updates use structured **`extract_profile_patch`** — see current **`docs/privacy.md`**.)
- **Documentation**: **`docs/privacy.md`** — how PII is limited for LLM calls, redaction, and operational caveats.
- **Profile in chat (LINE + app)**: **`Intent.UPDATE_PROFILE`** with **`UserDataPort.patch_user_profile`** after structured extraction (**historical note**: early iterations used local regex parsing; current code uses **`LLMPort.extract_profile_patch`**).
- **LLM privacy boundary**: **`redact_pii_text`** / **`redact_conversation_turns_for_llm`** mask emails, typical
  phone shapes, and long digit runs before **turn interpretation** (**`interpret_user_turn`** today; historically **`classify_intent`**), **`compose_reply`**, and medication extract/remove
  calls; **`build_patient_context_for_llm`** sends only **coarse profile signals** (plus medication list), while
  **`build_patient_context_for_chat_display`** keeps full text for **user-facing** list replies. Persona / reply
  instructions state the model must not invent names or raw health/contact details.
- **Supabase `drug_reference_cache`**: global table to cache drug usage / label text
  (`source`, `query_key`, `title`, `usage_text`, optional indication/dosing/warning fields,
  `raw_payload`, `fetched_at`, `expires_at`) with RLS for `anon`, matching other MedBuddy tables.
- **Supabase `drug_personalization_cache`**: per-patient cache for **LLM-personalized** explanations
  (`patient_id`, optional `medication_id`, optional `reference_cache_id`, `query_fingerprint`,
  `intent`, `personalized_text`, `locale`, `llm_meta`, timestamps, `expires_at`) with unique
  `(patient_id, query_fingerprint)` and RLS for `anon`.
- **Drug cache wiring**: With Supabase configured, **`CachingDrugData`** backs
  **`drug_reference_cache`** (read-through for TFDA/OpenFDA snippets; TTL
  **`MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS`**). **`run_assistant_text_turn`** uses
  **`SupabaseDrugCaches`** for **`drug_personalization_cache`**: cache hit short-circuits before
  remote drug fetch / LLM compose; after compose, replies are saved (fingerprint includes
  medication-list snapshot via **`personalization_fingerprint`**; TTL
  **`MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS`**).
- **Medication comprehension prototype (Expo)**: Home links to **Medication helper** (`app/companion.tsx`) — chat with **Read aloud**, large type, suggested questions, and optional **`POST /v1/app/messages`** when `EXPO_PUBLIC_USE_MOCK_DATA` is false (headers `X-App-User-Id`, optional bearer). Offline mode uses i18n mock explanations (purpose / timing / interactions).
- **Assistant prompts**: For `explain_medication` and `interaction_check` intents, `run_assistant_text_turn` appends locale-specific **companion** instructions so replies emphasize purpose, timing rationale, and interaction cautions without replacing clinical advice.
- **`docs/use-cases.md`**: Documents implemented channels, assistant intents (including drug-cache behavior and **add-medication** grounding), Supabase layers, and Expo companion notes.
- **Supabase `dose_events`**: `patient_id`, `medication_id`, `scheduled_at`, optional `taken_at`, with RLS
  policy for `anon` (see `apps/backend/supabase/schema.sql`).
- **Text medication management** in the assistant (`list_medications`, `add_medication`, `remove_medication` intents): parse fields via LLM (Gemini JSON) or test doubles, persist with **`UserDataPort.add_medication` / `delete_medication`** (in-memory mock + Supabase). Routed through **`MedicationAgent`** for LINE and **`POST /v1/app/messages`** (**`application/medication_intents.py`** was removed later as duplicate).
- **Add-medication acknowledgment**: After save, reload patient list, fetch **`DrugDataPort`** snippets for the new drug name, and call **`LLMPort.compose_medication_added_reply`** (Gemini + i18n task strings; mocks use **`mocks.llm.medication_added`**) so the reply restates schedule, adds brief grounded context, and falls back to **`medication.added`** if compose fails. Does **not** use **`drug_personalization_cache`** (that remains for explain/interaction only).
- **Observability**: `LOG_LEVEL` (default `INFO`) configures `medbuddy.*` and `uvicorn.error`
  log verbosity; LINE webhook and orchestrator emit structured INFO logs (event types, flow steps,
  reply sizes) without logging raw message text. Render blueprint sets `LOG_LEVEL=INFO`.
- **Assistant turn logs**: each `run_assistant_text_turn` logs `user_key`, `med_count`, and one flat
  line per saved medication (`id`, name, dosage, schedule, `instructions`).
- Dependency **`line-bot-sdk==3.22.0`**; LINE channel uses **`WebhookParser`** / **`SignatureValidator`**
  on **`POST /v1/line/webhook`**, and **`LineHttpClient`** uses **`AsyncMessagingApi`** /
  **`AsyncMessagingApiBlob`** for replies and message content download.
- **Render** deploy: root [`render.yaml`](render.yaml) Blueprint and repo-root [`Dockerfile`](Dockerfile)
  (default path for [Render](https://render.com/) Docker services, context **`.`**) with **`llm`**,
  **`supabase`**, **`tts`** extras and **`PORT`** for production hosts.
- **Supabase** optional persistence in real integration mode: when `SUPABASE_URL` and
  **`SUPABASE_PUBLISHABLE_KEY`** / **`SUPABASE_ANON_KEY`** are set and `medbuddy-api` is installed
  with the **`supabase`** extra, **`UserDataPort`** and **`ConversationStorePort`** use Postgres
  tables in **`apps/backend/supabase/schema.sql`** (RLS policies for the `anon` role; see
  [Supabase API keys](https://supabase.com/docs/guides/api/api-keys)).
- **`application/assistant_turn`**: shared assistant text turn (intent, grounding, LLM) used by
  LINE and **`POST /v1/app/messages`**.
- **Standalone app API** under `/v1/app/`: **`GET /me`**, **`POST /messages`**
  with Pydantic validation; **Bearer** auth (`MEDBUDDY_MOBILE_BEARER_TOKEN`) and **`X-App-User-Id`**
  header (optional Bearer when `MOCK_EXTERNAL_SERVICES=true` for local dev).
- **Standalone app onboarding**: First-launch screen (`app/onboarding.tsx`, gate in `app/_layout.tsx`)
  with large-type fields; **`GET /v1/app/me`** returns profile fields (including **`timezone`** since
  per-user IANA support); **`POST /v1/app/onboarding`** saves **`preferred_name`**, optional
  **`age_years`**, **`emergency_contact`**, **`health_notes`**, optional **`timezone`**, and
  **`onboarding_completed_at`**. **`UserDataPort.save_onboarding_profile`** (Supabase +
  **`MockUserData`**). Supabase **`users`** gains matching columns with idempotent **`ALTER`** in
  **`schema.sql`**. Expo mock mode persists the same shape via AsyncStorage (**`companionApi`**).
- **Assistant patient context**: **`build_patient_context_for_llm`** prepends onboarding demographics
  to the medication list for **`run_assistant_text_turn`**, medication intents, and drug-cache
  fingerprinting; **`prompts.system_persona`** / **`gemini.reply_instruction`** tell the model to
  address users by preferred name and weigh stated allergies or health notes in safety guidance.

### Changed

- **`GeminiLLM`** default model is **`gemini-2.5-flash`** ( **`gemini-1.5-flash`** often returns **404** on current **`generate_content` / v1beta**). Override with **`GEMINI_MODEL`**.
- **`GeminiLLM`** now uses the **`google-genai`** SDK (`genai.Client` and **`models.generate_content`**) instead of the legacy **`google.generativeai`** package, matching the **`medbuddy-api[llm]`** extra.
- **Render production lock**: when host env **`RENDER`** is true (Render web services), settings force **`MOCK_EXTERNAL_SERVICES=false`**, **`DEBUG=false`**, and **`MEDBUDDY_INTEGRATION=real`** if it was mock. Blueprint sets **`DEBUG=false`** explicitly; see [`render.yaml`](render.yaml).
- **Backend default integrations**: `MOCK_EXTERNAL_SERVICES` now defaults to **`false`** (real LINE/STT/TTS/LLM/drugs when configured). Local mock runs: `make be-dev` / `make be-dev-mock` or set `MOCK_EXTERNAL_SERVICES=true` / `MEDBUDDY_INTEGRATION=mock`.
- **LINE / Supabase**: removed **`users.consent_accepted`** and the consent quick-reply gate; **follow** sends a plain welcome (**`line.follow_welcome`**). Existing DBs: **`alter table public.users drop column if exists consent_accepted;`**
- **Supabase schema trim**: dropped unused **`created_at`** from **`public.users`** and **`public.medications`** (listing meds orders by **`id`**). See migration comments at the top of **`apps/backend/supabase/schema.sql`**.
- **`public.conversation_turns`**: timestamps are **`created_at`** only (append-only turns; no **`updated_at`**). **`SupabaseConversationStore`** maps **`created_at`** to **`ConversationTurn.at`**. Upgrade SQL is commented in **`schema.sql`**.
- **Docker image**: one repo-root **`Dockerfile`** (build context `.`) for Render’s default
  **`./Dockerfile`** path, **`compose.yaml`**, and **`make be-build`**; removed **`apps/backend/Containerfile`**.
- **Supabase env**: `SUPABASE_SERVICE_ROLE_KEY` removed in favor of **`SUPABASE_PUBLISHABLE_KEY`**
  (or **`SUPABASE_ANON_KEY`**) so the backend uses the low-privilege key per
  [Supabase API keys](https://supabase.com/docs/guides/api/api-keys); `supabase/schema.sql` adds
  RLS policies for role `anon`.
- **Integrations layout**: concrete adapters (`line_client`, `gemini_llm`, `supabase_stores`, …)
  live next to **`integrations/mocks/`** (no **`integrations/real/`** subpackage); imports use
  **`medbuddy.integrations.<module>`**.
- Backend package layout: **delivery channels** (`channels/line`, `channels/mobile`), shared HTTP
  infrastructure (`http/shared_routes.py`), and `deps.get_services`; LINE pipeline moved out of
  `engine/` into `channels/line/`. New JSON endpoints `GET /v1/app/health` and `GET /v1/app/info`
  for the standalone app.

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
