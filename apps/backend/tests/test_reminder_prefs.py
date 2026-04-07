"""Tests for LLM-driven reminder metadata → dose_event instants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from medbuddy.reminders.dose_schedule import iter_scheduled_dose_times_utc
from medbuddy.reminders.prefs import (
    ReminderPrefs,
    iter_dose_instants_for_medication,
    reminder_prefs_from_metadata,
)


def test_one_off_minutes_only_produces_single_instant() -> None:
    now = datetime(2026, 4, 7, 10, 0, tzinfo=UTC)
    prefs = ReminderPrefs(
        first_reminder_in_minutes=5,
        materialize_daily=False,
        needs_horizon_confirmation=False,
    )
    out = iter_dose_instants_for_medication(
        prefs,
        tz_name="Asia/Taipei",
        default_local_hhmm="09:00",
        default_horizon_days=14,
        now_utc=now,
    )
    assert len(out) == 1
    assert out[0] == now + timedelta(minutes=5)


def test_default_prefs_matches_plain_daily_iterator() -> None:
    now = datetime(2026, 4, 7, 10, 0, tzinfo=UTC)
    prefs = ReminderPrefs()
    a = iter_dose_instants_for_medication(
        prefs,
        tz_name="Asia/Taipei",
        default_local_hhmm="09:00",
        default_horizon_days=14,
        now_utc=now,
    )
    b = iter_scheduled_dose_times_utc(
        tz_name="Asia/Taipei",
        local_hhmm="09:00",
        horizon_days=14,
        now_utc=now,
    )
    assert a == b


def test_needs_horizon_confirmation_skips_daily_and_first() -> None:
    now = datetime(2026, 4, 7, 10, 0, tzinfo=UTC)
    prefs = ReminderPrefs(needs_horizon_confirmation=True, materialize_daily=False)
    out = iter_dose_instants_for_medication(
        prefs,
        tz_name="Asia/Taipei",
        default_local_hhmm="09:00",
        default_horizon_days=14,
        now_utc=now,
    )
    assert out == []


def test_needs_horizon_confirmation_with_first_keeps_first_only() -> None:
    now = datetime(2026, 4, 7, 10, 0, tzinfo=UTC)
    prefs = ReminderPrefs(
        first_reminder_in_minutes=3,
        materialize_daily=True,
        needs_horizon_confirmation=True,
    )
    out = iter_dose_instants_for_medication(
        prefs,
        tz_name="Asia/Taipei",
        default_local_hhmm="09:00",
        default_horizon_days=14,
        now_utc=now,
    )
    assert len(out) == 1
    assert out[0] == now + timedelta(minutes=3)


def test_reminder_prefs_from_metadata_reads_nested_reminder() -> None:
    p = reminder_prefs_from_metadata(
        {"reminder": {"first_reminder_in_minutes": 10, "materialize_daily": False}}
    )
    assert p.first_reminder_in_minutes == 10
    assert p.materialize_daily is False


@pytest.mark.parametrize(
    ("raw", "expected_hhmm"),
    [
        ({"reminder": {"daily_local_hhmm": "bad"}}, None),
        ({"reminder": {"daily_local_hhmm": "08:30"}}, "08:30"),
    ],
)
def test_reminder_prefs_invalid_hhmm_dropped(raw: dict, expected_hhmm: str | None) -> None:
    p = reminder_prefs_from_metadata(raw)
    assert p.daily_local_hhmm == expected_hhmm


def test_three_local_times_per_day_times_horizon_yields_product() -> None:
    """Breakfast/lunch/dinner × N days → 3×N dose_events (when all slots are after now)."""
    now = datetime(2026, 4, 6, 23, 0, tzinfo=UTC)  # Asia/Taipei 2026-04-07 07:00
    prefs = ReminderPrefs(
        horizon_days=3,
        daily_local_hhmm_list=("08:00", "12:30", "18:30"),
    )
    out = iter_dose_instants_for_medication(
        prefs,
        tz_name="Asia/Taipei",
        default_local_hhmm="09:00",
        default_horizon_days=14,
        now_utc=now,
    )
    assert len(out) == 9


def test_reminder_prefs_from_metadata_daily_list() -> None:
    p = reminder_prefs_from_metadata(
        {
            "reminder": {
                "daily_local_hhmm_list": ["18:30", "08:00", "12:30"],
                "horizon_days": 2,
            }
        }
    )
    assert p.daily_local_hhmm_list == ("08:00", "12:30", "18:30")
    assert p.horizon_days == 2
