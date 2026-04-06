"""Drug explanation tool — fetch grounding data then compose a patient-friendly reply."""

from __future__ import annotations

import logging
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.drug_cache_keys import (
    DRUG_REFERENCE_SOURCE_OPENFDA,
    DRUG_REFERENCE_SOURCE_TFDA,
    normalize_query_key,
    personalization_fingerprint,
    resolve_medication_id_for_personalization,
)
from medbuddy.engine.types import AppServices
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.i18n import t
from medbuddy.models.domain import ConversationTurn, Intent, MedicationRecord
from medbuddy.privacy.redact import redact_conversation_turns_for_llm, redact_pii_text
from medbuddy.prompts.persona import build_patient_context_for_llm, get_system_persona

log = logging.getLogger(__name__)


class ExplainMedicationTool:
    """Explain a medication's purpose, dosing rationale, and basic safety notes."""

    name = "explain_medication"
    description = (
        "Explain a medication: purpose, dosing rationale, and basic safety info. "
        "Uses drug-registry grounding (OpenFDA / TFDA) when available."
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
        patient_ctx = build_patient_context_for_llm(user_row, medications, locale=locale)

        # Personalization cache check
        if svc.drug_caches is not None:
            fp = personalization_fingerprint(
                intent=Intent.EXPLAIN_MEDICATION,
                user_text=safe_text,
                patient_context=patient_ctx,
            )
            cached = await svc.drug_caches.get_personalized_reply(
                user_uuid=user_row["id"], query_fingerprint=fp
            )
            if cached:
                log.info("explain_medication: cache_hit user_key=%s", user_key)
                return ToolResult(reply=cached, metadata={"cache_hit": True})

        # Fetch grounding
        drug_grounding, ref_cache_id, grounding_source = await _fetch_grounding(
            svc, user_text, locale
        )

        system_persona = get_system_persona(locale=locale)
        system_persona = (
            f"{system_persona}\n\n{t('gemini.medication_companion_explain', locale=locale)}"
        )
        history_llm = redact_conversation_turns_for_llm(history)

        reply = await svc.llm.compose_reply(
            system_persona=system_persona,
            patient_context=patient_ctx,
            drug_grounding=drug_grounding,
            history=history_llm,
            user_message=safe_text,
            locale=locale,
        )

        # Save to personalization cache
        if svc.drug_caches is not None:
            fp = personalization_fingerprint(
                intent=Intent.EXPLAIN_MEDICATION,
                user_text=safe_text,
                patient_context=patient_ctx,
            )
            med_cache_id = resolve_medication_id_for_personalization(medications, user_text)
            prov_source = grounding_source or (
                "mock_llm" if isinstance(svc.llm, MockLLM) else svc.settings.active_llm_model_id
            )
            await svc.drug_caches.save_personalized_reply(
                user_uuid=user_row["id"],
                query_fingerprint=fp,
                intent=Intent.EXPLAIN_MEDICATION.value,
                personalized_text=reply,
                locale=locale,
                llm_meta={"cached_turn": True, "source": prov_source},
                medication_id=med_cache_id,
                reference_cache_id=ref_cache_id,
            )

        return ToolResult(reply=reply, metadata={"grounding_source": grounding_source})


async def _fetch_grounding(
    svc: AppServices, user_text: str, locale: str
) -> tuple[str | None, str | None, str | None]:
    """Return (drug_grounding_text, reference_cache_id, source_label)."""
    q = user_text.strip()
    parts: list[str] = []
    ref_cache_id: str | None = None
    source: str | None = None

    try:
        tfda = await svc.drugs.fetch_tfda_snippet(q)
    except Exception:
        log.debug("drug_lookup: TFDA fetch failed for %r", q)
        tfda = None
    try:
        ofda = await svc.drugs.fetch_openfda_label_snippet(q)
    except Exception:
        log.debug("drug_lookup: OpenFDA fetch failed for %r", q)
        ofda = None

    if tfda:
        parts.append(f"{tfda.source}: {tfda.title}\n{tfda.body_zh}")
    if ofda:
        parts.append(f"{ofda.source}: {ofda.title}\n{ofda.body_zh}")

    if svc.drug_caches is not None:
        cache_key = normalize_query_key(q)
        if ofda:
            source = DRUG_REFERENCE_SOURCE_OPENFDA
            ref_cache_id = await svc.drug_caches.get_reference_cache_id(
                source=DRUG_REFERENCE_SOURCE_OPENFDA, query_key=cache_key
            )
        elif tfda:
            source = DRUG_REFERENCE_SOURCE_TFDA
            ref_cache_id = await svc.drug_caches.get_reference_cache_id(
                source=DRUG_REFERENCE_SOURCE_TFDA, query_key=cache_key
            )

    grounding = "\n\n".join(parts) if parts else None
    return grounding, ref_cache_id, source
