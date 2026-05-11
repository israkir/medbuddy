"""MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES (comma-separated env)."""

from __future__ import annotations

import pytest

from medbuddy.config import get_settings, load_settings


@pytest.fixture(autouse=True)
def _clear_settings_lru_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_comma_separated_env_parses_to_int_tuple() -> None:
    s = load_settings({"MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES": "15,30,60"})
    assert s.reminder_nudge_intervals_minutes == (15, 30, 60)


def test_empty_env_gives_empty_tuple() -> None:
    s = load_settings({})
    assert s.reminder_nudge_intervals_minutes == ()


def test_get_settings_with_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES", "1,2")
    assert get_settings().reminder_nudge_intervals_minutes == (1, 2)
