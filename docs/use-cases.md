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
| **Assistant chat** | **`run_assistant_text_turn`** — one user text in, one reply string out. Used by **LINE** (text + STT transcript from voice) and **`POST /v1/app/messages`**. Implementation: [`MedicationAgent`](../apps/backend/src/medbuddy/agents/medication_agent.py). |
| **LINE-only (no full assistant turn)** | **`follow`** → fixed welcome i18n (`line.follow_welcome`). **`postback`** → logged, **no reply** (unhandled). Unsupported **`message`** types (e.g. sticker, image) → logged, **no assistant reply**. |
| **HTTP without chat pipeline** | **`GET /v1/app/health`**, **`GET /v1/app/info`**, **`GET /v1/app/me`**, **`POST /v1/app/onboarding`**, **`GET /v1/app/summary`** — auth + user store / LLM as documented below. |
| **Infrastructure** | **`GET /health`**, **`GET /internal-media/{file_id}`** (TTS audio for LINE), **`POST /internal/reminders/reconcile`** (cron). |

---

## 1. Entry points

### 1.1 LINE Messaging API

| Event / message | User-visible outcome | Process |
|-----------------|----------------------|---------|
| **`follow`** | Fixed **welcome** (i18n `line.follow_welcome`). | `get_or_create_user` → **`run_assistant_text_turn` is not called.** |
| **`message` · text** | Assistant reply (text). | Webhook verified → `run_assistant_text_turn(user_key=line_user_id, user_text=…)` → `reply_text` to LINE. |
| **`message` · audio** | Assistant reply: **audio + text** batch (when TTS configured), else behavior follows project settings. | Download audio → **STT** (`transcribe_m4a`) → same `run_assistant_text_turn` on transcript → optional **TTS** URL under `/internal-media/...` + text batch; temp file TTL cleanup. |
| **`postback`** | *(None)* | Parsed `action` is logged; **no user reply** (placeholder for future rich UI). |
| **`message` · other types** (sticker, image, …) | *(None)* | Logged as unsupported; **no** `run_assistant_text_turn`. |

**Welcome copy (English, example):**

> Welcome to MedBuddy! I'll help you remember your medications and answer any medication-related questions (this does not replace doctor's or pharmacist's instructions). Please also let me know what you'd like to hear in one sentence: your preferred name, age (optional), family contact information, or any allergies/important health conditions—just type it out and send it to me; I can add it later.

**Welcome copy (简体中文, example):**

> 欢迎使用 MedBuddy！我会帮您记住用药安排，并回答与用药相关的问题（不能替代医生或药师的医嘱）。请用一句话告诉我您希望我了解的内容，例如：您希望我怎么称呼您、年龄（选填）、家属联系方式，或过敏史 / 重要健康状况——直接打字发给我即可，我稍后可以帮您录入。

**One-line user replies after welcome (简体中文 examples)** — typically classified as **`update_profile`** on the next text message:

- 叫我老王就行，今年 62 岁。
- 请叫我李阿姨；有事联系我儿子张伟，手机 138-xxxx-xxxx。
- 我对青霉素过敏，吃头孢要小心。
- 我有糖尿病和高血压，平时吃二甲双胍和缬沙坦。
- 叫我小陈，30 岁；家属电话：我爱人 139-xxxx-xxxx；我对海鲜过敏，有哮喘。
- 叫我张叔；儿子电话 138-xxxx-xxxx；无过敏。

---

### 1.2 Standalone HTTP API (`/v1/app`)

Same **user store** and **`user_key`** model as LINE (`external_user_id`); auth: **`X-App-User-Id`**, optional **`Authorization: Bearer`** when configured.

| Method / path | Assistant pipeline? | Behavior |
|---------------|---------------------|----------|
| **`GET /health`** | No | JSON `{"status":"ok","channel":"standalone"}`. |
| **`GET /info`** | No | Channel + API version metadata. |
| **`GET /me`** | No | Profile + **`locale`**, **`timezone`**, onboarding timestamp. |
| **`POST /onboarding`** | No | **`UserDataPort.save_onboarding_profile`** — name, optional age, gender, contacts, notes, **IANA `timezone`**, **`locale`** (`en` \| `zh-TW`). |
| **`POST /messages`** | **Yes** | Body `{"text":"…"}` → **`run_assistant_text_turn(user_key=app_user_id, user_text=…)`** → `{"reply":"…"}`. |
| **`GET /summary`** | No (dedicated tool path) | **`GenerateHealthSummaryTool`** with full history/meds — structured **doctor summary** JSON (+ `plain_text`), not the same JSON shape as chat-only summary text. |

