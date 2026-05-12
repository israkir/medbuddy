"""LLM tool-calling loop: model chooses tools; server executes and returns results.

Prior redacted user/assistant turns (when configured) are injected before the current user
message on the first provider hop — see ``orchestrator_prior_messages`` and ``run_tool_agent_loop``.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, cast

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
from medbuddy.agents.tools.health_history_lookup import LookupHealthHistoryTool
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
from medbuddy.llm.prompts.persona import format_health_conditions_block_for_llm
from medbuddy.llm.schemas import HealthConditionItem
from medbuddy.models.domain import (
    AgentTurnResult,
    ConversationTurn,
    HealthConditionInput,
    MedicationRecord,
    TurnInterpretation,
)
from medbuddy.privacy.redact import redact_conversation_turns_for_llm
from medbuddy.reminders.lifecycle import sync_and_enqueue_reminders
from medbuddy.services import AppServices
from medbuddy.application.profile.emergency_contacts import (
    emergency_contacts_hint_all,
    emergency_contacts_redacted_hint,
)

log = logging.getLogger(__name__)

_MAX_AGENT_STEPS = 8


def _tool_args_to_health_condition_inputs(raw: object) -> list[HealthConditionInput]:
    out: list[HealthConditionInput] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        cat_s = str(item.get("category") or "condition").strip().lower()
        cat: Literal["allergy", "condition", "history"] = cast(
            Literal["allergy", "condition", "history"],
            cat_s if cat_s in ("allergy", "condition", "history") else "condition",
        )
        act_s = str(item.get("action") or "add").strip().lower()
        act: Literal["add", "remove"] = cast(
            Literal["add", "remove"],
            act_s if act_s in ("add", "remove") else "add",
        )
        sev_r = item.get("severity")
        severity = sev_r.strip() if isinstance(sev_r, str) and sev_r.strip() else None
        notes_r = item.get("notes")
        notes = notes_r.strip() if isinstance(notes_r, str) and notes_r.strip() else None
        out.append(
            HealthConditionInput(
                name=name,
                category=cat,
                severity=severity,
                notes=notes,
                action=act,
            )
        )
    return out


def _schema_health_items_to_inputs(items: list[HealthConditionItem]) -> list[HealthConditionInput]:
    out: list[HealthConditionInput] = []
    for c in items:
        nm = (c.name or "").strip()
        if not nm:
            continue
        cat_s = str(c.category or "condition").strip().lower()
        cat: Literal["allergy", "condition", "history"] = cast(
            Literal["allergy", "condition", "history"],
            cat_s if cat_s in ("allergy", "condition", "history") else "condition",
        )
        act_s = str(c.action or "add").strip().lower()
        act: Literal["add", "remove"] = cast(
            Literal["add", "remove"],
            act_s if act_s in ("add", "remove") else "add",
        )
        sev = c.severity.strip() if isinstance(c.severity, str) and c.severity.strip() else None
        nts = c.notes.strip() if isinstance(c.notes, str) and c.notes.strip() else None
        out.append(HealthConditionInput(name=nm, category=cat, severity=sev, notes=nts, action=act))
    return out


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


_EXTRACTION_CONTEXT_MAX_TURNS = 8


def recent_conversation_for_medication_extraction(
    turns: list[ConversationTurn],
    *,
    max_turns: int = _EXTRACTION_CONTEXT_MAX_TURNS,
) -> str | None:
    """Redacted user/assistant lines as one block for ``extract_medication_draft`` (excludes current line)."""
    if max_turns <= 0 or not turns:
        return None
    redacted = redact_conversation_turns_for_llm(turns)
    tail = redacted[-max_turns:]
    lines: list[str] = []
    for turn in tail:
        if turn.role not in ("user", "assistant"):
            continue
        content = (turn.content or "").strip()
        if not content:
            continue
        lines.append(f"{turn.role}: {content}")
    if not lines:
        return None
    return "\n".join(lines)


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
    interpretation: TurnInterpretation | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    pii_token_substitutions: dict[str, str] = field(default_factory=dict)

    async def reload_medications(self) -> None:
        self.medications = await self.svc.users.list_medications(self.user_key)

    async def reload_user_row(self) -> None:
        self.user_row = await self.svc.users.get_or_create_user(self.user_key)


def _merge_confirm_dose_payload(
    args: dict[str, Any],
    interpretation: TurnInterpretation | None,
) -> tuple[bool, str | None]:
    """Combine planner JSON with classifier adherence slots (stage-1 structured output)."""
    tool_record = bool(args.get("record_pending_dose_as_taken", False))
    tool_raw = args.get("dose_adherence_note")
    tool_note = tool_raw.strip() if isinstance(tool_raw, str) else None

    if interpretation is None:
        return tool_record, tool_note

    interp_record = bool(interpretation.record_pending_dose_as_taken)
    interp_raw = interpretation.dose_adherence_note
    interp_note = interp_raw.strip() if isinstance(interp_raw, str) else None

    record = tool_record or interp_record

    if tool_note and interp_note:
        if tool_note == interp_note:
            note: str | None = tool_note
        else:
            combined = f"{tool_note} | {interp_note}"
            note = combined[:500] if len(combined) > 500 else combined
    elif tool_note:
        note = tool_note
    else:
        note = interp_note

    return record, note


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

    def _capture_metadata(result: ToolResult, tool_name: str) -> None:
        if result.metadata:
            ctx.metadata.update(result.metadata)
        ctx.metadata["last_tool_name"] = tool_name
        cue = str(ctx.metadata.get("education_cue_shown") or "").strip()
        if cue and tool_name in {"explain_medication", "interaction_check"}:
            ctx.metadata["education_cta_clicked"] = True

    if name == "list_medications":
        r = await _run_tool_safe(
            _list_tool,
            svc=svc,
            user_key=user_key,
            medications=ctx.medications,
            user_row=ctx.user_row,
            locale=locale,
        )
        _capture_metadata(r, name)
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
        _capture_metadata(r, name)
        return r.reply

    if name == "add_medication":
        recent_extraction = recent_conversation_for_medication_extraction(ctx.history)
        r = await _run_tool_safe(
            _add_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            user_row=ctx.user_row,
            locale=locale,
            recent_context=recent_extraction,
        )
        _capture_metadata(r, name)
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
        _capture_metadata(r, name)
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
        _capture_metadata(r, name)
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
        rec, note = _merge_confirm_dose_payload(args, ctx.interpretation)
        r = await _run_tool_safe(
            _confirm_dose_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            user_row=ctx.user_row,
            locale=locale,
            record_pending_dose_as_taken=rec,
            dose_adherence_note=note,
        )
        _capture_metadata(r, name)
        return r.reply

    if name == "report_missed_dose":
        r = await _run_tool_safe(
            _report_missed_dose_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            locale=locale,
        )
        _capture_metadata(r, name)
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
            drug_query=(args.get("drug_query") or None),
            medication_id=(args.get("medication_id") or None),
        )
        _capture_metadata(r, name)
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
        _capture_metadata(r, name)
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
            drug_query=(args.get("drug_query") or None),
            medication_id=(args.get("medication_id") or None),
        )
        _capture_metadata(r, name)
        return r.reply

    if name == "log_vital":
        r = await _run_tool_safe(
            _log_vital_tool,
            svc=svc,
            user_key=user_key,
            user_text=ctx.user_text,
            locale=locale,
        )
        _capture_metadata(r, name)
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
        _capture_metadata(r, name)
        return r.reply

    if name == "export_health_journal":
        vitals = await svc.users.list_recent_vital_logs(user_key, limit=15)
        lines: list[str] = []
        hc_rows = await svc.users.list_health_conditions(user_key, active_only=True)
        hc_block = format_health_conditions_block_for_llm(hc_rows, locale=locale)
        if hc_block.strip():
            lines.append(t("journal.health_conditions_header", locale=locale))
            lines.append(hc_block)
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
        hint = emergency_contacts_hint_all(ctx.user_row.get("emergency_contacts"), locale=locale)
        return t(
            "agent.simulated_emergency_notify",
            locale=locale,
            reason=reason,
            contact_hint=hint or t("agent.simulated_emergency_no_contact", locale=locale),
        )

    if name == "manage_health_conditions":
        action = (args.get("action") or "add").strip().lower()
        if action not in ("add", "remove", "list"):
            action = "add"

        if action == "list":
            rows = await svc.users.list_health_conditions(user_key, active_only=True)
            body = format_health_conditions_block_for_llm(rows, locale=locale)
            if not body.strip():
                return t("agent.health_conditions_list_empty", locale=locale)
            return f"{t('agent.health_conditions_list_intro', locale=locale)}\n\n{body}"

        if action == "remove":
            cid = (args.get("condition_id") or "").strip()
            if cid:
                ok = await svc.users.deactivate_health_condition(user_key, cid)
                await ctx.reload_user_row()
                if ok:
                    return t("agent.health_conditions_removed_id", locale=locale)
                return t("agent.health_conditions_unclear", locale=locale)

        inputs = _tool_args_to_health_condition_inputs(args.get("conditions"))
        if not inputs:
            items = await svc.llm.extract_health_conditions(ctx.user_text, locale=locale)
            inputs = _schema_health_items_to_inputs(items)
        if action == "remove":
            inputs = [
                HealthConditionInput(
                    name=i.name,
                    category=i.category,
                    severity=i.severity,
                    notes=i.notes,
                    action="remove",
                )
                for i in inputs
            ]
        if not inputs:
            return t("agent.health_conditions_unclear", locale=locale)
        saved = await svc.users.upsert_health_conditions(user_key, inputs)
        await ctx.reload_user_row()
        if not saved:
            return t("agent.health_conditions_unclear", locale=locale)
        return t("agent.health_conditions_saved", locale=locale, count=len(saved))

    if name == "update_profile":
        patch = await svc.llm.extract_profile_patch(ctx.user_text, locale=locale)
        reply = await apply_profile_update_from_extracted_patch(
            svc, user_key=user_key, patch=patch, baseline_locale=locale
        )
        await ctx.reload_user_row()
        return reply

    if name == "lookup_health_history":
        since_days = args.get("since_days")
        if isinstance(since_days, (int, float)):
            since_days = int(since_days)
        else:
            since_days = None
        r = await LookupHealthHistoryTool().run(
            svc=svc,
            user_key=user_key,
            locale=locale,
            since_days=since_days,
        )
        return r.reply

    return t("agent.generic_error", locale=locale)


async def _orchestrator_system_prompt_content(
    svc: AppServices,
    *,
    user_key: str,
    user_row: dict[str, Any],
    medications: list[MedicationRecord],
    locale: str,
    prior_turn_count: int,
    system_prompt_suffix: str | None,
) -> str:
    """Build the medication-agent system message (catalog JSON + patient context block)."""
    cat = json.dumps(
        [{"id": m.id, "name": m.name} for m in medications],
        ensure_ascii=False,
    )
    patient_ctx = await patient_context_for_llm(svc, user_key, user_row, medications, locale=locale)
    return build_agent_system_prompt(
        locale=locale,
        medication_catalog_json=cat,
        patient_context_block=patient_ctx,
        prior_turn_count=prior_turn_count,
        extra_instructions=system_prompt_suffix,
    )


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
    interpretation: TurnInterpretation | None = None,
    tools: list[dict[str, Any]] | None = None,
    system_prompt_suffix: str | None = None,
) -> AgentTurnResult:
    """Multi-step OpenAI-tool loop until the model returns text or max steps."""
    prior_msgs = orchestrator_prior_messages(history, max_turns=max_prior_turns)
    prior_turn_count = len(prior_msgs)
    system = await _orchestrator_system_prompt_content(
        svc,
        user_key=user_key,
        user_row=user_row,
        medications=medications,
        locale=locale,
        prior_turn_count=prior_turn_count,
        system_prompt_suffix=system_prompt_suffix,
    )
    _ec_hint, _token_map = emergency_contacts_redacted_hint(
        user_row.get("emergency_contacts"), locale=locale
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
        interpretation=interpretation,
        pii_token_substitutions=_token_map,
    )

    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    messages.extend(prior_msgs)
    messages.append({"role": "user", "content": safe_text})

    effective_tools: list[dict[str, Any]] = (
        tools if tools is not None else cast(list[dict[str, Any]], AGENT_TOOLS_OPENAI)
    )

    for step in range(_MAX_AGENT_STEPS):
        content, tool_calls = await llm.complete_chat_with_tools(
            messages=messages,
            tools=effective_tools,
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
            names_in_batch = {tc.name for tc in tool_calls}
            for tc in tool_calls:
                out = await execute_agent_tool(tc.name, tc.arguments, ctx)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": out,
                    }
                )
            intr = ctx.interpretation
            if (
                intr is not None
                and "report_side_effects" in names_in_batch
                and "confirm_dose" not in names_in_batch
                and (intr.record_pending_dose_as_taken or (intr.dose_adherence_note or "").strip())
            ):
                mech_id = f"mechanical-confirm-dose-{uuid.uuid4().hex[:12]}"
                out = await execute_agent_tool(
                    "confirm_dose",
                    json.dumps(
                        {"record_pending_dose_as_taken": False, "dose_adherence_note": None},
                    ),
                    ctx,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": mech_id,
                        "content": out,
                    }
                )
            _PROMPT_REFRESH_TOOLS = {
                "update_profile",
                "manage_health_conditions",
                "add_medication",
                "remove_medication",
                "update_medication",
                "remove_all_medications",
            }
            if names_in_batch & _PROMPT_REFRESH_TOOLS:
                messages[0]["content"] = await _orchestrator_system_prompt_content(
                    svc,
                    user_key=user_key,
                    user_row=ctx.user_row,
                    medications=ctx.medications,
                    locale=locale,
                    prior_turn_count=prior_turn_count,
                    system_prompt_suffix=system_prompt_suffix,
                )
            continue
        final = (content or "").strip()
        if final:
            if ctx.pii_token_substitutions:
                for _token, _real in ctx.pii_token_substitutions.items():
                    final = final.replace(_token, _real)
                # Strip any hallucinated tokens the map didn't cover.
                leftover = re.sub(r"\[EMERGENCY_CONTACT_\d+\]", "", final).strip()
                if leftover != final.strip():
                    log.warning(
                        "orchestrator: LLM emitted unmapped emergency-contact token user_key=%s",
                        user_key,
                    )
                    final = leftover
            return AgentTurnResult(reply=final, metadata=dict(ctx.metadata))
        break

    log.warning("orchestrator: empty reply after steps user_key=%s", user_key)
    return AgentTurnResult(
        reply=t("agent.generic_error", locale=locale),
        metadata=dict(ctx.metadata),
    )
