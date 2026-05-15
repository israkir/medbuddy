# LLM inputs: what we send and how privacy is applied

This document describes **what data** each backend LLM call includes, **which redaction** applies today, and where it lives in code. It complements **[privacy.md](./privacy.md)** (operational goals and limits) with a **per-call** map.

**Audience:** Developers working on prompts, tools, or compliance reviews.

---

## Shared building blocks

### User message redaction (`redact_pii_text`)

Used on the **current turn** before many LLM calls. Pattern-based masking for emails, common phone shapes (including Taiwan `09…`), and long digit runs (see `apps/backend/src/medbuddy/privacy/redact.py`). **Not** full clinical de-identification: free-text names and many international formats may remain.

### Conversation history redaction (`redact_conversation_turns_for_llm`)

Maps each turn’s `content` through `redact_pii_text`. Used wherever tools pass **history** into `compose_reply` and for **`interpret_user_turn`** recent context.

**Exception:** `generate_health_summary` currently embeds **last 20 conversation turns without this redaction step** in the Gemini/OpenAI adapters (see below)—treat as higher sensitivity.

### Patient context for external LLMs (`patient_context_for_llm` → `build_patient_context_for_llm`)

**Assembler:** `apps/backend/src/medbuddy/application/patient_llm_context.py` runs `UserDataPort.sync_upcoming_dose_events`, queries **`list_upcoming_dose_events`** for a ~**7-day** window from **local calendar midnight** in **`patients.timezone`**, formats that slice with `apps/backend/src/medbuddy/reminders/upcoming_display.py`, then calls **`build_patient_context_for_llm`** (`apps/backend/src/medbuddy/llm/prompts/persona.py`) with the result as **`upcoming_doses_context`**.

Typical blocks in the string sent to the model:

| Block | Contents |
|--------|-----------|
| Profile signals | Preferred **form of address** (when the user saved one—so the model can greet them naturally), **age band** (not exact age), self-reported sex/gender label, flags that health notes or emergency contact exist (without raw note/contact text). |
| Profile gaps | Localized lines describing profile fields **not** yet stored (so the model may ask one item when relevant). |
| Medications | Lines from the user’s saved list: drug **name**, **dosage**, **schedule** (`format_patient_medication_context`). |
| Upcoming doses | When the sync/window yields rows: **local time** (and date if not today), **medication name**, **dosage**, **schedule** text; lines are **pending** `dose_events` only (`taken_at` / `missed_at` null), soonest first. Intro comes from `prompts.upcoming_doses_*` keys. |

**Not** included: raw free-text from `patient_health_conditions.notes` entries, raw emergency contact values, exact `age_years`.

**Call sites** using the assembler (so the model sees the schedule): `MedicationAgent` fallback `compose_reply`, **Explain medication**, **Interaction check**, **Side effects**, **Health summary**, and **post-add** flows in **`build_post_add_patient_reply`** (`compose_medication_added_reply` / `compose_medication_added_primary`, **`post_add_interaction_crosscheck`**) after reminder sync, with `sync_dose_events_first=False` to avoid double sync. Post-add assembly uses `include_health_notes=True`. The `include_health_notes=True` flag toggles inclusion of the `recent_health_notes` buffer — a formatted block built from recent `patient_health_conditions` rows (not a removed stored column); it is omitted from the standard context block but included deliberately on the safety-critical call sites listed above. **`ListUpcomingDosesTool`** does not use this blob—it returns deterministic i18n only.

### Patient context for **display** only (`build_patient_context_for_chat_display`)

Full profile text for **user-facing** strings (e.g. listing meds with profile lines). **Do not** pass this blob to third-party LLM APIs; use **`patient_context_for_llm`** (or the same composition rules) for model prompts and explain/interaction cache fingerprints so **upcoming `dose_events`** stay aligned with reminders.

### Locale scaffolding

