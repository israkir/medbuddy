"""Tool: look up past health-issue events by date range or keyword."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.application.health_events.health_issue_events_format import (
    format_health_issue_events_for_summary,
)
from medbuddy.core.i18n import t
from medbuddy.services import AppServices


class LookupHealthHistoryTool:
    name = "lookup_health_history"
    description = (
        "Fetch past health events and symptom notes for the user. "
        "Use when the user asks 'when did I last…', 'have I had…', or wants to recall a past symptom."
    )

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        locale: str,
        since_days: int | None = None,
        **_: Any,
    ) -> ToolResult:
        limit = 30
        events = await svc.users.list_recent_health_issue_events(user_key, limit=limit)
        if since_days is not None and since_days > 0:
            cutoff = datetime.now(UTC) - timedelta(days=since_days)
            events = [e for e in events if e.created_at >= cutoff]
        if not events:
            return ToolResult(reply=t("health_history.empty", locale=locale))
        body = format_health_issue_events_for_summary(events)
        return ToolResult(reply=body)
