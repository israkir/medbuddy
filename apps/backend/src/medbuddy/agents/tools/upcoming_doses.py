"""Answer questions about time-ordered scheduled doses (materialized dose_events)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.core.i18n import t
from medbuddy.core.timezone import effective_user_timezone
from medbuddy.llm.medication_draft_build import is_placeholder_field
from medbuddy.reminders.prefs import reminder_prefs_from_metadata
from medbuddy.reminders.upcoming_display import (
    format_upcoming_doses_user_reply,
    upcoming_schedule_window_utc,
)
from medbuddy.services import AppServices


class ListUpcomingDosesTool:
    name = "upcoming_doses"
    description = "List pending scheduled doses from the reminder calendar, soonest first."

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_row: dict[str, Any],
        locale: str,
        **_: Any,
    ) -> ToolResult:
        tz_name = effective_user_timezone(
            str(user_row.get("timezone")) if user_row.get("timezone") else None
        )
        now = datetime.now(UTC)
        await svc.users.sync_upcoming_dose_events(user_key)
        start_utc, end_utc = upcoming_schedule_window_utc(tz_name, now, horizon_days=7)
        rows = await svc.users.list_upcoming_dose_events(
            user_key,
            from_utc=start_utc,
            until_utc_exclusive=end_utc,
            max_items=96,
        )

        # Split out dose_events whose medication has a placeholder name — those are incomplete
        # records that should never be presented as real scheduled doses.
        good_rows = [r for r in rows if not is_placeholder_field(r.medication_name)]
        incomplete_names = [
            r.medication_name for r in rows if is_placeholder_field(r.medication_name)
        ]

        reply = format_upcoming_doses_user_reply(
            good_rows, tz_name=tz_name, now_utc=now, locale=locale
        )

        # Append notice for medications with placeholder names
        if incomplete_names:
            unique_incomplete = list(dict.fromkeys(incomplete_names))
            names_str = (
                "、".join(unique_incomplete)
                if locale.startswith("zh")
                else ", ".join(unique_incomplete)
            )
            reply += "\n\n" + t(
                "medication.incomplete_setup_notice", locale=locale, names=names_str
            )

        # Append notice for medications awaiting horizon confirmation
        meds = await svc.users.list_medications(user_key)
        pending_horizon = [
            m
            for m in meds
            if reminder_prefs_from_metadata(m.raw_metadata).needs_horizon_confirmation
        ]
        if pending_horizon:
            names_str = (
                "、".join(m.name for m in pending_horizon)
                if locale.startswith("zh")
                else ", ".join(m.name for m in pending_horizon)
            )
            reply += "\n\n" + t("medication.pending_horizon_notice", locale=locale, names=names_str)

        return ToolResult(reply=reply)
