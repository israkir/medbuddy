# MedBuddy — Use cases

**Disclaimer:** MedBuddy is a software prototype. It is **not** a substitute for professional medical advice, diagnosis, or treatment.

## How this document relates to the feature catalog

| Document | Focus |
|----------|--------|
| **This file (`use-cases.md`)** | **Scenarios:** entry points, every implemented interaction, example utterances, and how a turn flows through the backend. |
| **[`features.md`](features.md)** | **Capabilities:** product-style feature specs (summary, user value, boundaries). Primary product: **LINE + backend**; HTTP API without UI detail. |
| **[`frontend-expo.md`](frontend-expo.md)** | **Reference / future:** Expo client only — not expanded here. |

---

## Interaction map (what calls what)

| Kind | Implemented today |
|------|-------------------|
| **Assistant chat** | **`run_assistant_text_turn`** → **`AgentTurnResult`** (`reply` + optional **`metadata`**). Used by **LINE** (text + STT transcript from voice), **`POST /v1/app/messages`**, and **`POST /v1/app/messages/voice`** (after STT). Core implementation: [`MedicationAgent`](../apps/backend/src/medbuddy/agents/medication_agent.py) + [`run_tool_agent_loop`](../apps/backend/src/medbuddy/agents/orchestrator.py). |
| **LINE-only (no full assistant turn)** | **`follow`** → `get_user_profile` (LINE `language`) may **`patch_user_profile`** (`locale`) → fixed welcome i18n (`line.follow_welcome`). **`postback`** → logged, **no reply** (unhandled). Unsupported **`message`** types (e.g. sticker, image) → logged, **no assistant reply**. |
| **HTTP without chat pipeline** | **`GET /v1/app/health`**, **`GET /v1/app/info`**, **`GET /v1/app/me`**, **`POST /v1/app/onboarding`**, **`GET /v1/app/summary`** — auth + user store / LLM as documented below. |
| **Infrastructure** | **`GET /health`**, **`POST /internal/reminders/reconcile`** (cron). |
| **LINE TTS asset** | **`GET /v1/line/media/audio/{id}`** — ephemeral m4a blob when voice replies are enabled (see `features.md` §1.1). |

---

## 1. Entry points

### 1.1 LINE Messaging API

| Event / message | User-visible outcome | Process |
|-----------------|----------------------|---------|
| **`follow`** | Fixed **welcome** (i18n `line.follow_welcome`) in the user’s effective locale. | `get_or_create_user` → optional **`get_user_profile`** → if LINE **`language`** maps to `en` / `zh-TW`, **`patch_user_profile`** → **`run_assistant_text_turn` is not called.** |
| **`message` · text** | Assistant reply (text). | Webhook verified → `run_assistant_text_turn(user_key=line_user_id, user_text=…)` → `reply_text` to LINE. |
| **`message` · audio** | Assistant reply: **text** by default; optional **text + audio** when LINE voice replies are enabled. | Download audio → **STT** (`transcribe_m4a`) → same `run_assistant_text_turn` on transcript. Reply mode depends on `MEDBUDDY_LINE_VOICE_REPLIES` (`off` / `audio_inbound` / `always`). |
| **`postback`** | *(None)* | Parsed `action` is logged; **no user reply** (placeholder for future rich UI). |
| **`message` · other types** (sticker, image, …) | *(None)* | Logged as unsupported; **no** `run_assistant_text_turn`. |

**Welcome copy (English, example):**

> Welcome to MedBuddy! I'll help you remember your medications and answer any medication-related questions (this does not replace doctor's or pharmacist's instructions). Please also let me know what you'd like to hear in one sentence: your preferred name, age (optional), family contact information, or any allergies/important health conditions—just type it out and send it to me; I can add it later.

**Welcome copy (繁體中文（台灣）, example):**

> 歡迎使用 MedBuddy！我會陪您記好用藥，也會回答用藥相關問題（不取代醫師或藥師指示）。請用一句話告訴我您希望我先知道的事，例如怎麼稱呼您、年齡（選填）、家人聯絡方式，或過敏／重要健康狀況；直接打字傳給我就可以，之後也能再補。

**One-line user replies after welcome (繁體中文 examples)** — typically classified as **`update_profile`** on the next text message:

