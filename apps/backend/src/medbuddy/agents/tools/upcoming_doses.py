"""Answer questions about time-ordered scheduled doses (materialized dose_events)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.engine.types import AppServices
from medbuddy.reminders.upcoming_display import (
    format_upcoming_doses_user_reply,
    upcoming_schedule_window_utc,
)
from medbuddy.user_timezone import effective_user_timezone


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
        reply = format_upcoming_doses_user_reply(rows, tz_name=tz_name, now_utc=now, locale=locale)
        return ToolResult(reply=reply)
