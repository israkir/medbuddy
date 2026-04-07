"""Build UTC dose instants from a user timezone and a daily local clock time (prototype)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta

from zoneinfo import ZoneInfo


def parse_hhmm(value: str) -> tuple[int, int]:
    s = value.strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if not m:
        msg = f"Invalid time (expected HH:MM): {value!r}"
        raise ValueError(msg)
    h, mn = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mn <= 59):
        msg = f"Invalid clock time: {value!r}"
        raise ValueError(msg)
    return h, mn


def iter_scheduled_dose_times_utc(
    *,
    tz_name: str,
    local_hhmm: str,
    horizon_days: int,
    now_utc: datetime | None = None,
) -> list[datetime]:
    """One local time per future dose day in ``tz_name``.

    Returns the next ``horizon_days`` future instants (strictly after ``now_utc``), so
    explicit requests like "remind me for 3 days" produce 3 upcoming doses even when
    today's scheduled time has already passed.
    """
    if horizon_days < 1:
        return []
    now = now_utc or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    hh, mm = parse_hhmm(local_hhmm)
    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    base_date: date = local_now.date()
    out: list[datetime] = []
    # Scan a small extra local-date window so we can still collect N future instants
    # when today's slot is already in the past.
    for i in range(horizon_days + 2):
        d = base_date + timedelta(days=i)
        dt_local = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
        dt_utc = dt_local.astimezone(UTC)
        if dt_utc > now:
            out.append(dt_utc)
            if len(out) >= horizon_days:
                break
    return out
