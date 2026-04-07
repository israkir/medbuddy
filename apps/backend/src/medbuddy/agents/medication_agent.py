"""MedicationAgent — intent-to-tool orchestrator.

Replaces the monolithic ``run_assistant_text_turn`` dispatch block with a
clean tool-dispatch table.  Each ``Intent`` maps to exactly one ``AgentTool``;
unhandled intents fall back to a free-form LLM ``compose_reply``.

Flow
----
1. Load user context (profile + medications) and recent conversation turns in parallel.
2. Classify intent via ``svc.llm.classify_intent(..., recent_context=...)``.
3. Locale change, hooks, then ``off_topic`` (fixed refusal), profile regex, tools, or
   ``compose_reply`` fallback.
4. Persist both turns to conversation store.
5. Optionally cache LLM-composed replies for EXPLAIN / INTERACTION intents.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.agents.tools.drug_lookup import ExplainMedicationTool
from medbuddy.agents.tools.health_summary import GenerateHealthSummaryTool
from medbuddy.agents.tools.interaction_check import InteractionCheckTool
from medbuddy.agents.tools.confirm_dose import ConfirmDoseTool
from medbuddy.agents.tools.medication_crud import (
    AddMedicationTool,
    ListMedicationsTool,
    RemoveMedicationTool,
)
from medbuddy.application.locale_intents import try_locale_change_reply
from medbuddy.application.profile_intents import try_profile_intent_reply
from medbuddy.engine.types import AppServices
from medbuddy.exceptions import MedBuddyError
from medbuddy.extensibility.intent_hooks import try_intent_hooks
from medbuddy.i18n import t
from medbuddy.models.domain import ConversationTurn, Intent, MedicationRecord
from medbuddy.privacy.redact import (
    redact_conversation_turns_for_llm,
    redact_pii_text,
)
from medbuddy.prompts.persona import build_patient_context_for_llm, get_system_persona
from medbuddy.user_locale import effective_user_locale

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool singletons (stateless — one instance is enough)
# ---------------------------------------------------------------------------
_list_tool = ListMedicationsTool()
_add_tool = AddMedicationTool()
_remove_tool = RemoveMedicationTool()
_explain_tool = ExplainMedicationTool()
_interaction_tool = InteractionCheckTool()
_summary_tool = GenerateHealthSummaryTool()
_confirm_dose_tool = ConfirmDoseTool()

_TOOL_MAP: dict[Intent, Any] = {
    Intent.LIST_MEDICATIONS: _list_tool,
    Intent.ADD_MEDICATION: _add_tool,
    Intent.REMOVE_MEDICATION: _remove_tool,
    Intent.CONFIRM_DOSE: _confirm_dose_tool,
    Intent.EXPLAIN_MEDICATION: _explain_tool,
    Intent.INTERACTION_CHECK: _interaction_tool,
    Intent.REQUEST_SUMMARY: _summary_tool,
}


class MedicationAgent:
    """Stateless agent — create once, call ``run()`` per conversation turn."""

    async def run(
        self,
        svc: AppServices,
        *,
        user_key: str,
        user_text: str,
    ) -> str:
        """Execute one full assistant turn and return the reply text.

        Args:
            svc: Wired ``AppServices`` container.
            user_key: Stable persistence key (LINE user id or app-scoped id).
            user_text: Raw user message (may contain PII — redact before LLM).

        Returns:
            The assistant reply suitable for sending back to the user.
        """
        safe_text = redact_pii_text(user_text)

        # Load profile/meds and recent turns so intent classification can use dialogue context
        # (short replies like "一次" / "once" need the prior assistant question to avoid off_topic).
        (user_row, medications), history = await asyncio.gather(
            _load_user_context(svc, user_key),
            svc.conversations.get_recent_turns(user_key, svc.settings.conversation_history_turns),
        )
        recent_ctx = _recent_context_for_intent(history)
        intent = await svc.llm.classify_intent(safe_text, recent_context=recent_ctx)
        log.info(
            "medication_agent: user_key=%s intent=%s med_count=%d user_chars=%d",
            user_key,
            intent.name,
            len(medications),
            len(user_text),
        )

        locale = effective_user_locale(user_row.get("locale"))

        # Persist user turn before generating reply
        await svc.conversations.append_turn(
            user_key,
            ConversationTurn(role="user", content=user_text, at=datetime.now(UTC)),
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
            await svc.conversations.append_turn(
                user_key,
                ConversationTurn(role="assistant", content=locale_reply, at=datetime.now(UTC)),
            )
            return locale_reply

        # 1. Extension hooks (highest priority, can short-circuit)
        reply = await try_intent_hooks(intent, svc, user_text)

        # 2. Off-topic: refuse without calling compose_reply (no LLM for the reply body)
        if reply is None and intent == Intent.OFF_TOPIC:
            reply = t("agent.off_topic", locale=locale)

        # 3. Profile update intent (regex-based, no LLM needed)
        if reply is None and intent == Intent.UPDATE_PROFILE:
            reply = await try_profile_intent_reply(
                svc,
                user_key=user_key,
                intent=intent,
                user_text=user_text,
                locale=locale,
                llm=svc.llm,
            )

        # 4. Dispatch to registered tool
        if reply is None:
            tool = _TOOL_MAP.get(intent)
            if tool is not None:
                result = await _run_tool_safe(
                    tool,
                    svc=svc,
                    user_key=user_key,
                    user_text=user_text,
                    user_row=user_row,
                    medications=medications,
                    history=history,
                    locale=locale,
                )
                reply = result.reply
            else:
                # 5. Free-form LLM fallback for unhandled intents
                reply = await _compose_fallback_reply(
                    svc,
                    intent=intent,
                    user_row=user_row,
                    medications=medications,
                    history=history,
                    safe_text=safe_text,
                    locale=locale,
                )

        await svc.conversations.append_turn(
            user_key,
            ConversationTurn(role="assistant", content=reply, at=datetime.now(UTC)),
        )
        return reply


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
    return "\n".join(f"{t.role}: {t.content}" for t in tail)


async def _run_tool_safe(tool: Any, **kwargs: Any) -> ToolResult:
    """Run a tool, converting ``MedBuddyError`` to a user-friendly message."""
    locale: str = kwargs.get("locale", "zh-TW")
    try:
        return await tool.run(**kwargs)
    except MedBuddyError as exc:
        log.warning("agent tool=%s error=%s code=%s", tool.name, exc.message, exc.code)
        return ToolResult(reply=_user_error_message(exc, locale=locale))
    except Exception:
        log.exception("agent tool=%s unexpected error", tool.name)
        return ToolResult(reply=t("agent.generic_error", locale=locale))


def _user_error_message(exc: MedBuddyError, *, locale: str) -> str:
    from medbuddy.exceptions import MedicationExtractionError, MedicationNotFoundError

    if isinstance(exc, MedicationExtractionError):
        return t("medication.add_incomplete", locale=locale)
    if isinstance(exc, MedicationNotFoundError):
        return t("medication.remove_not_found", locale=locale)
    return t("agent.generic_error", locale=locale)


async def _compose_fallback_reply(
    svc: AppServices,
    *,
    intent: Intent,
    user_row: dict[str, Any],
    medications: list[MedicationRecord],
    history: list[ConversationTurn],
    safe_text: str,
    locale: str,
) -> str:
    patient_ctx = build_patient_context_for_llm(user_row, medications, locale=locale)
    system_persona = get_system_persona(locale=locale)
    history_llm = redact_conversation_turns_for_llm(history)
    return await svc.llm.compose_reply(
        system_persona=system_persona,
        patient_context=patient_ctx,
        drug_grounding=None,
        history=history_llm,
        user_message=safe_text,
        locale=locale,
    )
