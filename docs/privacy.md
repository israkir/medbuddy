# MedBuddy — privacy and LLM data handling

This document describes how MedBuddy limits **personally identifiable information (PII)** and sensitive profile data sent to **third-party large language model (LLM)** APIs (e.g. Gemini). It is aimed at developers and operators; it is **not** a legal privacy notice for end users.

For a **call-by-call** list of inputs (including exceptions), see **[llm-context.md](./llm-context.md)**.

## Goals

- Keep **stored** profile fields that are highly sensitive (`health_notes`, `emergency_contact` text, exact `age_years`) out of the standard **patient context** block, except where a feature intentionally needs user wording (see **[llm-context.md](./llm-context.md)**). The user’s **preferred form of address** (when saved) is included in that block so the assistant can greet them naturally.
- **Mask** common direct identifiers in **user messages and chat history** before those strings are passed to an LLM (emails, typical Taiwan mobile patterns, long digit runs).
- Profile updates from chat use **structured LLM extraction** (`extract_profile_patch`) when intent is **`update_profile`**; operators should review provider terms for storing PII.
- Keep **user-facing** replies (e.g. medication list) able to show the user **their own** stored text where the product intentionally echoes it back.

## What still goes to an LLM today

| Data | Sent to LLM? | Notes |
|------|----------------|-------|
| **User message** (current turn) | Yes, **after redaction** | See `redact_pii_text` in `apps/backend/src/medbuddy/privacy/redact.py`. Redaction is pattern-based, not full PHI scrubbing. |
| **Recent conversation turns** | Yes, **after redaction** | `redact_conversation_turns_for_llm` in the same module. |
| **Patient “context” block** | Yes, **redacted/narrowed** | Built via `patient_context_for_llm` → `build_patient_context_for_llm` in `apps/backend/src/medbuddy/application/patient_llm_context.py` + `llm/prompts/persona.py`: **preferred form of address** when set, **age band** (not exact age), gender label, signals that notes/contact exist (without raw text), optional “gaps” lines, medication list (names, dose, schedule), and when present a **time-ordered upcoming dose** section from materialized **`dose_events`** (local times, drug names, dose/schedule text — same facts as LINE reminder targets). |
| **Drug reference / label snippets** | Yes | From registries (e.g. OpenFDA), not end-user PII. |
| **Turn interpretation** | Yes, on **redacted** user text | `LLMPort.interpret_user_turn` → **`Intent`** (+ optional fields for logs). Used for **`emergency`** / **`off_topic`** gates only. |
| **Tool orchestration rounds** | Yes | The **first** `complete_chat_with_tools` request per user line sends **system prompt**, **patient catalog/context**, **redacted prior** `user` / `assistant` messages from storage (tail capped by **`MEDBUDDY_AGENT_ORCHESTRATOR_HISTORY_TURNS`**, `0` = none), then the **current redacted** user line. **Later rounds** in the same turn append **assistant** tool-call lines and **`tool`** result messages. Tool **results** are JSON/text echoed back to the model in those follow-on rounds. |
| **Medication add / remove extraction** | Yes, on **redacted** text | `agents/tools/medication_crud.py` → `LLMPort.extract_medication_draft` / `resolve_medication_removal_id`. |
| **Profile fields from chat** | Yes, for extraction (**often raw user message**) | **`update_profile`** tool in **`run_tool_agent_loop`** → `LLMPort.extract_profile_patch` → **`patch_user_profile`** (`application/profile_intents.py`). |
| **Health summary** | Yes | Structured prompt includes **unredacted** recent conversation turns **and** a formatted block from persisted **`health_issue_events`** (classifier routing intents and structured vital rows), capped by **`MEDBUDDY_HEALTH_ISSUE_SUMMARY_EVENTS_LIMIT`**—see **[llm-context.md](./llm-context.md)** and **Persistence: `health_issue_events`** below. |

## Persistence: `health_issue_events`

The backend stores selected user turns in **`public.health_issue_events`** (Postgres): **`routing_intent`** mirrors the **`Intent`** classifier string; **`user_message`** holds the user line (used for doctor-summary synthesis); **`locale`** the effective UI locale; structured vital tool saves use **`routing_intent = log_vital`** with **`payload`**, **`kind`**, and **`display_summary`**. This is queryable health timeline data separate from full **`conversation_turns`**. Operators can narrow what gets logged via **`MEDBUDDY_HEALTH_ISSUE_LOG_INTENTS`** (comma-separated allowlist) or the sentinel **`all_non_off_topic`**—see `application/health_issue_event_log.py`.

## What is not sent to an LLM (by design)

- **Raw** `health_notes`, `emergency_contact`, or **exact** `age_years` inside the standard **`build_patient_context_for_llm`** block (those appear only as coarse signals or omitted).

