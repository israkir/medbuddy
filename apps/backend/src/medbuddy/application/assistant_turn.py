"""Single assistant text turn: intent → grounding → history → LLM reply (shared by LINE + mobile)."""

from __future__ import annotations

from datetime import UTC, datetime

from medbuddy.engine.types import AppServices
from medbuddy.extensibility.intent_hooks import try_intent_hooks
from medbuddy.models.domain import ConversationTurn, Intent
from medbuddy.prompts.persona import format_patient_medication_context, get_system_persona


async def run_assistant_text_turn(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
) -> str:
    """Classify intent, optionally ground on drug APIs, append turns, return assistant text.

    ``user_key`` is the persistence id for users/conversations (LINE user id or app scoped id).
    """
    intent = await svc.llm.classify_intent(user_text)
    drug_grounding: str | None = None
    if intent in (Intent.EXPLAIN_MEDICATION, Intent.INTERACTION_CHECK):
        tfda = await svc.drugs.fetch_tfda_snippet(user_text.strip())
        ofda = await svc.drugs.fetch_openfda_label_snippet(user_text.strip())
        parts = []
        if tfda:
            parts.append(f"{tfda.source}: {tfda.title}\n{tfda.body_zh}")
        if ofda:
            parts.append(f"{ofda.source}: {ofda.title}\n{ofda.body_zh}")
        drug_grounding = "\n\n".join(parts) if parts else None

    meds = await svc.users.list_medications(user_key)
    patient_ctx = format_patient_medication_context(meds, locale=svc.settings.locale)
    history = await svc.conversations.get_recent_turns(
        user_key,
        svc.settings.conversation_history_turns,
    )

    await svc.conversations.append_turn(
        user_key,
        ConversationTurn(role="user", content=user_text, at=datetime.now(UTC)),
    )

    reply_text = await try_intent_hooks(intent, svc, user_text)
    if reply_text is None:
        reply_text = await svc.llm.compose_reply(
            system_persona=get_system_persona(locale=svc.settings.locale),
            patient_context=patient_ctx,
            drug_grounding=drug_grounding,
            history=history,
            user_message=user_text,
        )

    await svc.conversations.append_turn(
        user_key,
        ConversationTurn(role="assistant", content=reply_text, at=datetime.now(UTC)),
    )

    return reply_text
