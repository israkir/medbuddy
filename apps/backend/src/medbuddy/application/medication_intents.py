"""Text-driven medication list management (add / list / remove) via classified intents."""

from __future__ import annotations

import logging

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.reminders.lifecycle import sync_and_enqueue_reminders
from medbuddy.models.domain import Intent, MedicationRecord
from medbuddy.privacy.redact import redact_pii_text
from medbuddy.prompts.persona import (
    build_patient_context_for_chat_display,
    build_patient_context_for_llm,
)

log = logging.getLogger(__name__)


async def _drug_grounding_for_query(svc: AppServices, query: str) -> str | None:
    q = query.strip()
    if not q:
        return None
    parts: list[str] = []
    tfda = await svc.drugs.fetch_tfda_snippet(q)
    ofda = await svc.drugs.fetch_openfda_label_snippet(q)
    if tfda:
        parts.append(f"{tfda.source}: {tfda.title}\n{tfda.body_zh}")
    if ofda:
        parts.append(f"{ofda.source}: {ofda.title}\n{ofda.body_zh}")
    return "\n\n".join(parts) if parts else None


async def try_medication_intent_reply(
    svc: AppServices,
    *,
    user_key: str,
    intent: Intent,
    user_text: str,
    medications: list[MedicationRecord],
    locale: str,
) -> str | None:
    user_row = await svc.users.get_or_create_user(user_key)

    if intent == Intent.LIST_MEDICATIONS:
        if not medications:
            return t("medication.list_empty", locale=locale)
        body = build_patient_context_for_chat_display(user_row, medications, locale=locale)
        intro = t("medication.list_intro", locale=locale)
        return f"{intro}\n{body}"

    if intent == Intent.ADD_MEDICATION:
        safe_text = redact_pii_text(user_text)
        draft = await svc.llm.extract_medication_draft(safe_text, locale=locale)
        if draft is None or not draft.name.strip():
            return t("medication.add_incomplete", locale=locale)
        saved = await svc.users.add_medication(user_key, draft)
        meds_updated = await svc.users.list_medications(user_key)
        patient_ctx = build_patient_context_for_llm(user_row, meds_updated, locale=locale)
        drug_grounding = await _drug_grounding_for_query(svc, saved.name)
        try:
            reply = await svc.llm.compose_medication_added_reply(
                patient_context=patient_ctx,
                drug_grounding=drug_grounding,
                saved=saved,
                user_message=safe_text,
                locale=locale,
            )
        except (OSError, ValueError, RuntimeError):
            log.exception("compose_medication_added_reply failed; using template fallback")
            reply = t(
                "medication.added",
                locale=locale,
                name=saved.name,
                dosage=saved.dosage,
                schedule=saved.schedule,
            )
        await sync_and_enqueue_reminders(svc, user_key)
        return reply

    if intent == Intent.REMOVE_MEDICATION:
        if not medications:
            return t("medication.remove_not_found", locale=locale)
        mid = await svc.llm.resolve_medication_removal_id(
            redact_pii_text(user_text), medications, locale=locale
        )
        if not mid:
            return t("medication.remove_not_found", locale=locale)
        target = next((m for m in medications if m.id == mid), None)
        if target is None:
            return t("medication.remove_not_found", locale=locale)
        ok = await svc.users.delete_medication(user_key, mid)
        if not ok:
            return t("medication.remove_not_found", locale=locale)
        await sync_and_enqueue_reminders(svc, user_key)
        return t("medication.removed", locale=locale, name=target.name)

    return None
