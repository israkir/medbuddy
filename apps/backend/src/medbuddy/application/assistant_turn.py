"""Single assistant text turn: intent → grounding → history → LLM reply (shared by LINE + mobile)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from medbuddy.application.medication_intents import try_medication_intent_reply
from medbuddy.application.profile_intents import try_profile_intent_reply
from medbuddy.drug_cache_keys import (
    DRUG_REFERENCE_SOURCE_OPENFDA,
    DRUG_REFERENCE_SOURCE_TFDA,
    normalize_query_key,
    personalization_fingerprint,
    resolve_medication_id_for_personalization,
)
from medbuddy.config import Settings
from medbuddy.engine.types import AppServices
from medbuddy.extensibility.intent_hooks import try_intent_hooks
from medbuddy.i18n import t
from medbuddy.models.domain import ConversationTurn, Intent, MedicationRecord
from medbuddy.privacy.redact import redact_conversation_turns_for_llm, redact_pii_text
from medbuddy.prompts.persona import (
    build_patient_context_for_llm,
    get_system_persona,
)

log = logging.getLogger(__name__)


def _personalization_provenance_source(
    drug_grounding_source: str | None, settings: Settings
) -> str:
    """``drug_personalization_cache.llm_meta.source``: registry API id or LLM model id."""
    if drug_grounding_source:
        return drug_grounding_source
    if settings.mock_external_services:
        return "mock_llm"
    return settings.gemini_model


def _log_medications_flat(user_key: str, meds: list[MedicationRecord]) -> None:
    """One log line per medication for host log UX (grep-friendly, flat key=value style)."""
    if not meds:
        log.info("assistant_turn: user_key=%s med_count=0", user_key)
        return
    log.info("assistant_turn: user_key=%s med_count=%d", user_key, len(meds))
    for i, m in enumerate(meds):
        ins = m.instructions_zh or ""
        log.info(
            "assistant_turn: user_key=%s med_i=%d med_id=%s name=%s dosage=%s schedule=%s "
            "instructions_zh=%s",
            user_key,
            i,
            m.id,
            m.name,
            m.dosage,
            m.schedule,
            ins,
        )


async def run_assistant_text_turn(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
) -> str:
    """Classify intent, optionally ground on drug APIs, append turns, return assistant text.

    ``user_key`` is the persistence id for users/conversations (LINE user id or app scoped id).
    """
    text_for_llm = redact_pii_text(user_text)
    intent = await svc.llm.classify_intent(text_for_llm)
    log.info(
        "assistant_turn: user_key=%s intent=%s user_chars=%d",
        user_key,
        intent.name,
        len(user_text),
    )

    user_row = await svc.users.get_or_create_user(user_key)
    meds = await svc.users.list_medications(user_key)
    _log_medications_flat(user_key, meds)
    loc = svc.settings.locale
    patient_ctx = build_patient_context_for_llm(user_row, meds, locale=loc)

    if svc.drug_caches is not None and intent in (
        Intent.EXPLAIN_MEDICATION,
        Intent.INTERACTION_CHECK,
    ):
        fp = personalization_fingerprint(
            intent=intent, user_text=text_for_llm, patient_context=patient_ctx
        )
        cached_reply = await svc.drug_caches.get_personalized_reply(
            user_uuid=user_row["id"],
            query_fingerprint=fp,
        )
        if cached_reply:
            log.info(
                "assistant_turn: user_key=%s drug_personalization_cache_hit fingerprint=%s",
                user_key,
                fp[:80],
            )
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="user", content=user_text, at=datetime.now(UTC)),
            )
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=cached_reply, at=datetime.now(UTC)),
            )
            return cached_reply

    drug_grounding: str | None = None
    personalization_reference_cache_id: str | None = None
    personalization_drug_grounding_source: str | None = None
    if intent in (Intent.EXPLAIN_MEDICATION, Intent.INTERACTION_CHECK):
        qstrip = user_text.strip()
        tfda = await svc.drugs.fetch_tfda_snippet(qstrip)
        ofda = await svc.drugs.fetch_openfda_label_snippet(qstrip)
        parts = []
        if tfda:
            parts.append(f"{tfda.source}: {tfda.title}\n{tfda.body_zh}")
        if ofda:
            parts.append(f"{ofda.source}: {ofda.title}\n{ofda.body_zh}")
        drug_grounding = "\n\n".join(parts) if parts else None
        if ofda:
            personalization_drug_grounding_source = DRUG_REFERENCE_SOURCE_OPENFDA
        elif tfda:
            personalization_drug_grounding_source = DRUG_REFERENCE_SOURCE_TFDA
        if svc.drug_caches is not None:
            cache_key = normalize_query_key(qstrip)
            if ofda:
                personalization_reference_cache_id = await svc.drug_caches.get_reference_cache_id(
                    source=DRUG_REFERENCE_SOURCE_OPENFDA, query_key=cache_key
                )
            elif tfda:
                personalization_reference_cache_id = await svc.drug_caches.get_reference_cache_id(
                    source=DRUG_REFERENCE_SOURCE_TFDA, query_key=cache_key
                )

    history = await svc.conversations.get_recent_turns(
        user_key,
        svc.settings.conversation_history_turns,
    )

    await svc.conversations.append_turn(
        user_key,
        ConversationTurn(role="user", content=user_text, at=datetime.now(UTC)),
    )

    reply_text = await try_intent_hooks(intent, svc, user_text)
    composed_via_llm = False
    if reply_text is None:
        reply_text = await try_profile_intent_reply(
            svc,
            user_key=user_key,
            intent=intent,
            user_text=user_text,
            locale=loc,
        )
    if reply_text is None:
        reply_text = await try_medication_intent_reply(
            svc,
            user_key=user_key,
            intent=intent,
            user_text=user_text,
            medications=meds,
            locale=loc,
        )
    if reply_text is None:
        patient_ctx = build_patient_context_for_llm(user_row, meds, locale=loc)
        system_persona = get_system_persona(locale=loc)
        if intent == Intent.EXPLAIN_MEDICATION:
            system_persona = (
                f"{system_persona}\n\n{t('gemini.medication_companion_explain', locale=loc)}"
            )
        elif intent == Intent.INTERACTION_CHECK:
            system_persona = (
                f"{system_persona}\n\n{t('gemini.medication_companion_interactions', locale=loc)}"
            )
        history_llm = redact_conversation_turns_for_llm(history)
        reply_text = await svc.llm.compose_reply(
            system_persona=system_persona,
            patient_context=patient_ctx,
            drug_grounding=drug_grounding,
            history=history_llm,
            user_message=text_for_llm,
        )
        composed_via_llm = True

    await svc.conversations.append_turn(
        user_key,
        ConversationTurn(role="assistant", content=reply_text, at=datetime.now(UTC)),
    )

    if (
        composed_via_llm
        and svc.drug_caches is not None
        and intent in (Intent.EXPLAIN_MEDICATION, Intent.INTERACTION_CHECK)
    ):
        fp = personalization_fingerprint(
            intent=intent, user_text=text_for_llm, patient_context=patient_ctx
        )
        med_cache_id = resolve_medication_id_for_personalization(meds, user_text)
        prov_source = _personalization_provenance_source(
            personalization_drug_grounding_source, svc.settings
        )
        await svc.drug_caches.save_personalized_reply(
            user_uuid=user_row["id"],
            query_fingerprint=fp,
            intent=intent.value,
            personalized_text=reply_text,
            locale=loc,
            llm_meta={
                "cached_turn": True,
                "source": prov_source,
            },
            medication_id=med_cache_id,
            reference_cache_id=personalization_reference_cache_id,
        )

    return reply_text
