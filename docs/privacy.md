# MedBuddy — privacy and LLM data handling

This document describes how MedBuddy limits **personally identifiable information (PII)** and sensitive profile data sent to **third-party large language model (LLM)** APIs (e.g. Gemini). It is aimed at developers and operators; it is **not** a legal privacy notice for end users.

## Goals

- Avoid sending **stored** profile fields (name, raw health notes, emergency contact text, exact age) to LLMs in prompts.
- **Mask** common direct identifiers in **user messages and chat history** before those strings are passed to an LLM (emails, typical Taiwan mobile patterns, long digit runs).
- Profile updates from chat use **structured LLM extraction** (`extract_profile_patch`) when intent is **`update_profile`**; operators should review provider terms for storing PII.
- Keep **user-facing** replies (e.g. medication list) able to show the user **their own** stored text where the product intentionally echoes it back.

## What still goes to an LLM today

| Data | Sent to LLM? | Notes |
|------|----------------|-------|
| **User message** (current turn) | Yes, **after redaction** | See `redact_pii_text` in `apps/backend/src/medbuddy/privacy/redact.py`. Redaction is pattern-based, not full PHI scrubbing. |
| **Recent conversation turns** | Yes, **after redaction** | `redact_conversation_turns_for_llm` in the same module. |
| **Patient “context” block** | Yes, **de-identified** | Built with `build_patient_context_for_llm` in `apps/backend/src/medbuddy/prompts/persona.py`: coarse signals (e.g. “preferred name on file” without the name), **age band** (not exact age), medication list lines (drug names, dose, schedule). |
| **Drug reference / label snippets** | Yes | From registries (e.g. OpenFDA), not end-user PII. |
| **Intent classification** | Yes, on **redacted** user text | `run_assistant_text_turn` in `apps/backend/src/medbuddy/application/assistant_turn.py`. |
| **Medication add / remove extraction** | Yes, on **redacted** text | `agents/tools/medication_crud.py` → `LLMPort.extract_medication_draft` / `resolve_medication_removal_id`. |
| **Profile fields from chat** | Yes, for extraction | `application/profile_intents.py` → `LLMPort.extract_profile_patch` (structured output); then **`patch_user_profile`**. |

## What is not sent to an LLM (by design)

- **Raw** `preferred_name`, `health_notes`, `emergency_contact`, or **exact** `age_years` in the patient context block.

## User-facing vs model-facing context

- **`build_patient_context_for_llm`**: use for **all** prompts and cache fingerprints that should stay de-identified (`assistant_turn`, `compose_medication_added_reply` patient block, etc.).
- **`build_patient_context_for_chat_display`**: use when the **same thread** should show the user their **full** stored profile snippet (e.g. listing medications together with profile lines). This string is **not** intended for external LLM APIs.

Conversation rows in the database are still stored from the **original** user message (for continuity with the product); only the **copy** passed into the LLM adapter is redacted.

## Redaction behavior (summary)

Implemented in `privacy/redact.py`:

- Email-like substrings replaced with a fixed placeholder (e.g. `[…]`).
- Taiwan-oriented mobile patterns (including cases where `09…` follows CJK text without a word boundary).
- Long runs of digits (e.g. 10+), which often indicate account or ID numbers.

**Limits:** Names, addresses, free-form clinical details in the user’s wording, and many international phone formats may **not** be removed. Treat LLM calls as receiving **possibly sensitive free text** unless you add stricter policies (on-prem models, DLP, or blocking certain intents without human review).

## Prompt instructions

Locale strings under `apps/backend/src/medbuddy/locales/` (e.g. `prompts.system_persona`, `gemini.reply_instruction`) instruct the model **not** to invent or echo specific names, phone numbers, or raw health/contact details when only “signals” are present, and to treat **`[…]`** as masked content.

## Code map

| Area | Location |
|------|-----------|
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