**Exceptions:** Profile extractors and health-summary prompts may include **raw or unredacted** user or conversation text where the feature requires it—see **[llm-context.md](./llm-context.md)**. Adherence and dose notes are set only via the **`confirm_dose`** tool (**`interpret_user_turn`** does not apply adherence).

## User-facing vs model-facing context

- **`patient_context_for_llm`** (preferred) / **`build_patient_context_for_llm`** with optional **`upcoming_doses_context`**: use for **all** prompts and cache fingerprints that should stay de-identified (`assistant_turn`, explain/interaction/side-effect/summary tools, `compose_medication_added_reply` patient block, etc.).
- **`build_patient_context_for_chat_display`**: use when the **same thread** should show the user their **full** stored profile snippet (e.g. listing medications together with profile lines). This string is **not** intended for external LLM APIs.

Conversation rows in the database are still stored from the **original** user message (for continuity with the product). Most assistant/tool paths pass **redacted** text into the LLM; **profile update**, **locale**, and **health summary** paths may use **raw** or **unredacted** strings as documented in **[llm-context.md](./llm-context.md)**.

## Redaction vs. de-identification

**Redaction (current):** Pattern-based masking applied at the LLM boundary on every call — emails, Taiwan-style mobile numbers, and long digit runs are replaced with `[…]` before text reaches any LLM. This runs in `privacy/redact.py` and is unit-tested on every PR. Redaction is fast and deterministic but is not a substitute for clinical de-identification: names, addresses, free-form clinical details, and many international phone formats may pass through.

**De-identification (future hardening):** NER-based clinical scrubbing — a dedicated service or on-prem model that recognizes and removes named entities (persons, locations, medical identifiers) before LLM calls. Planned as a Growth-phase privacy investment; see the Future hardening section below. In code-adjacent prose and implementation notes, use *redaction* for the current mechanism and reserve *de-identification* for the future NER-based hardening.

## Redaction behavior (summary)

Implemented in `privacy/redact.py`:

- Email-like substrings replaced with a fixed placeholder (e.g. `[…]`).
- Taiwan-oriented mobile patterns (including cases where `09…` follows CJK text without a word boundary).
- Long runs of digits (e.g. 10+), which often indicate account or ID numbers.

Examples (original → redacted):

- `請聯絡我 john.doe+med@example.com` → `請聯絡我 […]`
- `我的電話是0912-345-678，晚上可接` → `我的電話是[…]，晚上可接`
- `我的電話是+886 912345678` → `我的電話是[…]`
- `客服備註手機09xxxxxxxx也要遮罩（CJK後面直接接09）` → `客服備註手機[…]也要遮罩（CJK後面直接接09）`
- `保單號碼 123456789012` → `保單號碼 […]`
- `請記住我住台北市大安區，最近胸悶兩天` → *(unchanged by current regex rules)*

**Limits:** Names, addresses, free-form clinical details in the user’s wording, and many international phone formats may **not** be removed. Treat LLM calls as receiving **possibly sensitive free text** unless you add stricter policies (on-prem models, DLP, or blocking certain intents without human review).

## Prompt instructions

Locale strings under `apps/backend/src/medbuddy/locales/` (e.g. `prompts.system_persona`, `gemini.reply_instruction`) instruct the model how to use **only** the preferred address form provided in the patient background (when present), **not** to invent other names or echo phone numbers or raw health/contact details, and to treat **`[…]`** as masked content.

## Code map

| Area | Location |
|------|-----------|
| Per-call LLM inputs and privacy exceptions | [docs/llm-context.md](./llm-context.md) |
| Redaction | `apps/backend/src/medbuddy/privacy/redact.py` |
| Orchestration (when redaction applies) | `apps/backend/src/medbuddy/application/assistant_turn.py` → `agents/medication_agent.py`, `profile_intents.py` |
| De-identified vs display context | `apps/backend/src/medbuddy/llm/prompts/persona.py` |
| Tests | `apps/backend/tests/test_privacy_redact.py`, `test_persona_llm_safe.py` |

## Operations and compliance

- **Vendor agreements**: Ensure your LLM provider’s **terms, retention, and training** policies match your regulatory needs (e.g. HIPAA, GDPR, PDPA). Code-level masking does not replace contracts or Data Processing Agreements.
- **Logging**: Do not log raw user messages, tokens, or full prompts in production without a reviewed retention policy.
- **Caching**: Personalized reply caches (`drug_personalization_cache`) fingerprint using **de-identified** patient context and **redacted** query text where applicable; still treat stored reply text as sensitive if it could reflect user-specific questions.

## Future hardening (optional)

- Named-entity masking or dedicated **de-identification** service before LLM calls.
- Stricter separation: **no** user free text to cloud LLM for certain intents; template-only or on-device models.
- Field-level encryption at rest for `patients` and conversation tables, plus access auditing.
