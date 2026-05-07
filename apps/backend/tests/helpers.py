"""Shared test helpers."""

from __future__ import annotations

from medbuddy.config import Settings, load_settings


def make_mock_settings(**overrides: str) -> Settings:
    """Construct a Settings with mock defaults. Pass env-var name overrides as kwargs."""
    base: dict[str, str] = {
        "MEDBUDDY_INTEGRATION": "mock",
        "MEDBUDDY_LOCALE": "zh-TW",
        "LOG_LEVEL": "INFO",
        "LINE_CHANNEL_SECRET": "testsecret",
        "PUBLIC_BASE_URL": "http://test",
    }
    base.update(overrides)
    return load_settings(base)
