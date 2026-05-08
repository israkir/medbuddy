"""Medication CRUD tools: add, update, list, remove."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.services import AppServices
from medbuddy.core.errors import MedicationExtractionError, MedicationNotFoundError
from medbuddy.core.i18n import t
from medbuddy.llm.medication_draft_build import (
    apply_one_off_reminder_dose_default,
    dose_or_schedule_display,
    medication_draft_needs_add_confirmation,
)
from medbuddy.models.domain import (
    MedicationAddConfirmationPending,
    MedicationDraft,
    MedicationRecord,
    ReminderHorizonPending,
)
from medbuddy.privacy.redact import redact_pii_text
from medbuddy.application.patient_llm_context import patient_context_for_llm
from medbuddy.llm.prompts.persona import format_patient_medication_context
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


def _purpose_from_grounding(grounding: str | None) -> str | None:
    """Best-effort one-liner from grounding text for quick education cues."""
    if not grounding:
        return None
    for raw in grounding.splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("tfda(") or lowered.startswith("openfda("):
            continue
        for sep in (":", "："):
            if sep in line:
                _, tail = line.split(sep, 1)
                line = tail.strip()
                break
        if not line:
            continue
        trimmed = line[:140].rstrip(".,;: ")
        return trimmed
    return None


def _education_lines_for_medication(
    *,
    locale: str,
    medication_name: str,
    purpose: str | None,
) -> tuple[list[str], bool]:
    if purpose:
        lines = [
            t(
                "medication.education_purpose_line",
                locale=locale,
                name=medication_name,
                purpose=purpose,
            ),
            t("medication.education_deep_dive_cta", locale=locale),
            t("medication.education_boundary", locale=locale),
        ]
        return lines, True
    lines = [
        t("medication.education_uncertain_line", locale=locale, name=medication_name),
        t("medication.education_deep_dive_cta", locale=locale),
        t("medication.education_boundary", locale=locale),
    ]
    return lines, False


async def persist_medication_add_from_draft(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
    draft: MedicationDraft,
    locale: str,
) -> ToolResult:
    """Save draft, sync reminders, and compose the post-add reply (shared confirm + add tool)."""
    safe_text = redact_pii_text(user_text)
    user_row = await svc.users.get_or_create_user(user_key)
    saved = await svc.users.add_medication(user_key, draft)
    meds_updated = await svc.users.list_medications(user_key)
    await sync_and_enqueue_reminders(svc, user_key)

    # If daily reminders need a duration answer from the user, set a pending state so
    # the next message that clearly states "N days" is automatically resolved.
    if draft.needs_horizon_confirmation:
        expires = datetime.now(UTC) + timedelta(seconds=svc.settings.dose_clarification_ttl_seconds)
        await svc.users.set_reminder_horizon_pending(
            user_key,
            ReminderHorizonPending(
                medication_id=saved.id,
                medication_name=saved.name,
                expires_at=expires,
            ),
        )

    # Include actual health notes so the LLM can flag drug-condition contraindications.
    patient_ctx = await patient_context_for_llm(
        svc,
        user_key,
        user_row,
        meds_updated,
        locale=locale,
        sync_dose_events_first=False,
        include_health_notes=True,
    )
    drug_grounding = await _drug_grounding_text(svc, saved.name)

    purpose: str | None = _purpose_from_grounding(drug_grounding)
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
        un = t("medication.unspecified", locale=locale)
        reply = t(
            "medication.added",
            locale=locale,
            name=saved.name,
            dosage=dose_or_schedule_display(saved.dosage, unspecified_label=un),
            schedule=dose_or_schedule_display(saved.schedule, unspecified_label=un),
        )
    education_lines, grounded = _education_lines_for_medication(
        locale=locale,
        medication_name=saved.name,
        purpose=purpose,
    )
    reply = f"{reply}\n" + "\n".join(education_lines)
    log.info(
        "add_medication: user_key=%s med_id=%s name_len=%d (from_draft)",
        user_key,
        saved.id,
        len(saved.name or ""),
    )
    return ToolResult(
        reply=reply,
        structured=saved,
        metadata={
            "education_cue_shown": "add",
            "education_grounding_available": grounded,
            "education_fallback_uncertain": not grounded,
        },
    )


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
        purpose_tags: list[str] = []
        for med in medications[:2]:
            grounding = await _drug_grounding_text(svc, med.name)
            purpose = _purpose_from_grounding(grounding)
            if purpose:
                purpose_tags.append(
                    t(
                        "medication.education_purpose_line",
                        locale=locale,
                        name=med.name,
                        purpose=purpose,
                    )
                )
        intro = t("medication.list_intro", locale=locale)
        parts = [f"{intro}\n{body}"]
        if purpose_tags:
            parts.append("\n".join(purpose_tags))
        parts.append(t("medication.list_education_cta", locale=locale))
        return ToolResult(
            reply="\n".join(parts),
            metadata={
                "education_cue_shown": "list",
                "education_grounding_available": bool(purpose_tags),
                "education_fallback_uncertain": not bool(purpose_tags),
            },
        )


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

        un = t("medication.unspecified", locale=locale)
        draft = apply_one_off_reminder_dose_default(draft, unspecified_label=un, locale=locale)
        if medication_draft_needs_add_confirmation(
            draft, unspecified_label=un, user_text=user_text
        ):
            expires = datetime.now(UTC) + timedelta(
                seconds=svc.settings.dose_clarification_ttl_seconds
            )
            await svc.users.set_medication_add_confirmation_pending(
                user_key,
                MedicationAddConfirmationPending(draft=draft, expires_at=expires),
            )
            instr = (draft.instructions or "").strip()
            instr_disp = (
                instr if instr else t("medication.add_confirm_no_instructions", locale=locale)
            )
            reply = t(
                "medication.add_confirm_prompt",
                locale=locale,
                name=draft.name,
                dosage=dose_or_schedule_display(draft.dosage, unspecified_label=un),
                schedule=dose_or_schedule_display(draft.schedule, unspecified_label=un),
                instructions=instr_disp,
            )
            return ToolResult(reply=reply)

        return await persist_medication_add_from_draft(
            svc,
            user_key=user_key,
            user_text=user_text,
            draft=draft,
            locale=locale,
        )


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
        un = t("medication.unspecified", locale=locale)
        dose_disp = dose_or_schedule_display(updated.dosage, unspecified_label=un)
        sched_disp = dose_or_schedule_display(updated.schedule, unspecified_label=un)
        inst = updated.instructions if isinstance(updated.instructions, str) else ""
        if inst.strip():
            reply = t(
                "medication.updated_with_note",
                locale=locale,
                name=updated.name,
                dosage=dose_disp,
                schedule=sched_disp,
                instructions=inst.strip(),
            )
        else:
            reply = t(
                "medication.updated",
                locale=locale,
                name=updated.name,
                dosage=dose_disp,
                schedule=sched_disp,
            )
        if "dosage" in fields or "schedule" in fields:
            reply = f"{reply}\n{t('medication.update_reminder_followup', locale=locale)}"
        material_change = any(k in fields for k in ("name", "dosage", "schedule"))
        grounded = False
        uncertain = False
        if material_change:
            grounding = await _drug_grounding_text(svc, updated.name)
            purpose = _purpose_from_grounding(grounding)
            education_lines, grounded = _education_lines_for_medication(
                locale=locale,
                medication_name=updated.name,
                purpose=purpose,
            )
            uncertain = not grounded
            reply = f"{reply}\n" + "\n".join(education_lines)
        metadata: dict[str, Any] = {
            "education_grounding_available": grounded,
            "education_fallback_uncertain": uncertain,
        }
        if material_change:
            metadata["education_cue_shown"] = "update"
        return ToolResult(reply=reply, structured=updated, metadata=metadata)