Prompts are assembled with localized headers and instructions from `apps/backend/src/medbuddy/locales/*.json` (e.g. `prompts.system_persona`, `llm.patient_background`, `llm.reference`, `llm.reply_instruction`, task-specific `llm.medication_companion_*`).

### Deterministic tool copy vs agent-generated copy

Some locale keys (for example `medication.confirm_dose_*`) are intentionally used as **deterministic system responses** for transactional tool outcomes and error states, not as "conversation quality" prose.

`ConfirmDoseTool` currently returns fixed `t("...")` strings directly from code after writing adherence state. This design is intentional:

- **Determinism for critical actions:** marking a dose as taken (or reporting no matching dose) uses stable wording and avoids model drift.
- **Compliance/safety tone control:** medication-adherence confirmations keep predictable, reviewed phrasing.
- **Localization parity:** the same key set in `en` and `zh-TW` keeps behavior and wording aligned across locales.
- **Test stability:** integration tests can assert exact tool outcomes.
- **Latency/cost:** no additional LLM call is needed for simple transactional acknowledgments.

You can make this path fully agent-driven by replacing deterministic tool replies with `compose_reply`, but trade-offs are expected:

- less predictable phrasing for safety-critical confirmations,
- harder regression testing (exact-string assertions become brittle),
- higher token/call cost and added latency,
- more prompt-engineering effort to keep edge-case UX consistent.

Current architecture is intentionally **hybrid**:

- keep deterministic i18n keys for CRUD/adherence state transitions,
- use LLM-generated copy for explanatory, contextual, and empathetic replies.

---

## Per `LLMPort` method (what goes to the model)

Implementation reference: `apps/backend/src/medbuddy/protocols/llm.py` (`LLMPort`). Concrete adapters: `apps/backend/src/medbuddy/integrations/llm/gemini_llm.py`, `apps/backend/src/medbuddy/integrations/llm/openai_llm.py` (same contract).

### `interpret_user_turn`

| Input | Redaction / notes |
|--------|-------------------|
| Current user message | **Redacted** (`safe_text` in `MedicationAgent`). |
| `recent_context` | Last few turns formatted as `role: content` after **redaction** (`_recent_context_for_intent` → `redact_conversation_turns_for_llm`). |
| Prompt + schema | **`IntentClassification`** → **`TurnInterpretation`**. **`intent`** gates **`emergency`** / **`off_topic`**; remaining fields are for logs/metrics. Tools and adherence come only from **`complete_chat_with_tools`**. |

### `complete_chat_with_tools`

Multi-step medication orchestration: OpenAI **chat.completions** with **`tools`** / Gemini structured **`AgentOrchestratorStep`** (see `integrations/llm/*.py`). The **first** provider request includes **system**, then **prior** **`user` / `assistant`** messages (recent thread from `conversation_turns`, **redacted**, capped by **`MEDBUDDY_AGENT_ORCHESTRATOR_HISTORY_TURNS`**, default 12), then the **current** **redacted** user line (`safe_text`). Later rounds append **assistant** + **tool** messages from the same turn.

| Input | Redaction / notes |
|--------|-------------------|
| Prior turns | **Redacted** (`orchestrator_prior_messages` → `redact_conversation_turns_for_llm`). |
| Current user line | **Redacted** (`safe_text`). |
| System content | Catalog of medication **ids/names** for tool arguments; de-identified patient block; locale-aware instructions (`agent_system_prompt.py`). |
| Tool outputs | Server-executed tool replies (often localized strings or JSON summaries); may echo user-facing medication names and schedule text—**not** an extra redaction pass today. |
| Later rounds | Model may emit natural-language **assistant** content between tool calls; same thread is sent to the provider until a final reply or step limit. |

### `compose_reply`

Used inside tools (**Explain medication**, **Interaction check** fallback, **`compose_reply`-style paths**), not as the top-level assistant dispatcher.