- 叫我老王就好，今年 62 歲。
- 請叫我李阿姨；有事聯絡我兒子張偉，手機 138-xxxx-xxxx。
- 我對青黴素過敏，吃頭孢要小心。
- 我有糖尿病和高血壓，平常吃二甲雙胍和纈沙坦。
- 叫我小陳，30 歲；家屬電話：我愛人 139-xxxx-xxxx；我對海鮮過敏，有氣喘。
- 叫我張叔；兒子電話 138-xxxx-xxxx；無過敏。

---

### 1.2 Standalone HTTP API (`/v1/app`)

Same **user store** and **`user_key`** model as LINE (`external_user_id`); auth: **`X-App-User-Id`**, optional **`Authorization: Bearer`** when configured.

| Method / path | Assistant pipeline? | Behavior |
|---------------|---------------------|----------|
| **`GET /v1/app/health`** | No | JSON health response for HTTP clients. |
| **`GET /v1/app/info`** | No | Public API metadata (non-secret). |
| **`GET /v1/app/me`** | No | Profile + **`locale`**, **`timezone`**, onboarding timestamp. While **`onboarding_completed_at`** is null, optional **`X-MedBuddy-Locale`** (device tag) or **first** **`Accept-Language`** entry may **`patch_user_profile`** so stored **`locale`** matches the client before onboarding is submitted. |
| **`POST /v1/app/onboarding`** | No | **`UserDataPort.save_onboarding_profile`** — name, optional age, gender, contacts, notes, **IANA `timezone`**, **`locale`** (`en` \| `zh-TW`). |
| **`POST /v1/app/messages`** | **Yes** | Body `{"text":"…"}` → **`run_assistant_text_turn`** → JSON **`{"reply":"…","metadata":{}}`** (metadata often empty; e.g. **`simulated_emergency_notification`** when the simulated caregiver-notify tool ran). |
| **`POST /v1/app/messages/voice`** | **Yes** | Multipart **`file`** → **STT** (`transcribe_m4a`, language from profile **`locale`**) → same assistant pipeline → `{"reply":"…","transcript":"…","metadata":{}}`. |
| **`GET /v1/app/summary`** | No (dedicated tool path) | **`GenerateHealthSummaryTool`** with full history/meds — structured **doctor summary** JSON (+ `plain_text`), not the same JSON shape as chat-only summary text. |

**Reference UI:** Expo **`Medication helper`** calls **`POST /v1/app/messages`** and **`POST /v1/app/messages/voice`** when live API mode is on — see [`frontend-expo.md`](frontend-expo.md).

---

## 2. Assistant pipeline (`run_assistant_text_turn`)

All **chat** turns share this flow (LINE text/voice transcript, **`POST /v1/app/messages`**, and **`POST /v1/app/messages/voice`** after STT).

1. **Redact** PII for LLM inputs (`redact_pii_text` on the current line).
2. **Load** user row + medication list **and** recent conversation turns **in parallel**; call **`interpret_user_turn`** with **recent redacted dialogue** (`MockLLM` in tests). Result: **`TurnInterpretation`** — drives steps **6–8** below (**emergency** / **`off_topic`**); otherwise logged for observability.
3. Resolve **effective locale** from `user_row`.
4. **Append** the **user** turn to the conversation store (**raw** user text).
5. **Early exits (pending / language)** — in order:
   - **`try_locale_change_reply`** when the user asked to switch reply language (returns assistant message; no orchestrator).
   - **`try_resolve_pending_medication_add_confirmation`** when an incomplete **add** is waiting for yes/no/corrected details.
   - **`try_resolve_pending_dose_clarification`** when **which dose** is ambiguous.
   - **`try_resolve_pending_reminder_horizon`** when **how many days** of daily reminders is still unanswered. (Chronic / `is_indefinite` saves never enter this state — they get the `llm.added_indefinite` reply at save time instead.)
