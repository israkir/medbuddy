"""Build de-identified patient context for external LLMs, including upcoming dose schedule.

``dose_events`` rows are materialized by ``sync_and_enqueue_reminders`` on medication/reminder
mutations. Callers must not run ``sync_upcoming_dose_events`` here by default: that replaces
future rows with new UUIDs and would orphan deferred ``send_reminder_for_dose`` jobs in Redis.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from medbuddy.services import AppServices
from medbuddy.models.domain import MedicationRecord
from medbuddy.llm.prompts.persona import build_patient_context_for_llm
from medbuddy.reminders.upcoming_display import (
    format_upcoming_doses_for_llm,
    upcoming_schedule_window_utc,
)
from medbuddy.core.timezone import effective_user_timezone
from medbuddy.application.health_events.health_issue_events_format import (
    format_health_issue_events_for_summary,
)


async def patient_context_for_llm(
    svc: AppServices,
    user_key: str,
    user_row: dict[str, Any],
    medications: list[MedicationRecord],
    *,
    locale: str,
    sync_dose_events_first: bool = False,
    include_health_notes: bool = False,
    include_recent_health_events: bool = True,
) -> str:
    tz_name = effective_user_timezone(
        str(user_row.get("timezone")) if user_row.get("timezone") else None
    )
    now = datetime.now(UTC)
    if sync_dose_events_first:
        await svc.users.sync_upcoming_dose_events(user_key)
    start_utc, end_utc = upcoming_schedule_window_utc(tz_name, now, horizon_days=7)
    upcoming = await svc.users.list_upcoming_dose_events(
        user_key,
        from_utc=start_utc,
        until_utc_exclusive=end_utc,
        max_items=96,
    )
    block = format_upcoming_doses_for_llm(upcoming, tz_name=tz_name, now_utc=now, locale=locale)
    health_conditions = await svc.users.list_health_conditions(user_key, active_only=True)

    recent_health_notes: str | None = None
    if include_recent_health_events:
        events = await svc.users.list_recent_health_issue_events(user_key, limit=12)
        if events:
            from medbuddy.core.i18n import t

            header = t("prompts.recent_health_notes_header", locale=locale)
            body = format_health_issue_events_for_summary(events)
            recent_health_notes = f"{header}\n{body}"

    return build_patient_context_for_llm(
        user_row,
        medications,
        locale=locale,
        upcoming_doses_context=block,
        include_health_notes=include_health_notes,
        health_conditions=health_conditions,
        recent_health_notes=recent_health_notes,
    )
