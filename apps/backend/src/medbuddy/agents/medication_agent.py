"""MedicationAgent — LLM tool orchestration with fast routing hooks."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from medbuddy.agents.orchestrator import run_tool_agent_loop
from medbuddy.application.health_events.health_issue_event_log import maybe_record_health_issue_turn
from medbuddy.application.pending.dose_clarification_resolve import (
    try_resolve_pending_dose_clarification,
)
from medbuddy.application.pending.locale_intents import try_locale_change_reply
from medbuddy.application.pending.medication_add_confirm_resolve import (
    try_resolve_pending_medication_add_confirmation,
)
from medbuddy.application.pending.reminder_horizon_resolve import (
    try_resolve_pending_reminder_horizon,
)
from medbuddy.application.profile.emergency_contact_resolve import (
    try_resolve_emergency_contact_from_message,
)
from medbuddy.application.profile.profile_completion_nudge import (
    append_profile_completion_nudge_if_due,
)
from medbuddy.services import AppServices
from medbuddy.extensibility.intent_hooks import try_intent_hooks
from medbuddy.core.i18n import t
from medbuddy.models.domain import AgentTurnResult, ConversationTurn, Intent, MedicationRecord
from medbuddy.privacy.redact import (
    redact_conversation_turns_for_llm,
    redact_pii_text,
)
from medbuddy.core.locale import effective_user_locale

log = logging.getLogger(__name__)


def _preview_text(text: str, *, limit: int = 120) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


class MedicationAgent:
    """Stateless agent — create once, call ``run()`` per conversation turn."""

    async def run(
        self,
        svc: AppServices,
        *,
        user_key: str,
        user_text: str,
    ) -> AgentTurnResult:
        """Execute one full assistant turn and return reply plus optional metadata."""
        safe_text = redact_pii_text(user_text)
        log.info(
            "medication_agent: user_key=%s inbound chars=%d redacted_preview=%r",
            user_key,
            len(user_text),
            _preview_text(safe_text),
        )

        (user_row, medications), history = await asyncio.gather(
            _load_user_context(svc, user_key),
            svc.conversations.get_recent_turns(user_key, svc.settings.conversation_history_turns),
        )
        recent_ctx = _recent_context_for_intent(history)
        interpretation = await svc.llm.interpret_user_turn(safe_text, recent_context=recent_ctx)
        intent = interpretation.intent
        log.info(
            "medication_agent: user_key=%s intent=%s med_count=%d",
            user_key,
            intent.name,
            len(medications),
        )

        locale = effective_user_locale(user_row.get("locale"))

        await svc.conversations.append_turn(
            user_key,
            ConversationTurn(role="user", content=user_text, at=datetime.now(UTC)),
        )
        log.info("medication_agent: user_key=%s conversation appended role=user", user_key)

        await maybe_record_health_issue_turn(
            svc,
            user_key=user_key,
            user_text=user_text,
            locale=locale,
            intent=intent,
        )

        locale_reply = await try_locale_change_reply(
            svc,
            user_key=user_key,
            user_text=user_text,
            user_row=user_row,
            intent=intent,
            llm=svc.llm,
        )
        if locale_reply is not None:
            log.info("medication_agent: user_key=%s locale change handled", user_key)
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=locale_reply, at=datetime.now(UTC)),
            )
            return AgentTurnResult(reply=locale_reply, metadata={})

        med_confirm_reply = await try_resolve_pending_medication_add_confirmation(
            svc, user_key=user_key, user_text=user_text, locale=locale
        )
        if med_confirm_reply is not None:
            log.info(
                "medication_agent: user_key=%s pending med add confirmation resolved", user_key
            )
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=med_confirm_reply, at=datetime.now(UTC)),
            )
            return AgentTurnResult(reply=med_confirm_reply, metadata={})

        clarify_reply = await try_resolve_pending_dose_clarification(
            svc, user_key=user_key, user_text=user_text, locale=locale
        )
        if clarify_reply is not None:
            log.info("medication_agent: user_key=%s pending dose clarification resolved", user_key)
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=clarify_reply, at=datetime.now(UTC)),
            )
            return AgentTurnResult(reply=clarify_reply, metadata={})

        horizon_reply = await try_resolve_pending_reminder_horizon(
            svc, user_key=user_key, user_text=user_text, locale=locale
        )
        if horizon_reply is not None:
            log.info("medication_agent: user_key=%s pending reminder horizon resolved", user_key)
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=horizon_reply, at=datetime.now(UTC)),
            )
            return AgentTurnResult(reply=horizon_reply, metadata={})

        if intent == Intent.EMERGENCY:
            log.warning("medication_agent: user_key=%s emergency intent matched", user_key)
            contact_raw = user_row.get("emergency_contact")
            hint = (
                contact_raw.strip() if isinstance(contact_raw, str) and contact_raw.strip() else ""
            )
            if hint:
                reply = t("agent.emergency_with_saved_contact", locale=locale)
                reason = _preview_text(safe_text, limit=120)
                reply = f"{reply}\n\n" + t(
                    "agent.simulated_emergency_notify",
                    locale=locale,
                    reason=reason,
                    contact_hint=hint,
                )
                meta: dict[str, Any] = {"simulated_emergency_notification": True}
            else:
                reply = t("agent.emergency", locale=locale)
                meta = {}
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=reply, at=datetime.now(UTC)),
            )
            return AgentTurnResult(reply=reply, metadata=meta)

        contact_reply = await try_resolve_emergency_contact_from_message(
            svc,
            user_key=user_key,
            user_text=user_text,
            history=history,
            locale=locale,
            intent=intent,
        )
        if contact_reply is not None:
            log.info(
                "medication_agent: user_key=%s emergency contact line saved from chat", user_key
            )
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=contact_reply, at=datetime.now(UTC)),
            )
            return AgentTurnResult(reply=contact_reply, metadata={})

        hook_reply = await try_intent_hooks(intent, svc, user_text)
        if hook_reply is not None:
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=hook_reply, at=datetime.now(UTC)),
            )
            return AgentTurnResult(reply=hook_reply, metadata={})

        if intent == Intent.OFF_TOPIC:
            reply = t("agent.off_topic", locale=locale)
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=reply, at=datetime.now(UTC)),
            )
            return AgentTurnResult(reply=reply, metadata={})

        user_row = await svc.users.get_or_create_user(user_key)
        medications = await svc.users.list_medications(user_key)

        orch = await run_tool_agent_loop(
            svc,
            user_key=user_key,
            user_text=user_text,
            safe_text=safe_text,
            user_row=user_row,
            medications=medications,
            history=history,
            locale=locale,
            llm=svc.llm,
            max_prior_turns=svc.settings.agent_orchestrator_history_turns,
        )
        reply = await _maybe_append_pending_reminder(
            svc, user_key=user_key, reply=orch.reply, locale=locale
        )
        reply = append_profile_completion_nudge_if_due(
            settings=svc.settings,
            user_key=user_key,
            user_row=user_row,
            reply=reply,
            locale=locale,
            history_before_latest_user_message=history,
        )

        await svc.conversations.append_turn(
            user_key,
            ConversationTurn(role="assistant", content=reply, at=datetime.now(UTC)),
        )
        log.info(
            "medication_agent: user_key=%s conversation appended role=assistant reply_chars=%d",
            user_key,
            len(reply),
        )
        return AgentTurnResult(reply=reply, metadata=orch.metadata)


async def _load_user_context(
    svc: AppServices, user_key: str
) -> tuple[dict[str, Any], list[MedicationRecord]]:
    return await asyncio.gather(
        svc.users.get_or_create_user(user_key),
        svc.users.list_medications(user_key),
    )


def _recent_context_for_intent(turns: list[ConversationTurn], *, max_turns: int = 4) -> str | None:
    """Format recent turns for intent classification (redacted, last N only)."""
    if not turns:
        return None
    tail = redact_conversation_turns_for_llm(turns[-max_turns:])
    return "\n".join(f"{turn.role}: {turn.content}" for turn in tail)


async def _maybe_append_pending_reminder(
    svc: AppServices,
    *,
    user_key: str,
    reply: str,
    locale: str,
) -> str:
    """Append a one-line reminder when the user has an unanswered pending agent question."""
    med_confirm = await svc.users.get_medication_add_confirmation_pending(user_key)
    if med_confirm is not None:
        reminder = t(
            "medication.add_confirm_pending_reminder",
            locale=locale,
            name=med_confirm.draft.name,
        )
        return f"{reply}\n\n{reminder}"

    horizon = await svc.users.get_reminder_horizon_pending(user_key)
    if horizon is not None:
        reminder = t(
            "reminder.horizon_still_needed",
            locale=locale,
            name=horizon.medication_name,
        )
        return f"{reply}\n\n{reminder}"

    return reply