6. **`emergency`** — if classified intent is **`emergency`**, return fixed **`agent.emergency`** (**§3.14**) (no LLM reply body). When **at least one row exists in `emergency_contacts`** for the patient, the same branch additionally appends the simulated outreach line listing **every contact on file** (via **`emergency_contacts_hint_all`**) and returns **`metadata.simulated_emergency_notification = true`** for the app banner (i18n key `agent.emergency_with_saved_contact`).
7. **Emergency-contact capture from chat** — **`try_resolve_emergency_contact_from_message`** persists Taiwan-mobile + relationship lines (or replies after the assistant asked for the contact) to the **`emergency_contacts`** table **before** the tool loop, so lines like “my son David, 0900111111” are not misrouted into `add_medication`.
8. **Intent hooks** — optional pilot short-circuit (**§5**).
9. **`off_topic`** — fixed **`agent.off_topic`** (**§3.9**).
10. **Tool orchestrator** — **`run_tool_agent_loop`** ([`agents/orchestrator.py`](../apps/backend/src/medbuddy/agents/orchestrator.py)): the model receives **system context** (medication id/name catalog, **`patient_context_for_llm`**), **prior redacted user/assistant turns** from storage (cap **`MEDBUDDY_AGENT_ORCHESTRATOR_HISTORY_TURNS`**, default 12), plus the **current redacted** user line, then calls **`LLMPort.complete_chat_with_tools`** in a loop (OpenAI native function calling; Gemini structured **`AgentOrchestratorStep`**). The server executes **named tools** (list/add/update/remove meds, **`remove_all_medications`**, **`disable_reminders`**, upcoming doses, confirm/missed dose, explain, side effects, interactions, vitals, health summary, **`export_health_journal`**, **`update_profile`**, **`simulate_notify_emergency_contact`**, …) and feeds **tool results** back until the model returns a final natural-language reply. Multiple tools may run in one user turn. **`AgentTurnResult`** carries **`metadata`** (e.g. **`simulated_emergency_notification`**) for HTTP clients.
11. **`_maybe_append_pending_reminder`** — if **add-confirm** or **reminder-horizon** is still pending, append a one-line nudge after the main reply.
12. **`append_profile_completion_nudge_if_due`** — when onboarding-style profile fields (name, age, gender, emergency contact, active **health conditions**) are still missing, append a short footer every **`MEDBUDDY_PROFILE_COMPLETION_NUDGE_EVERY_N_USER_TURNS`** user messages (default **12**, **`0`** disables). Staggered per user.
13. **Append** the **assistant** turn and return **`AgentTurnResult`**.

**`interpret_user_turn`** sets **`emergency`** and **`off_topic`** (after hooks). All other behavior is **`run_tool_agent_loop`** — tool names, arguments, and reply prose. Adherence is **`confirm_dose`** tool arguments only.

---

## 3. Chat scenarios (tool-backed) — behaviors and examples

Section titles follow **`Intent`** / tool names for readability. **`interpret_user_turn`** does **not** select tools for the main path. **Examples** are illustrative; the orchestrator picks **`complete_chat_with_tools`** steps from the user message.

### 3.1 `list_medications`

| | |
|--|--|
| **Scenario** | User asks for their saved medication list. |
| **Examples** | 「我的藥清單」 · “What’s on my med list?” |
| **Outcome** | List from **`UserDataPort.list_medications`** + i18n intro or empty state. **No** LLM compose for the list body. The reply uses **`format_patient_medication_context`**: placeholder dose/schedule shows as **`medication.unspecified`**, and if any row is incomplete, **`medication.list_hint_fill_dose_schedule`** is appended. Optional purpose tags and **`medication.list_education_cta`** may follow. |
| **Errors** | Unusual failures → generic agent error message (`agent.generic_error`). |

---

### 3.2 `upcoming_doses`

| | |
|--|--|
| **Scenario** | User asks **when** to take medicines next — soon, later, rest of today, this week, “what’s next,” etc. — from **materialized** reminders, not only static list copy. |
| **Examples** | “What should I take later today?” · 「接下來要吃什麼藥」 · “What’s my schedule?” |
| **Outcome** | **`ListUpcomingDosesTool`**: **`UserDataPort.sync_upcoming_dose_events`**, then **`list_upcoming_dose_events`** over a sliding window (**local midnight** through **7 days**, pending rows only), formatted in the user’s **`patients.timezone`**. **No** LLM compose for the list body. |
| **Contrast** | **`list_medications`** (**§3.1**) is inventory (name, dose, schedule text). **`upcoming_doses`** is clock-ordered **`dose_events`**. Empty schedule means no pending rows in the window (e.g. no reminder metadata yet). |
| **Errors** | Same generic agent error pattern as other tools. |

---

### 3.3 `add_medication`

