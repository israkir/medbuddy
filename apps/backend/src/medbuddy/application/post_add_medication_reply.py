"""Assemble the patient-visible reply after persisting a new medication."""

from __future__ import annotations

import logging
from typing import Any

from medbuddy.agents.tools.interaction_check import format_interaction_reply
from medbuddy.application.drug_grounding import (
    education_lines_for_medication,
    purpose_from_grounding,
)
from medbuddy.core.i18n import t
from medbuddy.llm.medication_draft_build import dose_or_schedule_display
from medbuddy.models.domain import MedicationRecord
from medbuddy.services import AppServices

log = logging.getLogger(__name__)


async def build_post_add_patient_reply(
    svc: AppServices,
    *,
    saved: MedicationRecord,
    meds_updated: list[MedicationRecord],
    patient_context: str,
    drug_grounding: str | None,
    user_message: str,
    locale: str,
    suppress_horizon_appendix: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Compose primary acknowledgment, optional list cross-check, education tail on fallback only."""
    purpose = purpose_from_grounding(drug_grounding)
    list_cross_check = len(meds_updated) >= 2

    used_llm_primary = False
    try:
        if list_cross_check:
            reply = await svc.llm.compose_medication_added_primary(
                patient_context=patient_context,
                drug_grounding=drug_grounding,
                saved=saved,
                user_message=user_message,
                locale=locale,
                suppress_horizon_appendix=suppress_horizon_appendix,
            )
        else:
            reply = await svc.llm.compose_medication_added_reply(
                patient_context=patient_context,
                drug_grounding=drug_grounding,
                saved=saved,
                user_message=user_message,
                locale=locale,
                suppress_horizon_appendix=suppress_horizon_appendix,
            )
        used_llm_primary = True
    except Exception:
        log.exception("add_medication: compose post-add reply failed; using fallback")
        un = t("medication.unspecified", locale=locale)
        reply = t(
            "medication.added",
            locale=locale,
            name=saved.name,
            dosage=dose_or_schedule_display(saved.dosage, unspecified_label=un),
            schedule=dose_or_schedule_display(saved.schedule, unspecified_label=un),
        )
        used_llm_primary = False

    if list_cross_check:
        checker = getattr(svc.llm, "post_add_interaction_crosscheck", None)
        if callable(checker):
            ix_query = t(
                "medication.post_add_interaction_user_query",
                locale=locale,
                name=saved.name,
            )
            try:
                ix_result = await checker(
                    user_message=ix_query,
                    medications=meds_updated,
                    patient_context=patient_context,
                    drug_grounding=drug_grounding,
                    locale=locale,
                )
                bridge = t("medication.post_add_interaction_bridge", locale=locale)
                ix_text = format_interaction_reply(ix_result, locale=locale)
                reply = f"{reply}\n\n{bridge}\n{ix_text}"
            except Exception:
                log.exception("add_medication: post-add interaction cross-check failed")

    if not used_llm_primary:
        edu_lines, grounded = education_lines_for_medication(
            locale=locale,
            medication_name=saved.name,
            purpose=purpose,
        )
        reply = f"{reply}\n" + "\n".join(edu_lines)
        metadata = {
            "education_cue_shown": "add",
            "education_grounding_available": grounded,
            "education_fallback_uncertain": not grounded,
        }
    else:
        metadata = {
            "education_cue_shown": "add",
            "education_grounding_available": bool(purpose),
            "education_fallback_uncertain": not bool(purpose),
        }

    return reply, metadata
