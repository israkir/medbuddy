"""Medication CRUD tools: add, update, list, remove."""

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
    build_patient_context_for_llm,
    format_patient_medication_context,
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
        log.debug("medication_crud: TFDA lookup failed query_len=%d", len(q))
    try:
        ofda = await svc.drugs.fetch_openfda_label_snippet(q)
        if ofda:
            parts.append(f"{ofda.source}: {ofda.title}\n{ofda.body_zh}")
    except Exception:
        log.debug("medication_crud: OpenFDA lookup failed query_len=%d", len(q))
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
        body = format_patient_medication_context(medications, locale=locale)
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
        log.info(
            "add_medication: user_key=%s med_id=%s name_len=%d",
            user_key,
            saved.id,
            len(saved.name or ""),
        )
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
        log.info(
            "remove_medication: user_key=%s med_id=%s name_len=%d",
            user_key,
            mid,
            len(target.name or ""),
        )
        return ToolResult(reply=t("medication.removed", locale=locale, name=target.name))


class UpdateMedicationTool:
    name = "update_medication"
    description = "Update one medication fields (name/dose/schedule/instructions)."

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
            return ToolResult(reply=t("medication.update_not_found", locale=locale))
        resolved = await svc.llm.resolve_medication_update(
            redact_pii_text(user_text), medications, locale=locale
        )
        if resolved is None or not resolved.medication_id:
            return ToolResult(reply=t("medication.update_not_found", locale=locale))
        target = next((m for m in medications if m.id == resolved.medication_id), None)
        if target is None:
            return ToolResult(reply=t("medication.update_not_found", locale=locale))

        fields: dict[str, Any] = {}
        for key in ("name", "dosage", "schedule", "instructions"):
            value = getattr(resolved, key)
            if isinstance(value, str):
                v = value.strip()
                if v:
                    fields[key] = v
        if resolved.clear_instructions:
            fields["instructions"] = None
        if not fields:
            return ToolResult(
                reply=t("medication.update_incomplete", locale=locale, name=target.name)
            )

        updated = await svc.users.patch_medication(user_key, target.id, fields)
        if updated is None:
            return ToolResult(reply=t("medication.update_not_found", locale=locale))

        await sync_and_enqueue_reminders(svc, user_key)
        log.info(
            "update_medication: user_key=%s med_id=%s fields=%s",
            user_key,
            updated.id,
            ",".join(sorted(fields.keys())),
        )
        return ToolResult(
            reply=t(
                "medication.updated",
                locale=locale,
                name=updated.name,
                dosage=updated.dosage,
                schedule=updated.schedule,
                instructions=(updated.instructions or "-"),
            ),
            structured=updated,
        )