| | |
|--|--|
| **Scenario** | User adds a drug with dose/schedule in natural language. |
| **Examples** | 「新增阿斯匹靈 100mg 每天飯後」 · `add aspirin 100mg after meals` · 「我每天早上要吃 Losartan 50mg，長期吃」 · `Add levothyroxine 50 mcg every morning, I have to take it for life` (chronic phrasing → `is_indefinite=true`) |
| **Outcome (save now)** | When the draft is **complete** and passes **`medication_draft_needs_add_confirmation`** guardrails: **`UserDataPort.add_medication`** → **`sync_and_enqueue_reminders`** → **`build_post_add_patient_reply`** — **`compose_medication_added_reply`** (or i18n **`medication.added`** fallback) when this is the **only** med on file; when the user **already had one or more other medications**, **`compose_medication_added_primary`** then **`post_add_interaction_crosscheck`** (appended after **`medication.post_add_interaction_bridge`**; separate from chat **`interaction_check`** §3.6). **`check_drug_condition_interactions`** may append condition–drug lines when active health conditions exist. Post-add, if **`needs_horizon_confirmation`**, a **`ReminderHorizonPending`** row may be set so the next message can supply “N days” without re-invoking add intent. **Chronic / lifelong meds** (extracted with `is_indefinite=true` — e.g. *"long-term"*, *"終身"*, *"慢性病用藥"*) skip the horizon question entirely: the row is persisted with `medications.is_indefinite=true`, the reply uses `llm.added_indefinite`, and the rolling-window refill is taken over by the daily chronic resync cron + delivery-time top-up ([`reminders.md`](reminders.md#chronic--indefinite-duration-medications)). |
| **Outcome (confirm first)** | When dose/schedule is missing, unclear, or the utterance lacks evidence the user stated both dose and schedule: **`MedicationAddConfirmationPending`** is stored; user sees conversational **`medication.add_confirm_prompt`** (prose summary of draft fields, not a rigid bullet checklist). Reply **yes** / **no** (or locale equivalents) is handled by **`try_resolve_pending_medication_add_confirmation`** before the next full turn. A **non** yes/no message **does not** clear pending—the normal agent answers (e.g. a drug question) and pending stays until resolved (**`medication.add_confirm_pending_reminder`** may append on later turns). |
| **Incomplete** | No drug name → **`MedicationExtractionError`** → **`medication.add_incomplete`**. |
| **Side effect** | When Supabase + reminders are configured: **dose_events** sync / LINE push — [`reminders.md`](reminders.md). |

---

### 3.4 `remove_medication`

| | |
|--|--|
| **Scenario** | User stops tracking a med. |
| **Examples** | 「停藥普拿疼」 · `remove Tylenol from my list` |
| **Outcome** | Resolve row (**LLM** or mock) → **`delete_medication`** → i18n confirm or **`medication.remove_not_found`**. |
| **Side effect** | Reminder rebuild when configured (same as add). |

---

### 3.5 `explain_medication`

| | |
|--|--|
| **Scenario** | User wants to understand a drug or regimen. |
| **Examples** | 「解釋 Metformin 是做什麼的」 · “Why do I take this blood pressure pill?” |
| **Outcome** | **Personalization cache** hit (Supabase) → cached text + history append, skip fetch/LLM. Else **OpenFDA** (etc.) grounding + **`compose_reply`** with **companion** instructions (purpose, timing, cautions). **Upsert** personalization when composed. |
| **Prefetch** | Drug snippets prefetched in this turn path. |

---

### 3.6 `interaction_check`

| | |
|--|--|
| **Scenario** | Drug–drug or combination questions. |
| **Examples** | 「阿斯匹靈可以跟抗凝血藥一起吃嗎？」 · “Can I take aspirin with my blood thinner?” |
| **Outcome** | Primary path: **`check_interactions_structured`** (interaction-focused companion + full med list in the adapter); optional personalization cache. Fallback: **`compose_reply`** with interaction add-on. Severity labels and recommendation prefix use locale keys under **`interaction.*`**. See §3.3 for the **post-add** path (**`post_add_interaction_crosscheck`**, not this tool). |

---

### 3.7 `request_summary` (in chat)

| | |
|--|--|
| **Scenario** | User asks for a recap or doctor-ready summary **in the conversation**. |
| **Examples** | 「用三句話總結我們聊的」 · “Summarize what we discussed for my doctor.” |
| **Outcome** | **`GenerateHealthSummaryTool`** — structured generation + **reply text** (`as_text()`) stored as the assistant message. |
| **Contrast** | **`GET /v1/app/summary`** returns **JSON** (fields + `plain_text`) without going through the normal single-string chat reply path for the HTTP layer — same tool concept, different transport. |

---

### 3.8 `update_profile`

| | |
|--|--|
| **Scenario** | User updates profile fields **in chat** (name, age, emergency contact, gender, locale, timezone). Allergies/diagnoses use **`manage_health_conditions`**, not **`update_profile`**. |
| **Examples** | Same one-line replies as after LINE welcome; “叫我老王”; “我對青霉素过敏”; “switch to English”; “my timezone is America/New_York”. |
| **Outcome** | **`LLMPort.extract_profile_patch`** (structured output) → **`patch_user_profile`**. Empty parse → **`profile.update_unclear`**. Locale updates are acknowledged in the target language. |
| **Contrast** | Standalone **onboarding** uses **`POST /v1/app/onboarding`** with typed JSON — not this intent. |

---

### 3.9 `off_topic`

| | |
|--|--|
| **Scenario** | Message is **clearly** not medication- or care-related (weather, sports, random chit-chat with no care angle). |
| **Examples** | “What’s the weather today?” · 「今天天氣怎麼樣」 |
| **Outcome** | Fixed **`agent.off_topic`** string in the user’s **effective locale**. **No** `compose_reply`. |
| **Note** | Very short replies that **answer** the assistant about reminders, dosing, or scheduling (e.g. 「一次」, “once”, “7 days”) should **not** be labeled **`off_topic`** — **`interpret_user_turn`** receives **recent context** for that. |

---

### 3.10 `confirm_dose`

| | |
|--|--|
| **Scenario** | User turn is about **adherence logging**: they clearly **took** the scheduled dose and/or want a **note** on the dose record (including a follow-up after they already took it). **`interpret_user_turn`** must set **`record_pending_dose_as_taken`** and/or **`dose_adherence_note`**; intent is usually **`confirm_dose`**, but **slots** drive side effects—not the label alone. |
| **Examples** | 「吃了」 · “I took it” · “took my morning pills” · follow-up: “please note dizziness for my doctor” (note only, after pending cleared). |
| **Outcome** | If at least one adherence slot is set: **`ConfirmDoseTool`** applies them ( **`taken_at`** when **`record_pending_dose_as_taken`**, optional **`dose_events.notes`**). When several **`dose_events`** could match, the tool may set **dose clarification pending** and ask the user to pick a numbered option or **all**. Replies from **`medication.confirm_dose_*`**. If **`confirm_dose`** intent but **no** slots: **`compose_reply`** (e.g. symptom-only line mis-labeled). |
| **Contrast** | Ongoing symptoms **without** an explicit took-dose / dose-log meaning stay **`general_question`** with adherence fields false/null — **no** automatic **`taken_at`**. Different from asking *how* to dose or what to do if you forgot. Side-effect **reports** use **`report_side_effects`** (**§3.15**). |

---

### 3.11 `report_missed_dose`

| | |
|--|--|
| **Scenario** | User explicitly says they missed / skipped / forgot a scheduled dose and wants that captured. |
| **Examples** | 「我早上那次忘記吃了」 · “I skipped that dose” · “I forgot my morning pill” |
| **Outcome** | Marks the latest pending dose window as **missed** (`missed_at`) and acknowledges. Missed rows are excluded from future reminder/nudge delivery. |

---

### 3.12 `update_medication`

| | |
|--|--|
| **Scenario** | User wants to edit an existing medication entry (rename medication, change dosage/schedule, update or clear instructions) without deleting and recreating it. |
| **Examples** | 「把阿斯匹靈改成 81mg」 · “update my metformin to twice daily” · “clear the notes on my blood pressure pill” |
| **Outcome** | Resolve target row + patch fields via structured LLM extraction (`resolve_medication_update`) → `update_medication` persistence path → i18n **`medication.updated`** when saved **instructions** are empty, else **`medication.updated_with_note`**; dose/schedule display uses **`medication.unspecified`** for placeholders. If **dosage** or **schedule** was patched, **`medication.update_reminder_followup`** is appended. If target or patch is unclear, tool asks for clarification / returns a safe user-facing error. |
| **Dose events / reminders** | After a successful update, the reminder lifecycle sync runs: **future** `dose_events` (`scheduled_at > now`) for the user are deleted and regenerated from each medication's stored reminder metadata (`raw_metadata.reminder`), then new jobs are enqueued. Past/current events remain for adherence history. Updating free-text `schedule` changes displayed text in reminder payloads, but reminder timing follows `raw_metadata.reminder` fields (not `schedule` text alone). |

---

### 3.13 `log_vital` · `general_question`

| | |
|--|--|
| **Scenario** | Vital sign in text, small talk, or general medication-adjacent chat. `log_vital` has a dedicated extraction + save tool, while `general_question` goes through conversational fallback (`request_summary` is handled by **`GenerateHealthSummaryTool`** — **§3.7**). |
| **Examples** | 「藥物過量了怎麼辦」 · “What if I doubled my dose?” · 「血壓 130/85」 · 「早安」 |
| **Outcome** | For **`log_vital`**: extract and persist vital data via `LogVitalTool` (acknowledge or ask for missing details). For **`general_question`**: **`compose_reply`** with persona + **de-identified** patient context + history and the user’s **locale**. |
| **Prefetch** | The **main-turn** snippet prefetch (before tools) targets **`explain_medication`**, **`interaction_check`**, and post-save **`add_medication`** only. **`report_side_effects`** loads grounding **inside** its tool. |

---

### 3.14 `emergency`

| | |
|--|--|
| **Scenario** | User language suggests chest pain, severe bleeding, inability to breathe, or other **immediate** emergency situations (classifier-dependent). |
| **Examples** | “I can’t breathe” · 「胸口很痛」 · “severe allergic reaction swelling throat” |
| **Outcome** | Fixed localized **`agent.emergency`** message (call local emergency numbers, seek care). **No** LLM-generated reply body and **no** medication tools on this branch. **When at least one emergency contact is on file**, the reply additionally appends the simulated outreach line as **`simulate_notify_emergency_contact`** (i18n key `agent.emergency_with_saved_contact` + `agent.simulated_emergency_notify`), listing **every** stored contact via **`emergency_contacts_hint_all`**, and the turn metadata sets **`simulated_emergency_notification = true`** so the app can show a banner. Multiple contacts are kept on file per patient; only the most recently saved one is **`is_primary = true`** (older entries are demoted on every save). The copy avoids asking the user to add a contact "for next time" since one is on file. |

---

### 3.15 `report_side_effects`

| | |
|--|--|
| **Scenario** | User says they are **currently experiencing** a symptom they think is from a medication. |
| **Examples** | 「吃完這個藥一直暈」 · “This pill gives me a rash” · “I feel nauseous after my dose” |
| **Outcome** | **`ReportSideEffectsTool`**: grounded reply (OpenFDA/TFDA where available), empathy + expected vs concerning framing, **red-flag** escalation lines, disclaimer to see clinician/pharmacist. Not the same as **`explain_medication`** (hypothetical) or **`confirm_dose`** (took the dose). |

---

### 3.16 Just-in-time medication understanding

| | |
|--|--|
| **Scenario** | User just changed medication data (add/update), reviews a medication list, or receives a reminder and needs a quick “what this medicine is for” cue. |
| **Examples** | Add: 「新增 metformin 500mg 早晚各一次」 · Update: “change aspirin to 81mg” · Reminder follow-up: “what is this one for again?” |
| **Outcome** | Assistant appends a short purpose cue and offers an optional deep-dive CTA. If the user accepts, the next turn routes to existing **`explain_medication`**, **`interaction_check`**, or **`report_side_effects`** behavior. |
| **Event hooks** | **Add success:** always append purpose cue + optional CTA. **Update success:** append cue when identity/dose/schedule/reminder metadata changed. **List flow:** include compact purpose tags only when data is already available and list readability remains high; otherwise prompt on-demand explain. **Reminder flow:** keep primary reminder short; append refresher CTA only when cadence gate passes. |
| **Cadence gate** | Reminder refresher CTA is rate-limited per user+medication (default target: max once every 3-7 days), suppressed after recent explain/interaction turns, and skipped if already shown the same local day. |
| **Microcopy templates** | **EN cue:** `Saved. <med_name> is commonly used for <plain_purpose>.` **EN CTA:** `Want a quick note on common side effects or interaction cautions?` **zh-TW cue:** `已更新。<med_name> 常用於 <plain_purpose>。` **zh-TW CTA:** `要我補充常見副作用或交互作用重點嗎？` |
| **Boundary copy** | **EN:** `This is general information and does not replace your doctor or pharmacist's instructions.` **zh-TW:** `這是一般用藥資訊，不能取代醫師或藥師指示。` |

---

## 4. Caching and persistence (when Supabase is configured)

**Scenario:** Explain/interaction personalization, drug reference cache, conversations, medications, **`patients.locale`**, **`patients.timezone`**, **`dose_events`**.

**Detail:** [`features.md` §6](features.md#6-persistence-and-caching-supabase) · **Reminders:** [`reminders.md`](reminders.md).

Without Supabase: in-memory user/conversation mocks; drug caches not wired.

---

## 5. Extensibility (intent hooks)

**Scenario:** Pilot intercepts a classified intent before **`off_topic`** and **`run_tool_agent_loop`**.

**Process:** [`try_intent_hooks`](../apps/backend/src/medbuddy/extensibility/intent_hooks.py) — if a hook returns a non-empty string, that reply is used. Order in **`MedicationAgent`** after pending resolvers and **`emergency`**: **hooks** → **`off_topic`** → **`run_tool_agent_loop`** (tools include profile patch via **`update_profile`**, adherence via **`confirm_dose`**, etc.).

---

## 6. LINE dose reminder pushes (prototype)

**Trigger:** Successful medication save/update/delete **`UserDataPort`** operations after orchestrator tools (**`add_medication`**, **`update_medication`**, **`remove_medication`**, **`remove_all_medications`**, **`disable_reminders`** follow-up sync, etc.) — same **`sync_and_enqueue_reminders`** path as before.

**User-visible outcome:** **LINE push** near **`scheduled_at`** (not in-app local notifications). Optional **follow-up nudges** after the primary push when **`MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES`** is configured. Optional just-in-time education CTA may be appended only when cadence gate passes — see [`reminders.md`](reminders.md) and [`features.md` §8](features.md#8-line-dose-reminders-prototype).

**Behavior:** **`dose_events`** rebuild from structured **`raw_metadata.reminder`** (e.g. **`daily_local_hhmm_list`** for multiple instants per day) + defaults; **arq** + Redis; primary copy under **`reminder.line_push`**, nudge copy under **`reminder.line_push_nudge`**. The string **`schedule`** field is for **display** in pushes; clock times come from stored reminder prefs populated from add-time extraction, not from parsing **`schedule`** alone. Just-in-time education CTA remains a short optional suffix and never replaces primary reminder text.

**Adherence in chat:** When the user confirms intake via the **`confirm_dose`** tool (or related flows), **`dose_events.taken_at`** can be set without LINE postback (**§3.10**).

**Full reference:** [`reminders.md`](reminders.md).

---

## 7. Measurement for just-in-time understanding

Track these rollout metrics by cohort (pre/post and by locale):

- `education_cue_shown` by source (`add`, `update`, `list`, `reminder`).
- `education_cta_shown` and `education_cta_clicked` (proxy: explain/interaction follow-up within one user turn).
- `education_cadence_suppressed` (cooldown prevented CTA), to validate fatigue controls.
- Reminder outcomes: confirm-dose within 24h and missed-dose rate.
- Safety/quality: grounded explain-turn rate and `education_fallback_uncertain` frequency.
- Guardrails: no >2% absolute drop in reminder confirmations and no >1% absolute rise in negative sentiment/off-topic replies after CTA insertion.

---

## 8. Out of scope (not implemented as primary flows here)

- Clinical diagnosis or replacing clinician/pharmacist judgment.
- **Full TFDA HTTP** — stub returns empty; mocks may imitate TFDA.
- **LINE `postback` handling** — no user-facing action yet.
- **Reference Expo** hold-to-talk → **`POST /v1/app/messages/voice`** — see [`frontend-expo.md`](frontend-expo.md). **LINE** voice notes use the same STT → assistant pipeline; replies are **text** by default and can be **text + audio** when `MEDBUDDY_LINE_VOICE_REPLIES` is enabled. Expo read-aloud remains on-device (expo-speech) after HTTP voice turns.
