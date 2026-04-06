# MedBuddy — covered use cases

This document summarizes behaviors the codebase implements today: what the user can do, an example, and how the backend handles it. All assistant replies share the core pipeline **`run_assistant_text_turn`** unless noted.

---

## Channels

### LINE: new follower

**Example:** User adds the official account and triggers a `follow` event.

**Process:** The webhook ensures a user record exists (`get_or_create_user`), then sends a fixed welcome string from i18n (not the full assistant turn).

---

### LINE: text message

**Example:** 「我的藥清單」 / `list my medications`; 「這顆要跟食物一起吃嗎？」 / `Do I need to take this with food?`; 「幫我記錄今天頭有點暈」 / `I felt a bit dizzy today—note that down`

**Process:** Verified webhook → event parsed → user id extracted → **`run_assistant_text_turn(user_key=line_user_id, user_text=...)`** → reply as LINE text (or batch; see audio).

---

### LINE: voice message

**Example:** User sends a voice clip asking a medication question.

**Process:** Audio bytes are fetched from LINE → **STT** (e.g. Whisper service or mock) → transcript fed into **`run_assistant_text_turn`**. If the client path prefers audio back, **TTS** builds a short-lived public URL; LINE gets a **batch** of audio + text, then storage deletes the temp object after TTL.

---

### Standalone app: one assistant message (HTTP)

**Example:** `POST /v1/app/messages` with JSON `{"text":"⋯"}` and headers `X-App-User-Id` (and optional `Authorization: Bearer` in production).

**Process:** Auth resolves `app_user_id` → same **`run_assistant_text_turn(user_key=app_user_id, user_text=...)`** as LINE text → JSON `{"reply":"⋯"}`.

---

### Expo companion: “Medication helper” UI

**Example:** User opens the in-app chat screen and sends “What is metformin for?” or 「我的藥哪些不能同時吃？」 / “Which of my meds shouldn’t I combine?” (or taps a suggested prompt).

**Process (when not in mock mode):** The app calls **`POST /v1/app/messages`**. When **`EXPO_PUBLIC_USE_MOCK_DATA=true`**, no API call; local i18n text is returned. The screen can **read aloud** replies with on-device TTS.

---

## Assistant intents (same core for LINE + mobile)

Classification is done by the configured **LLM** (e.g. Gemini) or **mock rules** in tests. Numeric order below is logical, not code order.

### List saved medications

**Example:** 「我的藥清單」 / “What’s on my med list?”

**Process:** Intent **`list_medications`** → **no LLM compose**: response is built from **`UserDataPort.list_medications`** (in-memory mock or Supabase) plus i18n intro / empty message.

---

### Add a medication

**Example:** 「新增阿斯匹靈 100mg 每天飯後」 / `add aspirin 100mg after meals`

**Process (high level):**

1. Intent **`add_medication`** → **extract** name/dose/schedule (and optional notes) via LLM JSON or mock heuristics. Incomplete extraction (no drug name) → i18n **`medication.add_incomplete`**; no full assistant compose.
2. **Persist** via **`UserDataPort.add_medication`**.
3. Reload the list → build **patient medication context** (includes the new row and any existing meds).
4. **Reference data:** **`DrugDataPort`** fetches snippets for the **new drug name** (HTTP **OpenFDA**; **`HttpDrugData`** TFDA returns nothing until a real integration exists; **mocks** may still simulate TFDA), same family of grounding used for explain—**not** the per-user **`drug_personalization_cache`** (that cache remains for **`explain_medication`** / **`interaction_check`** only).
5. **LLM `compose_medication_added_reply`** (Gemini in production, deterministic **`mocks.llm.medication_added`** in mock mode): short confirmation that restates **schedule in plain language**, adds **one or two sentences** of drug context personalized to the list + references only, and reminds that this is not individualized medical advice. If compose fails → **i18n `medication.added`** template fallback.

---

### Remove a medication

