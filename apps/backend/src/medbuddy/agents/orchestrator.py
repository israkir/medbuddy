"""LLM tool-calling loop: model chooses tools; server executes and returns results.

Prior redacted user/assistant turns (when configured) are injected before the current user
message on the first provider hop — see ``orchestrator_prior_messages`` and ``run_tool_agent_loop``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.agents.tools.confirm_dose import ConfirmDoseTool
from medbuddy.agents.tools.drug_lookup import ExplainMedicationTool
from medbuddy.agents.tools.health_summary import GenerateHealthSummaryTool
from medbuddy.agents.tools.interaction_check import InteractionCheckTool
from medbuddy.agents.tools.log_vital import LogVitalTool
from medbuddy.agents.tools.report_missed_dose import ReportMissedDoseTool
from medbuddy.agents.tools.side_effects import ReportSideEffectsTool
from medbuddy.agents.tools.medication_crud import (
    AddMedicationTool,
    ListMedicationsTool,
    RemoveMedicationTool,
    UpdateMedicationTool,
)
from medbuddy.agents.tools.upcoming_doses import ListUpcomingDosesTool
from medbuddy.application.patient_llm_context import patient_context_for_llm
from medbuddy.application.health_events.health_issue_events_format import (
    format_health_issue_events_for_summary,
)
from medbuddy.application.profile.profile_intents import apply_profile_update_from_extracted_patch
from medbuddy.core.errors import Error as MedBuddyError
from medbuddy.core.errors import (
    MedicationExtractionError,
    MedicationNotFoundError,
    VitalExtractionError,
)
from medbuddy.core.i18n import t
from medbuddy.llm.agent_system_prompt import build_agent_system_prompt
from medbuddy.llm.agent_tool_definitions import AGENT_TOOLS_OPENAI
from medbuddy.models.domain import AgentTurnResult, ConversationTurn, MedicationRecord
from medbuddy.privacy.redact import redact_conversation_turns_for_llm
from medbuddy.reminders.lifecycle import sync_and_enqueue_reminders
from medbuddy.services import AppServices

log = logging.getLogger(__name__)

_MAX_AGENT_STEPS = 8


def orchestrator_prior_messages(
    turns: list[ConversationTurn],
    *,
    max_turns: int,
) -> list[dict[str, Any]]:
    """Redacted user/assistant turns as Chat Completions messages (excludes the current line)."""
    if max_turns <= 0 or not turns:
        return []
    redacted = redact_conversation_turns_for_llm(turns)
    tail = redacted[-max_turns:]
    out: list[dict[str, Any]] = []
    for turn in tail:
        if turn.role not in ("user", "assistant"):
            continue
        content = (turn.content or "").strip()
        if not content:
            continue
        out.append({"role": turn.role, "content": content})
    return out


_list_tool = ListMedicationsTool()
_add_tool = AddMedicationTool()
_remove_tool = RemoveMedicationTool()
_update_tool = UpdateMedicationTool()
_explain_tool = ExplainMedicationTool()
_interaction_tool = InteractionCheckTool()
_summary_tool = GenerateHealthSummaryTool()
_confirm_dose_tool = ConfirmDoseTool()
_report_missed_dose_tool = ReportMissedDoseTool()
_log_vital_tool = LogVitalTool()
_side_effects_tool = ReportSideEffectsTool()
_upcoming_doses_tool = ListUpcomingDosesTool()


@dataclass
class _OrchestrationContext:
    svc: AppServices
    user_key: str
    user_text: str
    safe_text: str
    locale: str
    user_row: dict[str, Any]
    medications: list[MedicationRecord]
    history: list[ConversationTurn]
    metadata: dict[str, Any] = field(default_factory=dict)

    async def reload_medications(self) -> None:
        self.medications = await self.svc.users.list_medications(self.user_key)


def _tool_payload(args_raw: str) -> dict[str, Any]:
    if not args_raw or not args_raw.strip():
        return {}
    try:
        data = json.loads(args_raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _tool_user_message(exc: MedBuddyError, *, locale: str) -> str:
    if isinstance(exc, MedicationExtractionError):
        return t("medication.add_incomplete", locale=locale)
    if isinstance(exc, VitalExtractionError):
        return t("vital.log_incomplete", locale=locale)
    if isinstance(exc, MedicationNotFoundError):
        return t("medication.remove_not_found", locale=locale)
    return t("agent.generic_error", locale=locale)


async def _run_tool_safe(tool: Any, **kwargs: Any) -> ToolResult:
    locale: str = kwargs.get("locale", "zh-TW")
    try:
        return await tool.run(**kwargs)
    except MedBuddyError as exc:
        log.warning("orchestrator tool=%s error=%s code=%s", tool.name, exc.message, exc.code)
        return ToolResult(reply=_tool_user_message(exc, locale=locale))
    except Exception:
        log.exception("orchestrator tool=%s unexpected error", getattr(tool, "name", "?"))
        return ToolResult(reply=t("agent.generic_error", locale=locale))


async def execute_agent_tool(
    name: str,
    arguments_json: str,
    ctx: _OrchestrationContext,
) -> str:
    """Run one named tool; return a short string for the model (tool role)."""
    args = _tool_payload(arguments_json)
    svc = ctx.svc
    user_key = ctx.user_key
    locale = ctx.locale

    if name == "list_medications":
        r = await _run_tool_safe(
            _list_tool,
            svc=svc,
            user_key=user_key,
            medications=ctx.medications,
            user_row=ctx.user_row,
            locale=locale,
        )
        return r.reply

    if name == "list_upcoming_doses":
        r = await _run_tool_safe(
            _upcoming_doses_tool,
            svc=svc,
            user_key=user_key,
            user_row=ctx.user_row,
            medications=ctx.medications,
            locale=locale,
        )
        return r.reply

    if name == "add_medication":
        r = await _run_tool_safe(
            _add_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            user_row=ctx.user_row,
            locale=locale,
        )
        await ctx.reload_medications()
        return r.reply

    if name == "remove_medication":
        mid = (args.get("medication_id") or "").strip()
        if mid:
            target = next((m for m in ctx.medications if m.id == mid), None)
            if target is None:
                return t("medication.remove_not_found", locale=locale)
            ok = await svc.users.delete_medication(user_key, mid)
            if not ok:
                return t("medication.remove_not_found", locale=locale)
            await sync_and_enqueue_reminders(svc, user_key)
            await ctx.reload_medications()
            return t("medication.removed", locale=locale, name=target.name)
        r = await _run_tool_safe(
            _remove_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            medications=ctx.medications,
            locale=locale,
        )
        await ctx.reload_medications()
        return r.reply

    if name == "remove_all_medications":
        n = await svc.users.delete_all_medications(user_key)
        await sync_and_enqueue_reminders(svc, user_key)
        await ctx.reload_medications()
        return t("medication.removed_all", locale=locale, count=n)

    if name == "update_medication":
        r = await _run_tool_safe(
            _update_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            medications=ctx.medications,
            locale=locale,
        )
        await ctx.reload_medications()
        return r.reply

    if name == "disable_reminders":
        scope = (args.get("scope") or "all").strip().lower()
        mid = (args.get("medication_id") or "").strip() or None
        if scope == "single" and not mid:
            return t("medication.reminders_disable_need_id", locale=locale)
        med_filter = mid if scope == "single" else None
        n = await svc.users.bulk_disable_reminders(user_key, medication_id=med_filter)
        await sync_and_enqueue_reminders(svc, user_key)
        if scope == "single" and med_filter:
            target = next((m for m in ctx.medications if m.id == med_filter), None)
            label = target.name if target else med_filter
            return t("medication.reminders_disabled_one", locale=locale, name=label)
        return t("medication.reminders_disabled_all", locale=locale, count=n)

    if name == "confirm_dose":
        r = await _run_tool_safe(
            _confirm_dose_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            user_row=ctx.user_row,
            locale=locale,
            record_pending_dose_as_taken=bool(args.get("record_pending_dose_as_taken", False)),
            dose_adherence_note=args.get("dose_adherence_note"),
        )
        return r.reply

    if name == "report_missed_dose":
        r = await _run_tool_safe(
            _report_missed_dose_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            locale=locale,
        )
        return r.reply

    if name == "explain_medication":
        r = await _run_tool_safe(
            _explain_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            user_row=ctx.user_row,
            medications=ctx.medications,
            history=ctx.history,
            locale=locale,
        )
        return r.reply

    if name == "report_side_effects":
        r = await _run_tool_safe(
            _side_effects_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            user_row=ctx.user_row,
            medications=ctx.medications,
            history=ctx.history,
            locale=locale,
        )
        return r.reply

    if name == "interaction_check":
        r = await _run_tool_safe(
            _interaction_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            user_row=ctx.user_row,
            medications=ctx.medications,
            history=ctx.history,
            locale=locale,
        )
        return r.reply

    if name == "log_vital":
        r = await _run_tool_safe(
            _log_vital_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            locale=locale,
        )
        return r.reply

    if name == "generate_health_summary":
        r = await _run_tool_safe(
            _summary_tool,
            svc=svc,
            user_key=user_key,
            user_row=ctx.user_row,
            medications=ctx.medications,
            locale=locale,
        )
        return r.reply

    if name == "export_health_journal":
        vitals = await svc.users.list_recent_vital_logs(user_key, limit=15)
        lines: list[str] = []
        if vitals:
            lines.append(t("journal.vitals_header", locale=locale))
            for v in vitals:
                lines.append(
                    f"- {v.created_at.isoformat()} | {v.kind or ''} | {v.display_summary or ''}"
                    + (f" | notes: {v.notes}" if v.notes else "")
                )
        timeline = await svc.users.list_recent_health_issue_events(user_key, limit=40)
        if timeline:
            lines.append(t("journal.health_timeline_header", locale=locale))
            lines.append(format_health_issue_events_for_summary(timeline))
        hist_snip = redact_conversation_turns_for_llm(ctx.history[-12:])
        if hist_snip:
            lines.append(t("journal.chat_header", locale=locale))
            for turn in hist_snip:
                lines.append(f"{turn.role}: {turn.content}")
        med_notes = [m for m in ctx.medications if (m.instructions or "").strip()]
        if med_notes:
            lines.append(t("journal.med_notes_header", locale=locale))
            for m in med_notes:
                lines.append(f"- {m.name}: {m.instructions}")
        if not lines:
            return t("journal.empty", locale=locale)
        return "\n".join(lines)

    if name == "simulate_notify_emergency_contact":
        reason = (args.get("reason") or "").strip() or "urgent symptoms"
        ctx.metadata["simulated_emergency_notification"] = True
        contact = ctx.user_row.get("emergency_contact")
        hint = contact.strip() if isinstance(contact, str) and contact.strip() else ""
        return t(
            "agent.simulated_emergency_notify",
            locale=locale,
            reason=reason,
            contact_hint=hint or t("agent.simulated_emergency_no_contact", locale=locale),
        )

    if name == "update_profile":
        patch = await svc.llm.extract_profile_patch(ctx.user_text, locale=locale)
        return await apply_profile_update_from_extracted_patch(
            svc, user_key=user_key, patch=patch, baseline_locale=locale
        )

    return t("agent.generic_error", locale=locale)


async def run_tool_agent_loop(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
    safe_text: str,
    user_row: dict[str, Any],
    medications: list[MedicationRecord],
    history: list[ConversationTurn],
    locale: str,
    llm: Any,
    max_prior_turns: int,
) -> AgentTurnResult:
    """Multi-step OpenAI-tool loop until the model returns text or max steps."""
    cat = json.dumps(
        [{"id": m.id, "name": m.name} for m in medications],
        ensure_ascii=False,
    )
    patient_ctx = await patient_context_for_llm(svc, user_key, user_row, medications, locale=locale)
    prior_msgs = orchestrator_prior_messages(history, max_turns=max_prior_turns)
    system = build_agent_system_prompt(
        locale=locale,
        medication_catalog_json=cat,
        patient_context_block=patient_ctx,
        prior_turn_count=len(prior_msgs),
    )
    ctx = _OrchestrationContext(
        svc=svc,
        user_key=user_key,
        user_text=user_text,
        safe_text=safe_text,
        locale=locale,
        user_row=user_row,
        medications=list(medications),
        history=history,
    )

    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    messages.extend(prior_msgs)
    messages.append({"role": "user", "content": safe_text})

    for step in range(_MAX_AGENT_STEPS):
        content, tool_calls = await llm.complete_chat_with_tools(
            messages=messages,
            tools=AGENT_TOOLS_OPENAI,
        )
        if tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )
            for tc in tool_calls:
                out = await execute_agent_tool(tc.name, tc.arguments, ctx)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": out,
                    }
                )
            continue
        final = (content or "").strip()
        if final:
            return AgentTurnResult(reply=final, metadata=dict(ctx.metadata))
        break

    log.warning("orchestrator: empty reply after steps user_key=%s", user_key)
    return AgentTurnResult(
        reply=t("agent.generic_error", locale=locale),
        metadata=dict(ctx.metadata),
    )
