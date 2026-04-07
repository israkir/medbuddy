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
| **Patient “context” block** | Yes, **mostly de-identified** | Built with `build_patient_context_for_llm` in `apps/backend/src/medbuddy/prompts/persona.py`: **preferred form of address** when set, **age band** (not exact age), gender label, signals that notes/contact exist (without raw text), optional “gaps” lines, medication list (names, dose, schedule). |
| **Drug reference / label snippets** | Yes | From registries (e.g. OpenFDA), not end-user PII. |
| **Intent classification** | Yes, on **redacted** user text | `MedicationAgent` → `LLMPort.classify_intent` (see `apps/backend/src/medbuddy/application/assistant_turn.py` for the shared entrypoint). |
| **Medication add / remove extraction** | Yes, on **redacted** text | `agents/tools/medication_crud.py` → `LLMPort.extract_medication_draft` / `resolve_medication_removal_id`. |
| **Profile fields from chat** | Yes, for extraction (**often raw user message**) | `application/profile_intents.py` → `LLMPort.extract_profile_patch` (structured output); then **`patch_user_profile`**. |
| **Health summary** | Yes | Structured prompt includes **unredacted** recent conversation turns in adapters today—see **[llm-context.md](./llm-context.md)**. |

## What is not sent to an LLM (by design)

- **Raw** `health_notes`, `emergency_contact`, or **exact** `age_years` inside the standard **`build_patient_context_for_llm`** block (those appear only as coarse signals or omitted).

**Exceptions:** Profile/locale/dose-note extractors and health-summary prompts may include **raw or unredacted** user or conversation text where the feature requires it—see **[llm-context.md](./llm-context.md)**.

## User-facing vs model-facing context

- **`build_patient_context_for_llm`**: use for **all** prompts and cache fingerprints that should stay de-identified (`assistant_turn`, `compose_medication_added_reply` patient block, etc.).
- **`build_patient_context_for_chat_display`**: use when the **same thread** should show the user their **full** stored profile snippet (e.g. listing medications together with profile lines). This string is **not** intended for external LLM APIs.

Conversation rows in the database are still stored from the **original** user message (for continuity with the product). Most assistant/tool paths pass **redacted** text into the LLM; **profile update**, **locale**, **dose confirmation note**, and **health summary** paths may use **raw** or **unredacted** strings as documented in **[llm-context.md](./llm-context.md)**.

## Redaction behavior (summary)

Implemented in `privacy/redact.py`:

- Email-like substrings replaced with a fixed placeholder (e.g. `[…]`).
- Taiwan-oriented mobile patterns (including cases where `09…` follows CJK text without a word boundary).
- Long runs of digits (e.g. 10+), which often indicate account or ID numbers.

**Limits:** Names, addresses, free-form clinical details in the user’s wording, and many international phone formats may **not** be removed. Treat LLM calls as receiving **possibly sensitive free text** unless you add stricter policies (on-prem models, DLP, or blocking certain intents without human review).

## Prompt instructions

Locale strings under `apps/backend/src/medbuddy/locales/` (e.g. `prompts.system_persona`, `gemini.reply_instruction`) instruct the model how to use **only** the preferred address form provided in the patient background (when present), **not** to invent other names or echo phone numbers or raw health/contact details, and to treat **`[…]`** as masked content.

## Code map

| Area | Location |
|------|-----------|
| Per-call LLM inputs and privacy exceptions | [docs/llm-context.md](./llm-context.md) |
| Redaction | `apps/backend/src/medbuddy/privacy/redact.py` |
| Orchestration (when redaction applies) | `apps/backend/src/medbuddy/application/assistant_turn.py` → `agents/medication_agent.py`, `profile_intents.py`, `locale_intents.py` |
| De-identified vs display context | `apps/backend/src/medbuddy/prompts/persona.py` |
| Tests | `apps/backend/tests/test_privacy_redact.py`, `test_persona_llm_safe.py` |

## Operations and compliance

- **Vendor agreements**: Ensure your LLM provider’s **terms, retention, and training** policies match your regulatory needs (e.g. HIPAA, GDPR, PDPA). Code-level masking does not replace contracts or Data Processing Agreements.
- **Logging**: Do not log raw user messages, tokens, or full prompts in production without a reviewed retention policy.
- **Caching**: Personalized reply caches (`drug_personalization_cache`) fingerprint using **de-identified** patient context and **redacted** query text where applicable; still treat stored reply text as sensitive if it could reflect user-specific questions.

## Future hardening (optional)

- Named-entity masking or dedicated **de-identification** service before LLM calls.
- Stricter separation: **no** user free text to cloud LLM for certain intents; template-only or on-device models.
- Field-level encryption at rest for `patients` and conversation tables, plus access auditing.