**Example:** 「停藥普拿疼」 / `remove Tylenol from my list`

**Process:** Intent **`remove_medication`** → **resolve** which row (LLM JSON or mock match on name) → **delete** via **`delete_medication`** → i18n confirmation or “not found”.

---

### Explain a medication (comprehension)

**Example:** 「解釋 Metformin 是做什麼的」 / “Why do I take this blood pressure pill?”

**Process (high level):**

1. Intent **`explain_medication`** (or **`interaction_check`** for interactions — similar path).
2. **Personalization cache (Supabase only):** If **`drug_personalization_cache`** has a fresh row for `(user, fingerprint)`, fingerprint includes a **hash of the current medication list text** → return cached reply and append conversation turns; **skip** remote drug fetch and LLM.
3. Else **reference data:** **`DrugDataPort`** (HTTP OpenFDA label search; no TFDA row from HTTP until integrated, or mocks). With Supabase, **`CachingDrugData`** reads/writes **`drug_reference_cache`** (TTL configurable).
4. **Conversation history** loaded; **user message** stored.
5. Optional **intent hooks** and **medication intents** short-circuit if they return text.
6. Otherwise **LLM `compose_reply`** with system persona, **patient medication context**, **drug grounding** string, and history. Extra system text nudges **purpose, timing rationale, cautions**.
7. Assistant turn stored; if the reply came from **compose** (not list/add/remove/hook), **personalization row upserted** for next time.

---

### Drug–drug / combination caution

**Example:** 「阿斯匹靈可以跟抗凝血藥一起吃嗎？」 / “Can I take aspirin with my blood thinner?”

**Process:** Intent **`interaction_check`** → same structure as explain: personalization cache → grounded references → LLM with **interaction-focused** system add-on → optional save to personalization cache.

---

### Confirm dose / log vital / ask for summary / general chat

**Examples:** 「藥物過量了怎麼辦」 / `What if I accidentally took a double dose?`; 「血壓 130/85」; 「用三句話總結我們聊的」 / `Summarize our chat in three bullets`; 「早安，今天天氣不錯」 / small talk.

**Process:** Classified into **`confirm_dose`**, **`log_vital`**, **`request_summary`**, or **`general_question`**. **Drug API snippets** are prefetched inside the main turn for **`explain_medication`**, **`interaction_check`**, and (after a successful save) **`add_medication`**; other intents do not load that grounding in **`run_assistant_text_turn`**. Replies come from **hooks** (if registered), **medication handlers** (list/add/remove), or **generic `compose_reply`** without the explain/interaction “companion” add-on unless the intent matched those.

---

## Caching & data (when Supabase is configured)

| Layer | Table / behavior | Role |
|--------|------------------|------|
| User + meds | `users`, `medications` | Source of truth for list/add/remove and patient context string |
| Turns | `conversation_turns` | Recent dialogue for the LLM |
| Reference | `drug_reference_cache` | Shared label snippets per `source` + normalized `query_key` |
| Personalization | `drug_personalization_cache` | Per-user LLM answer for explain/interaction fingerprints; **`llm_meta.source`** is **`openfda`** / **`tfda`** when label snippets were used, else the **LLM model id** (model-only grounding) |

Without Supabase, users/conversations stay in memory and **drug_caches** / **CachingDrugData** are not wired.

---

## Extensibility

**Intent hooks** can return a string before medication handlers and **`compose_reply`** — useful for pilot features (e.g. doctor summary) without forking the LINE app.

---

## Out of scope (not primary flows here)

- Diagnosis or replacing clinician/pharmacist judgment (prompts explicitly discourage that).
- Full TFDA API integration (**`HttpDrugData.fetch_tfda_snippet`** currently returns **`None`** so **`source=tfda`** is not stored for placeholder text; mocks can still imitate TFDA).
- Companion **center mic** hold-to-talk → **automatic** STT to this backend (keyboard dictation or LINE voice are the intended voice paths today).
