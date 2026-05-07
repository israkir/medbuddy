"""Record adherence and dose-row notes from structured interpretation (no second-pass heuristics)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from medbuddy.agents.base import ToolResult
from medbuddy.services import AppServices
from medbuddy.core.i18n import t
from medbuddy.llm.medication_draft_build import dose_or_schedule_display, is_placeholder_field
from medbuddy.models.domain import DoseClarificationPending, DoseEventPendingCandidate
from medbuddy.core.timezone import effective_user_timezone

_NUDGE_AUTO_CONFIRM_MINUTES = 60


def _normalize_dose_note(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if len(s) > 500:
        return s[:500]
    return s


def _real_candidates(
    candidates: list[DoseEventPendingCandidate],
) -> list[DoseEventPendingCandidate]:
    """Drop candidates whose medication name is an unrecognised placeholder."""
    return [c for c in candidates if not is_placeholder_field(c.medication_name)]


def _nudge_auto_target(
    candidates: list[DoseEventPendingCandidate],
    *,
    now_utc: datetime,
) -> DoseEventPendingCandidate | None:
    """Return the single most-recently-nudged candidate if within the auto-confirm window."""
    cutoff = now_utc - timedelta(minutes=_NUDGE_AUTO_CONFIRM_MINUTES)
    recent = sorted(
        [c for c in candidates if c.last_nudge_at and c.last_nudge_at >= cutoff],
        key=lambda c: c.last_nudge_at,  # type: ignore[arg-type]
        reverse=True,
    )
    return recent[0] if recent else None


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
            all_candidates = await svc.users.list_pending_dose_candidates(user_key)
            candidates = _real_candidates(all_candidates)
            now_utc = datetime.now(UTC)

            auto_target = _nudge_auto_target(candidates, now_utc=now_utc)
            if auto_target is not None:
                # A reminder was sent for this exact dose recently — confirm it without asking.
                n = await svc.users.mark_dose_events_taken(
                    user_key, [auto_target.dose_event_id], notes=note
                )
            elif len(candidates) > 1:
                tz_name = effective_user_timezone(
                    str(user_row.get("timezone")) if user_row and user_row.get("timezone") else None
                )
                options = _format_disambiguation_options(candidates, tz_name=tz_name, locale=locale)
                expires = now_utc + timedelta(seconds=svc.settings.dose_clarification_ttl_seconds)
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
                    reply=t("medication.confirm_dose_ambiguous", locale=locale, options=options)
                )
            elif len(candidates) == 1:
                n = await svc.users.mark_dose_events_taken(
                    user_key, [candidates[0].dose_event_id], notes=note
                )
            # else: no candidates → fall through to confirm_dose_none

        if n > 0:
            confirmed = auto_target or (candidates[0] if len(candidates) == 1 else None)
            if confirmed is not None:
                un = t("medication.unspecified", locale=locale)
                dose_disp = dose_or_schedule_display(confirmed.dosage, unspecified_label=un)
                if note:
                    return ToolResult(
                        reply=t(
                            "medication.confirm_dose_recorded_detail_with_note",
                            locale=locale,
                            name=confirmed.medication_name,
                            dose=dose_disp,
                            note=note,
                        )
                    )
                return ToolResult(
                    reply=t(
                        "medication.confirm_dose_recorded_detail",
                        locale=locale,
                        name=confirmed.medication_name,
                        dose=dose_disp,
                    )
                )
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
                options = _format_disambiguation_options(
                    recent_taken, tz_name=tz_name, locale=locale
                )
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
                    reply=t("medication.confirm_dose_note_appended", locale=locale, note=note)
                )

        return ToolResult(reply=t("medication.confirm_dose_none", locale=locale))


def _format_disambiguation_options(
    candidates: list[DoseEventPendingCandidate], *, tz_name: str, locale: str
) -> str:
    un = t("medication.unspecified", locale=locale)
    tz = ZoneInfo(tz_name)
    lines: list[str] = []
    for idx, c in enumerate(candidates, start=1):
        ts = c.scheduled_at if c.scheduled_at.tzinfo else c.scheduled_at.replace(tzinfo=UTC)
        local_ts = ts.astimezone(tz)
        stamp = local_ts.strftime("%Y-%m-%d %H:%M")
        dose_disp = dose_or_schedule_display(c.dosage, unspecified_label=un)
        lines.append(f"{idx}) {c.medication_name} ({dose_disp}) - {stamp}")
    return "\n".join(lines)
