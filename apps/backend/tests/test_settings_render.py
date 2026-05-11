"""Settings — load_settings() behavior: integration mode, debug flag."""

from __future__ import annotations

import pytest

from medbuddy.config import IntegrationMode, load_settings, get_settings
from medbuddy.core.errors import ConfigError


@pytest.fixture(autouse=True)
def _clear_settings_lru_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_mock_integration_mode() -> None:
    s = load_settings({"MEDBUDDY_INTEGRATION": "mock"})
    assert s.integration_mode == IntegrationMode.MOCK
    assert s.is_mock is True


def _real_secrets() -> dict[str, str]:
    """Minimal env dict satisfying fail-closed production-mode validation."""
    return {
        "MEDBUDDY_MOBILE_BEARER_TOKEN": "tok",
        "LINE_CHANNEL_SECRET": "sec",
        "LINE_CHANNEL_ACCESS_TOKEN": "acc",
        "SUPABASE_URL": "https://x.supabase.co",
        "SUPABASE_SERVICE_KEY": "sb_secret_01234567890123456789012_abcd1234",
        "MEDBUDDY_CRON_SECRET": "cron",
        "LLM_PROVIDER": "gemini",
        "GEMINI_API_KEY": "gkey",
        "MEDBUDDY_LINE_VOICE_REPLIES": "off",
    }


def test_production_integration_mode() -> None:
    s = load_settings({"MEDBUDDY_INTEGRATION": "production", **_real_secrets()})
    assert s.integration_mode == IntegrationMode.PRODUCTION
    assert s.is_mock is False


def test_production_mode_missing_secrets_raises_at_startup() -> None:
    with pytest.raises(ConfigError, match="Missing required secrets"):
        load_settings({"MEDBUDDY_INTEGRATION": "production"})


def test_empty_medbuddy_integration_defaults_to_mock() -> None:
    s = load_settings({})
    assert s.integration_mode == IntegrationMode.MOCK
    assert s.is_mock is True


def test_mock_external_services_env_is_ignored() -> None:
    """MOCK_EXTERNAL_SERVICES is no longer read; integration mode is MEDBUDDY_INTEGRATION only."""
    s = load_settings({"MOCK_EXTERNAL_SERVICES": "false"})
    assert s.integration_mode == IntegrationMode.MOCK


def test_invalid_integration_mode_raises_config_error() -> None:
    for bad in ("staging", "local", "dev", "default"):
        with pytest.raises(ConfigError, match="MEDBUDDY_INTEGRATION"):
            load_settings({"MEDBUDDY_INTEGRATION": bad})


def test_debug_defaults_to_false() -> None:
    s = load_settings({})
    assert s.debug is False


def test_debug_true_from_env() -> None:
    s = load_settings({"DEBUG": "true"})
    assert s.debug is True