**Reference UI:** Expo **`Medication helper`** calls **`POST /messages`** when live API mode is on — see [`frontend-expo.md`](frontend-expo.md).

---

## 2. Assistant pipeline (`run_assistant_text_turn`)

All **chat** turns share this flow (LINE text/voice transcript and **`POST /v1/app/messages`**).

1. **Redact** PII for classification (`redact_pii_text`).
2. **Load** user row + medication list; **classify intent** via **`LLM`** (or mock rules in tests).
3. **Append** the **user** turn to conversation store (raw text).
4. **Locale change (first short-circuit):** [`try_locale_change_reply`](../apps/backend/src/medbuddy/application/locale_intents.py) — see **§3.8** `update_locale`. If it returns a string, **append assistant turn and return** (no hooks/tools below).
5. **Intent hooks** — optional pilot short-circuit (**§5**).
6. **`off_topic`** — fixed refusal string (`agent.off_topic`), **no** `compose_reply` for the body (**§3.9**).
7. **`update_profile`** — regex/heuristic parse + `patch_user_profile` (**§3.7**).
8. **Tool dispatch** — `list` / `add` / `remove` / `explain` / `interaction_check` / `request_summary` (**§3**).
9. **Fallback** — `compose_reply` with **no** drug grounding for intents without a tool (e.g. **`confirm_dose`**, **`log_vital`**, **`general_question`**).
10. **Append** the **assistant** turn and return reply text.

**Classification** uses the configured **`Intent`** enum ([`models/domain.py`](../apps/backend/src/medbuddy/models/domain.py)):
`add_medication`, `list_medications`, `remove_medication`, `explain_medication`, `interaction_check`, `confirm_dose`, `log_vital`, `request_summary`, `update_profile`, `update_locale`, `off_topic`, `general_question`.

---

## 3. Intents (chat) — behaviors and examples

Below, **“Examples”** are illustrative; the **LLM classifier** (or mocks) decides the label.

### 3.1 `list_medications`

| | |
|--|--|
| **Scenario** | User asks for their saved medication list. |
| **Examples** | 「我的藥清單」 · “What’s on my med list?” |
| **Outcome** | List from **`UserDataPort.list_medications`** + i18n intro or empty state. **No** LLM compose for the list body. |
| **Errors** | Unusual failures → generic agent error message (`agent.generic_error`). |

---

### 3.2 `add_medication`

| | |
|--|--|
| **Scenario** | User adds a drug with dose/schedule in natural language. |
| **Examples** | 「新增阿斯匹靈 100mg 每天飯後」 · `add aspirin 100mg after meals` |
| **Outcome** | Extract (**LLM** structured output or mock) → **`add_medication`**. Then **`DrugDataPort`** for the **new** drug only → **`compose_medication_added_reply`** (or i18n **`medication.added`** fallback). |
| **Incomplete** | No drug name → **`medication.add_incomplete`** (no full compose). |
| **Side effect** | When Supabase + reminders are configured: **dose_events** sync / LINE push path — [`reminders.md`](reminders.md). |

---

### 3.3 `remove_medication`

| | |
|--|--|
| **Scenario** | User stops tracking a med. |
| **Examples** | 「停藥普拿疼」 · `remove Tylenol from my list` |
| **Outcome** | Resolve row (**LLM** or mock) → **`delete_medication`** → i18n confirm or **`medication.remove_not_found`**. |
| **Side effect** | Reminder rebuild when configured (same as add). |

---

### 3.4 `explain_medication`

| | |
|--|--|
| **Scenario** | User wants to understand a drug or regimen. |
| **Examples** | 「解釋 Metformin 是做什麼的」 · “Why do I take this blood pressure pill?” |
| **Outcome** | **Personalization cache** hit (Supabase) → cached text + history append, skip fetch/LLM. Else **OpenFDA** (etc.) grounding + **`compose_reply`** with **companion** instructions (purpose, timing, cautions). **Upsert** personalization when composed. |
| **Prefetch** | Drug snippets prefetched in this turn path. |

---

### 3.5 `interaction_check`

| | |
|--|--|
| **Scenario** | Drug–drug or combination questions. |
| **Examples** | 「阿斯匹靈可以跟抗凝血藥一起吃嗎？」 · “Can I take aspirin with my blood thinner?” |
| **Outcome** | Same pipeline as explain with **interaction-focused** system add-on; optional personalization cache. |

---

### 3.6 `request_summary` (in chat)

