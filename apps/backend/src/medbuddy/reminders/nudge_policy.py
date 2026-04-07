"""Rules for whether a follow-up dose reminder nudge may still be sent."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def nudge_window_allows(scheduled_at: datetime, user_tz: str, *, now_utc: datetime) -> bool:
    """Allow nudges until the end of the local calendar day of ``scheduled_at`` (in ``user_tz``)."""
    tz = ZoneInfo(user_tz)
    local_sched = scheduled_at.astimezone(tz)
    end_of_day = local_sched.replace(hour=23, minute=59, second=59, microsecond=999999)
    end_utc = end_of_day.astimezone(UTC)
    return now_utc <= end_utc
