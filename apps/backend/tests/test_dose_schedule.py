"""Unit tests for prototype daily dose instant generation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from medbuddy.reminders.dose_schedule import iter_scheduled_dose_times_utc, parse_hhmm


def test_parse_hhmm() -> None:
    assert parse_hhmm("9:00") == (9, 0)
    assert parse_hhmm("09:30") == (9, 30)


def test_parse_hhmm_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid"):
        parse_hhmm("25:00")
    with pytest.raises(ValueError, match="Invalid"):
        parse_hhmm("noon")


def test_iter_scheduled_future_only() -> None:
    now = datetime(2026, 4, 7, 15, 0, tzinfo=UTC)
    instants = iter_scheduled_dose_times_utc(
        tz_name="Asia/Taipei",
        local_hhmm="09:00",
        horizon_days=3,
        now_utc=now,
    )
    # Apr 7 15:00 UTC is late evening Taipei; same-calendar-day 09:00 is skipped → 2 future slots.
    assert len(instants) == 2
    for at in instants:
        assert at > now
        assert at.tzinfo == UTC