| Input | Redaction / notes |
|--------|-------------------|
| `system_persona` | `get_system_persona` + optional task appendix (e.g. `llm.medication_companion_explain` or `llm.medication_companion_interactions`). |
| `patient_context` | `patient_context_for_llm` (includes upcoming `dose_events` block). |
| `drug_grounding` | Registry snippets (TFDA / OpenFDA) or placeholder `llm.no_drug_data`. Not end-user PII. |
| `history` | **Redacted** turns. **Interaction fallback** passes `history=[]` in the tool. |
| `user_message` | **Redacted** (`safe_text`). |
| Closing | `llm.reply_instruction`. |

**Explain medication:** Drug registry fetch uses the **original** `user_text` string for the HTTP lookup to TFDA/OpenFDA; the **LLM** still sees **redacted** `safe_text` as the user line.

### `compose_medication_added_reply`

Used when the patient’s list has **only the newly saved drug** (first medication on file). Assembled by **`build_post_add_patient_reply`**.

| Input | Redaction / notes |
|--------|-------------------|
| `patient_context` | `patient_context_for_llm` after the new med is saved and reminders are synced (`sync_dose_events_first=False`; often `include_health_notes=True`). |
| `drug_grounding` | TFDA/OpenFDA snippets for the **saved drug name**. |
| `saved` | Authoritative `name`, `dosage`, `schedule`, optional `instructions` in the prompt. |
| `user_message` | **Redacted** (`safe_text`). |

### `compose_medication_added_primary`

Used when the reloaded list has **≥ 2** medications (patient already had other drugs). Same inputs as **`compose_medication_added_reply`**; adapter uses task key `medication_added_primary_before_crosscheck` (shorter acknowledgment before the cross-check paragraph).

### `post_add_interaction_crosscheck`

**Not** the same prompt as chat **`check_interactions_structured`** — uses **`llm.post_add_interaction_crosscheck_task`** (continuation framing: do not re-greet; focus new drug vs rest of list). Called from **`build_post_add_patient_reply`** only when list length **≥ 2**; skipped on first-ever medication.

| Input | Redaction / notes |
|--------|-------------------|
| `user_message` | Localized synthetic line from **`medication.post_add_interaction_user_query`** + saved drug **name** (not the user’s raw add utterance). |
| `patient_context` | Same block as post-add compose (`include_health_notes=True`). |
| `medications` | Full updated list (name, dosage, schedule lines). |
| `drug_grounding` | TFDA/OpenFDA snippets for the **newly saved** drug (same blob as compose step). |
| History | **Not** included. |

### `check_interactions_structured`

Chat **`interaction_check`** tool only (user-initiated interaction questions).

| Input | Redaction / notes |
|--------|-------------------|
| `user_message` | **Redacted** user chat line (`safe_text`). |
| `patient_context` | `patient_context_for_llm` (includes upcoming `dose_events` block). |
| `medications` | Explicit list lines (name, dosage, schedule) in the adapter prompt. |
| `drug_grounding` | OpenFDA (and optional warnings excerpt) from the **user’s chat query**, or placeholder. |
| History | **Not** included in the structured Gemini/OpenAI prompt (unlike `compose_reply`). |

### `check_drug_condition_interactions`

Called from **`persist_medication_add_from_draft`** after **`build_post_add_patient_reply`** when active **`patient_health_conditions`** exist. Returns patient-safe warning **lines** (not `InteractionResult`); appended to the reply string in code.

| Input | Redaction / notes |
|--------|-------------------|
| `drug_name` | Saved medication **name** (not user chat). |
| `conditions` | Active condition rows: category, name, optional severity — **not** full clinical notes text from DB. |
| Prompt | Structured JSON extraction; only moderate/high concerns become visible lines. |

### `extract_medication_draft`

| Input | Redaction / notes |
|--------|-------------------|
| User text | **Redacted** (`safe_text` in `AddMedicationTool`). Structured extraction → `MedicationDraft`. |

