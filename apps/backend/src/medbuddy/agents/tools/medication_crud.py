"""Medication CRUD tools: add, list, remove."""

from __future__ import annotations

import logging
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.engine.types import AppServices
from medbuddy.exceptions import MedicationExtractionError, MedicationNotFoundError
from medbuddy.i18n import t
from medbuddy.models.domain import MedicationRecord
from medbuddy.privacy.redact import redact_pii_text
from medbuddy.prompts.persona import (
    build_patient_context_for_chat_display,
    build_patient_context_for_llm,
)
from medbuddy.reminders.lifecycle import sync_and_enqueue_reminders

log = logging.getLogger(__name__)


async def _drug_grounding_text(svc: AppServices, drug_name: str) -> str | None:
    """Fetch combined TFDA + OpenFDA grounding text for a drug name."""
    q = drug_name.strip()
    if not q:
        return None
    parts: list[str] = []
    try:
        tfda = await svc.drugs.fetch_tfda_snippet(q)
        if tfda:
            parts.append(f"{tfda.source}: {tfda.title}\n{tfda.body_zh}")
    except Exception:
        log.debug("medication_crud: TFDA lookup failed for %r", q)
    try:
        ofda = await svc.drugs.fetch_openfda_label_snippet(q)
        if ofda:
            parts.append(f"{ofda.source}: {ofda.title}\n{ofda.body_zh}")
    except Exception:
        log.debug("medication_crud: OpenFDA lookup failed for %r", q)
    return "\n\n".join(parts) if parts else None


class ListMedicationsTool:
    name = "list_medications"
    description = "List all medications currently registered for the user."

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        medications: list[MedicationRecord],
        user_row: dict[str, Any],
        locale: str,
        **_: Any,
    ) -> ToolResult:
        if not medications:
            return ToolResult(reply=t("medication.list_empty", locale=locale))
        body = build_patient_context_for_chat_display(user_row, medications, locale=locale)
        intro = t("medication.list_intro", locale=locale)
        return ToolResult(reply=f"{intro}\n{body}")


class AddMedicationTool:
    name = "add_medication"
    description = "Extract medication details from the user message and add to their list."

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_text: str,
        user_row: dict[str, Any],
        locale: str,
        **_: Any,
    ) -> ToolResult:
        safe_text = redact_pii_text(user_text)
        draft = await svc.llm.extract_medication_draft(safe_text, locale=locale)
        if draft is None or not draft.name.strip():
            raise MedicationExtractionError()

        saved = await svc.users.add_medication(user_key, draft)
        meds_updated = await svc.users.list_medications(user_key)
        patient_ctx = build_patient_context_for_llm(user_row, meds_updated, locale=locale)
        drug_grounding = await _drug_grounding_text(svc, saved.name)

        try:
            reply = await svc.llm.compose_medication_added_reply(
                patient_context=patient_ctx,
                drug_grounding=drug_grounding,
                saved=saved,
                user_message=safe_text,
                locale=locale,
            )
        except Exception:
            log.exception("add_medication: compose_medication_added_reply failed; using fallback")
            reply = t(
                "medication.added",
                locale=locale,
                name=saved.name,
                dosage=saved.dosage,
                schedule=saved.schedule,
            )

        await sync_and_enqueue_reminders(svc, user_key)
        log.info("add_medication: user_key=%s added med_name=%r", user_key, saved.name)
        return ToolResult(reply=reply, structured=saved)


class RemoveMedicationTool:
    name = "remove_medication"
    description = "Identify the medication from the user message and remove it."

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_text: str,
        medications: list[MedicationRecord],
        locale: str,
        **_: Any,
    ) -> ToolResult:
        if not medications:
            return ToolResult(reply=t("medication.remove_not_found", locale=locale))

        mid = await svc.llm.resolve_medication_removal_id(
            redact_pii_text(user_text), medications, locale=locale
        )
        if not mid:
            return ToolResult(reply=t("medication.remove_not_found", locale=locale))

        target = next((m for m in medications if m.id == mid), None)
        if target is None:
            raise MedicationNotFoundError(mid)

        ok = await svc.users.delete_medication(user_key, mid)
        if not ok:
            return ToolResult(reply=t("medication.remove_not_found", locale=locale))

        await sync_and_enqueue_reminders(svc, user_key)
        log.info("remove_medication: user_key=%s removed med_id=%s name=%r", user_key, mid, target.name)
        return ToolResult(reply=t("medication.removed", locale=locale, name=target.name))
