"""Side-effects reporting tool — acknowledge symptom, provide context, guide next steps.

When a user says they are *currently experiencing* a symptom they attribute to their
medication, this tool:

1. Fetches drug-registry grounding for the relevant medication (OpenFDA / TFDA).
2. Composes a patient-friendly reply that:
   - Acknowledges the symptom without dismissing or alarming.
   - Explains whether the symptom is typically expected or warrants concern,
     using only grounding data or known patterns — never invented facts.
   - Lists clear RED-FLAG signals that require immediate medical attention.
   - Recommends pharmacist / doctor follow-up proportional to severity.
   - Always ends with a disclaimer to consult their clinician.

This intent is distinct from:
- ``explain_medication`` (hypothetical side-effect questions, not currently experiencing).
- ``confirm_dose`` (logging adherence, not reporting a symptom).
- ``emergency`` (life-threatening symptoms — handled before this tool is reached).
"""

from __future__ import annotations

import logging
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.models.domain import ConversationTurn, MedicationRecord
from medbuddy.privacy.redact import redact_conversation_turns_for_llm, redact_pii_text
from medbuddy.application.patient_llm_context import patient_context_for_llm
from medbuddy.prompts.persona import get_system_persona

log = logging.getLogger(__name__)


class ReportSideEffectsTool:
    """Acknowledge a side effect report, provide drug-grounded context, guide next steps."""

    name = "report_side_effects"
    description = (
        "Handle a user-reported side effect: acknowledge, provide drug-grounded context on "
        "whether the symptom is expected, flag red-flag signs requiring immediate care, "
        "and recommend appropriate follow-up with clinician or pharmacist."
    )

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_text: str,
        user_row: dict[str, Any],
        medications: list[MedicationRecord],
        history: list[ConversationTurn],
        locale: str,
        **_: Any,
    ) -> ToolResult:
        safe_text = redact_pii_text(user_text)
        patient_ctx = await patient_context_for_llm(
            svc, user_key, user_row, medications, locale=locale
        )

        # Fetch drug grounding (best-effort; proceed without it if unavailable)
        drug_grounding = await _fetch_grounding(svc, user_text, locale)

        side_effect_persona = (
            f"{get_system_persona(locale=locale)}\n\n"
            f"{t('gemini.medication_companion_side_effects', locale=locale)}"
        )
        history_llm = redact_conversation_turns_for_llm(history)

        reply = await svc.llm.compose_reply(
            system_persona=side_effect_persona,
            patient_context=patient_ctx,
            drug_grounding=drug_grounding,
            history=history_llm,
            user_message=safe_text,
            locale=locale,
        )

        return ToolResult(reply=reply, metadata={"intent": "report_side_effects"})


async def _fetch_grounding(svc: AppServices, user_text: str, locale: str) -> str | None:
    """Fetch OpenFDA + TFDA snippets; return combined text or None."""
    _ = locale
    parts: list[str] = []
    try:
        tfda = await svc.drugs.fetch_tfda_snippet(user_text.strip())
        if tfda:
            parts.append(f"{tfda.source}: {tfda.title}\n{tfda.body_zh}")
    except Exception:
        log.debug("side_effects: TFDA fetch failed")
    try:
        ofda = await svc.drugs.fetch_openfda_label_snippet(user_text.strip())
        if ofda:
            parts.append(f"{ofda.source}: {ofda.title}\n{ofda.body_zh}")
    except Exception:
        log.debug("side_effects: OpenFDA fetch failed")
    return "\n\n".join(parts) if parts else None