### `resolve_medication_removal_id`

| Input | Redaction / notes |
|--------|-------------------|
| User text | **Redacted** (`safe_text`). |
| Medications | JSON catalog of `id` + `name` only. |

### `resolve_medication_update`

| Input | Redaction / notes |
|--------|-------------------|
| User text | **Redacted** (`safe_text`). |
| Medications | JSON catalog of `id`, `name`, dosage, schedule, instructions for **`UpdateMedicationTool`**. |

### `extract_health_conditions`

| Input | Redaction / notes |
|--------|-------------------|
| User text | **Raw** `user_text` when **`manage_health_conditions`** runs extraction (allergies/diagnoses — not **`update_profile`**). Higher PII exposure than redacted chat lines. |

### `extract_profile_patch`

| Input | Redaction / notes |
|--------|-------------------|
| User message | **Raw** `user_text` when the orchestrator runs **`update_profile`** → **`extract_profile_patch`**. Intentional so the model can extract profile updates (name, contact, locale, timezone); higher PII exposure than redacted chat lines. |

### `generate_health_summary`

| Input | Redaction / notes |
|--------|-------------------|
| `patient_context` | `patient_context_for_llm` (includes upcoming `dose_events` block). |
| Medications | Name, dosage, schedule, and **per-med `instructions`** (user notes) in the adapter prompt. |
| Logged health issues | Chronological lines built from **`health_issue_events`** (cap **`MEDBUDDY_HEALTH_ISSUE_SUMMARY_EVENTS_LIMIT`**); classifier intents plus structured vital rows. Same PHI considerations as chat. |
| Recent conversation | **Last 20 turns** embedded as `[role] content` in Gemini/OpenAI adapters. **Not** run through `redact_conversation_turns_for_llm` today—treat as **more sensitive** than `compose_reply` history. |
| Prompt | Instructs the model not to output PII in the structured summary; does not remove PII from the **input** conversation. |

### `simplify_drug_text_to_patient_zh`

| Input | Redaction / notes |
|--------|-------------------|
| `raw_label` | Label or registry text to simplify for the patient (not a user chat message). Locale-specific intro string. |

---

## Drug registry (“grounding”) data

Snippets from **TFDA** and/or **OpenFDA** are factual drug label excerpts, not patient identifiers. They are combined with patient context and user questions in explain / interaction / add-medication flows as described above.

---

## Caching (`drug_personalization_cache`)

Personalized replies for explain/interaction intents are keyed by a fingerprint that includes **hashed** `patient_context` from **`patient_context_for_llm`** (med list + **time-ordered upcoming doses** when rows exist) and **redacted** query text where applicable (`apps/backend/src/medbuddy/integrations/caching_drugs.py`). Cached reply text may still be sensitive; treat storage under your retention policy.

---

## Quick file map

| Concern | Location |
|--------|----------|
| Redaction helpers | `apps/backend/src/medbuddy/privacy/redact.py` |
| Patient context builders | `apps/backend/src/medbuddy/llm/prompts/persona.py`, `apps/backend/src/medbuddy/application/patient_llm_context.py` |
| Post-add reply assembly | `apps/backend/src/medbuddy/application/post_add_medication_reply.py` |
| Turn orchestration | `apps/backend/src/medbuddy/agents/medication_agent.py`, `apps/backend/src/medbuddy/agents/orchestrator.py` (`orchestrator_prior_messages`) |
| LLM adapters (prompt assembly) | `apps/backend/src/medbuddy/integrations/llm/gemini_llm.py`, `apps/backend/src/medbuddy/integrations/llm/openai_llm.py` |
| Privacy overview | [docs/privacy.md](./privacy.md) |

---

## Changelog discipline

When you change what is sent to an LLM (new fields, redaction, or prompts), update this doc and **[CHANGELOG.md](../CHANGELOG.md)** as appropriate.
