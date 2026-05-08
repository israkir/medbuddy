"""Drug interaction check tool — structured analysis with severity grading.

Uses Gemini structured output (``InteractionCheckResult``) so the response
is always well-typed, not free-form text requiring post-hoc parsing.
"""

from __future__ import annotations

import logging
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.application.drug_grounding_query import resolve_registry_lookup_query
from medbuddy.integrations.caching_drugs import (
    DRUG_REFERENCE_SOURCE_OPENFDA,
    normalize_query_key,
    personalization_fingerprint,
    resolve_medication_id_for_personalization,
)
from medbuddy.services import AppServices
from medbuddy.core.i18n import t
from medbuddy.llm.schemas import InteractionCheckResult
from medbuddy.models.domain import ConversationTurn, Intent, InteractionResult, MedicationRecord
from medbuddy.privacy.redact import redact_pii_text
from medbuddy.application.patient_llm_context import patient_context_for_llm

log = logging.getLogger(__name__)


class InteractionCheckTool:
    """Check for clinically relevant interactions among the user's medications."""

    name = "interaction_check"
    description = (
        "Analyse drug-drug and drug-condition interactions for the patient's "
        "current medication list. Returns severity-graded structured output."
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
        drug_query: str | None = None,
        medication_id: str | None = None,
        **_: Any,
    ) -> ToolResult:
        safe_text = redact_pii_text(user_text)
        registry_q = resolve_registry_lookup_query(
            user_text=user_text,
            history=history,
            medications=medications,
            drug_query=drug_query,
            medication_id=medication_id,
        )
        # Include actual health notes so the LLM can check drug-condition interactions.
        patient_ctx = await patient_context_for_llm(
            svc, user_key, user_row, medications, locale=locale, include_health_notes=True
        )

        # Personalization cache check
        if svc.drug_caches is not None:
            fp = personalization_fingerprint(
                intent=Intent.INTERACTION_CHECK,
                user_text=safe_text,
                patient_context=patient_ctx,
            )
            cached = await svc.drug_caches.get_personalized_reply(
                user_uuid=user_row["id"], query_fingerprint=fp
            )
            if cached:
                log.info("interaction_check: cache_hit user_key=%s", user_key)
                return ToolResult(reply=cached, metadata={"cache_hit": True})

        # Fetch grounding for mentioned drugs (resolved query avoids "sure" → OpenFDA).
        grounding_parts: list[str] = []
        grounding_sources: list[str] = []
        ref_cache_id: str | None = None

        if registry_q and registry_q.strip():
            q = registry_q.strip()
            try:
                ofda = await svc.drugs.fetch_openfda_label_snippet(q)
            except Exception:
                log.debug("interaction_check: OpenFDA fetch failed query_len=%d", len(q))
                ofda = None

            if ofda:
                grounding_parts.append(f"{ofda.source}: {ofda.title}\n{ofda.body_zh}")
                if ofda.warnings:
                    grounding_parts.append(f"Warnings: {ofda.warnings[:1000]}")
                grounding_sources.append(DRUG_REFERENCE_SOURCE_OPENFDA)
                if svc.drug_caches is not None:
                    ref_cache_id = await svc.drug_caches.get_reference_cache_id(
                        source=DRUG_REFERENCE_SOURCE_OPENFDA,
                        query_key=normalize_query_key(q),
                    )

        drug_grounding = "\n\n".join(grounding_parts) if grounding_parts else None

        # Use structured LLM method when available, fall back to compose_reply
        if hasattr(svc.llm, "check_interactions_structured"):
            interaction_result: InteractionResult = await svc.llm.check_interactions_structured(
                user_message=safe_text,
                medications=medications,
                patient_context=patient_ctx,
                drug_grounding=drug_grounding,
                locale=locale,
            )
            reply = format_interaction_reply(interaction_result, locale=locale)
        else:
            from medbuddy.llm.prompts.persona import get_system_persona

            system_persona = get_system_persona(locale=locale)
            system_persona = (
                f"{system_persona}\n\n"
                f"{t('llm.medication_companion_interactions', locale=locale)}"
            )
            reply = await svc.llm.compose_reply(
                system_persona=system_persona,
                patient_context=patient_ctx,
                drug_grounding=drug_grounding,
                history=[],
                user_message=safe_text,
                locale=locale,
            )
            interaction_result = InteractionResult(
                query=safe_text,
                result=_stub_interaction_result(reply),
                grounding_sources=grounding_sources,
            )

        # Save to personalization cache
        if svc.drug_caches is not None:
            fp = personalization_fingerprint(
                intent=Intent.INTERACTION_CHECK,
                user_text=safe_text,
                patient_context=patient_ctx,
            )
            extra_parts: list[str] = []
            if safe_text.strip() != user_text.strip():
                extra_parts.append(safe_text)
            if registry_q and normalize_query_key(registry_q) != normalize_query_key(user_text):
                extra_parts.append(registry_q)
            med_cache_id = resolve_medication_id_for_personalization(
                medications,
                user_text,
                extra_query_text=" ".join(extra_parts).strip() or None,
            )
            prov_source = (
                grounding_sources[0] if grounding_sources else svc.llm.drug_cache_provenance_id
            )
            await svc.drug_caches.save_personalized_reply(
                user_uuid=user_row["id"],
                query_fingerprint=fp,
                intent=Intent.INTERACTION_CHECK.value,
                personalized_text=reply,
                locale=locale,
                llm_meta={"cached_turn": True, "source": prov_source},
                medication_id=med_cache_id,
                reference_cache_id=ref_cache_id,
            )

        return ToolResult(
            reply=reply,
            structured=interaction_result,
            metadata={
                "has_serious_interactions": interaction_result.has_serious_interactions,
                "grounding_sources": grounding_sources,
            },
        )


def format_interaction_reply(result: InteractionResult, *, locale: str) -> str:
    """Render an ``InteractionResult`` as a readable patient-facing message."""
    r = result.result
    lines = [r.summary]
    if r.interactions:
        lines.append("")
        for ix in r.interactions:
            severity_label = _severity_label(ix.severity, locale=locale)
            lines.append(
                t(
                    "interaction.pair_line",
                    locale=locale,
                    drug_a=ix.drug_a,
                    drug_b=ix.drug_b,
                    severity=severity_label,
                )
            )
            lines.append(f"  {ix.description}")
            rec = t("interaction.recommendation_prefix", locale=locale)
            lines.append(f"  {rec}{ix.recommendation}")
    lines.append("")
    lines.append(r.disclaimer)
    return "\n".join(lines)


def _severity_label(severity: str, *, locale: str) -> str:
    s = severity.lower()
    key = f"interaction.severity_{s}"
    if s in ("none", "mild", "moderate", "severe", "unknown"):
        return t(key, locale=locale)
    return severity


def _stub_interaction_result(text: str) -> InteractionCheckResult:
    """Create a minimal InteractionCheckResult when structured output is unavailable."""
    return InteractionCheckResult(
        medications_checked=[],
        interactions=[],
        overall_severity="unknown",
        summary=text,
        disclaimer="",
    )
