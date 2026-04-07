"""Record adherence and dose-row notes from structured interpretation (no second-pass heuristics)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from medbuddy.agents.base import ToolResult
from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.models.domain import DoseClarificationPending, DoseEventPendingCandidate
from medbuddy.user_timezone import effective_user_timezone


def _normalize_dose_note(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if len(s) > 500:
        return s[:500]
    return s


class ConfirmDoseTool:
    name = "confirm_dose"
    description = "Apply adherence slots from turn interpretation: record taken and/or dose note."

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_text: str,
        user_row: dict[str, Any] | None = None,
        locale: str,
        record_pending_dose_as_taken: bool = False,
        dose_adherence_note: str | None = None,
        **_: Any,
    ) -> ToolResult:
        _ = user_text
        note = _normalize_dose_note(dose_adherence_note)
        n = 0
        if record_pending_dose_as_taken:
            candidates = await svc.users.list_pending_dose_candidates(user_key, max_items=4)
            if len(candidates) > 1:
                tz_name = effective_user_timezone(
                    str(user_row.get("timezone")) if user_row and user_row.get("timezone") else None
                )
                options = _format_disambiguation_options(candidates, tz_name=tz_name)
                expires = datetime.now(UTC) + timedelta(
                    seconds=svc.settings.dose_clarification_ttl_seconds
                )
                await svc.users.set_dose_clarification_pending(
                    user_key,
                    DoseClarificationPending(
                        kind="pending_taken",
                        option_ids=tuple(c.dose_event_id for c in candidates),
                        pending_note=note,
                        expires_at=expires,
                    ),
                )
                return ToolResult(
                    reply=t(
                        "medication.confirm_dose_ambiguous",
                        locale=locale,
                        options=options,
                    )
                )
            n = await svc.users.mark_pending_doses_taken(user_key, notes=note)
        if n > 0:
            if note:
                return ToolResult(
                    reply=t(
                        "medication.confirm_dose_recorded_with_note",
                        locale=locale,
                        count=n,
                        note=note,
                    )
                )
            return ToolResult(reply=t("medication.confirm_dose_recorded", locale=locale, count=n))
        if note:
            recent_taken = await svc.users.list_recent_taken_dose_candidates(user_key, max_items=4)
            if len(recent_taken) > 1:
                tz_name = effective_user_timezone(
                    str(user_row.get("timezone")) if user_row and user_row.get("timezone") else None
                )
                options = _format_disambiguation_options(recent_taken, tz_name=tz_name)
                expires = datetime.now(UTC) + timedelta(
                    seconds=svc.settings.dose_clarification_ttl_seconds
                )
                await svc.users.set_dose_clarification_pending(
                    user_key,
                    DoseClarificationPending(
                        kind="note_on_taken",
                        option_ids=tuple(c.dose_event_id for c in recent_taken),
                        pending_note=note,
                        expires_at=expires,
                    ),
                )
                return ToolResult(
                    reply=t(
                        "medication.confirm_dose_note_ambiguous",
                        locale=locale,
                        options=options,
                    )
                )
            appended = await svc.users.append_note_to_recent_taken_dose(user_key, notes=note)
            if appended > 0:
                return ToolResult(
                    reply=t(
                        "medication.confirm_dose_note_appended",
                        locale=locale,
                        note=note,
                    )
                )
        return ToolResult(reply=t("medication.confirm_dose_none", locale=locale))


def _format_disambiguation_options(
    candidates: list[DoseEventPendingCandidate], *, tz_name: str
) -> str:
    tz = ZoneInfo(tz_name)
    lines: list[str] = []
    for idx, c in enumerate(candidates, start=1):
        ts = c.scheduled_at if c.scheduled_at.tzinfo else c.scheduled_at.replace(tzinfo=UTC)
        local_ts = ts.astimezone(tz)
        stamp = local_ts.strftime("%Y-%m-%d %H:%M")
        lines.append(f"{idx}) {c.medication_name} ({c.dosage}) - {stamp}")
    return "\n".join(lines)
