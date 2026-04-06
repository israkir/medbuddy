"""Text-driven medication list management (add / list / remove) via classified intents."""

from __future__ import annotations

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.models.domain import Intent, MedicationRecord
from medbuddy.prompts.persona import format_patient_medication_context


async def try_medication_intent_reply(
    svc: AppServices,
    *,
    user_key: str,
    intent: Intent,
    user_text: str,
    medications: list[MedicationRecord],
    locale: str,
) -> str | None:
    if intent == Intent.LIST_MEDICATIONS:
        if not medications:
            return t("medication.list_empty", locale=locale)
        body = format_patient_medication_context(medications, locale=locale)
        intro = t("medication.list_intro", locale=locale)
        return f"{intro}\n{body}"

    if intent == Intent.ADD_MEDICATION:
        draft = await svc.llm.extract_medication_draft(user_text, locale=locale)
        if draft is None or not draft.name.strip():
            return t("medication.add_incomplete", locale=locale)
        saved = await svc.users.add_medication(user_key, draft)
        return t(
            "medication.added",
            locale=locale,
            name=saved.name,
            dosage=saved.dosage,
            schedule=saved.schedule,
        )

    if intent == Intent.REMOVE_MEDICATION:
        if not medications:
            return t("medication.remove_not_found", locale=locale)
        mid = await svc.llm.resolve_medication_removal_id(user_text, medications, locale=locale)
        if not mid:
            return t("medication.remove_not_found", locale=locale)
        target = next((m for m in medications if m.id == mid), None)
        if target is None:
            return t("medication.remove_not_found", locale=locale)
        ok = await svc.users.delete_medication(user_key, mid)
        if not ok:
            return t("medication.remove_not_found", locale=locale)
        return t("medication.removed", locale=locale, name=target.name)

    return None