| | |
|--|--|
| **Scenario** | User asks for a recap or doctor-ready summary **in the conversation**. |
| **Examples** | 「用三句話總結我們聊的」 · “Summarize what we discussed for my doctor.” |
| **Outcome** | **`GenerateHealthSummaryTool`** — structured generation + **reply text** (`as_text()`) stored as the assistant message. |
| **Contrast** | **`GET /v1/app/summary`** returns **JSON** (fields + `plain_text`) without going through the normal single-string chat reply path for the HTTP layer — same tool concept, different transport. |

---

### 3.7 `update_profile`

| | |
|--|--|
| **Scenario** | User updates profile fields **in chat** (name, age, emergency contact, health notes, gender). |
| **Examples** | Same one-line replies as after LINE welcome; “叫我老王”; “我對青霉素过敏”. |
| **Outcome** | **`parse_profile_patch_from_text`** (heuristics) → **`patch_user_profile`**. No LLM JSON extraction for stored PII. Empty parse → **`profile.update_unclear`**. |
| **Contrast** | Standalone **onboarding** uses **`POST /onboarding`** with typed JSON — not this intent. |

---

### 3.8 `update_locale`

| | |
|--|--|
| **Scenario** | User asks to switch **UI/reply language** (`en` or `zh-TW`). |
| **Examples** | “switch to English” · 「請用中文」 · “I prefer English replies from now on” (classifier + LLM extract if regex misses). |
| **Outcome** | **`parse_locale_request_from_text`** first; if missing but intent is **`update_locale`**, **`extract_locale_intent`**. **`patch_user_profile`** with **`locale`**. Already on target → **`locale.unchanged`**; invalid → **`locale.unclear`**. |
| **Note** | Phrases like “explain this in English” (content language only) are **excluded** from switching UI locale — see [`user_locale.py`](../apps/backend/src/medbuddy/user_locale.py). |

---

### 3.9 `off_topic`

| | |
|--|--|
| **Scenario** | Message is **not** medication-related (weather, sports, etc.). |
| **Examples** | “What’s the weather today?” · 「今天天氣怎麼樣」 |
| **Outcome** | Fixed **`agent.off_topic`** string in the user’s **effective locale**. **No** `compose_reply`. |

---

### 3.10 `confirm_dose` · `log_vital` · `general_question`

| | |
|--|--|
| **Scenario** | Dosing concern, vital sign in text, small talk, or general medication-adjacent chat **without** a dedicated tool. |
| **Examples** | 「藥物過量了怎麼辦」 · “What if I doubled my dose?” · 「血壓 130/85」 · 「早安」 |
| **Outcome** | **`compose_reply`** with persona + **de-identified** patient context + history; **no** automatic drug API prefetch for these intents (unlike explain / interaction / post-add ack). |
| **Prefetch** | Only **`explain_medication`**, **`interaction_check`**, and (after successful save) **`add_medication`** load drug grounding inside the main turn. |

---

## 4. Caching and persistence (when Supabase is configured)

**Scenario:** Explain/interaction personalization, drug reference cache, conversations, medications, **`users.locale`**, **`users.timezone`**, **`dose_events`**.

**Detail:** [`features.md` §6](features.md#6-persistence-and-caching-supabase) · **Reminders:** [`reminders.md`](reminders.md).

Without Supabase: in-memory user/conversation mocks; drug caches not wired.

---

## 5. Extensibility (intent hooks)

**Scenario:** Pilot intercepts a classified intent before fixed refusals, profile, tools, or fallback.

**Process:** [`try_intent_hooks`](../apps/backend/src/medbuddy/extensibility/intent_hooks.py) — if a hook returns a non-empty string, that reply is used. Order in **`MedicationAgent`**: **locale** short-circuit first → **hooks** → **`off_topic`** → **`update_profile`** → **tools** → **`compose_reply`** fallback.

---

## 6. LINE dose reminder pushes (prototype)

**Trigger:** Successful **`add_medication`** or **`remove_medication`** via medication intents (any channel using the same handler).

**User-visible outcome:** **LINE push** near **`scheduled_at`** (not in-app local notifications).

**Behavior:** **`dose_events`** rebuild; **arq** + Redis; copy under **`reminder.line_push`**. Free-text **`schedule`** echoed but **v1** does not expand to multiple times per day.

**Full reference:** [`reminders.md`](reminders.md).

---

## 7. Out of scope (not implemented as primary flows here)

- Clinical diagnosis or replacing clinician/pharmacist judgment.
- **Full TFDA HTTP** — stub returns empty; mocks may imitate TFDA.
- **LINE `postback`** handling** — no user-facing action yet.
- **Reference Expo** hold-to-talk → backend STT — see [`frontend-expo.md`](frontend-expo.md); **LINE audio** + Whisper is supported.
