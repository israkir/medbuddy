"""MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES (comma-separated env)."""

import pytest

from medbuddy.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_lru_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_comma_separated_env_parses_to_int_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES", "15,30,60")
    s = Settings()
    assert s.reminder_nudge_intervals_minutes == [15, 30, 60]


def test_json_array_env_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES", "[10, 20]")
    s = Settings()
    assert s.reminder_nudge_intervals_minutes == [10, 20]


def test_get_settings_with_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES", "1,2")
    assert get_settings().reminder_nudge_intervals_minutes == [1, 2]
