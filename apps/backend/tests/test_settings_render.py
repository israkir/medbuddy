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


def test_real_integration_mode() -> None:
    s = load_settings({"MEDBUDDY_INTEGRATION": "real"})
    assert s.integration_mode == IntegrationMode.REAL
    assert s.is_mock is False


def test_integration_mode_aliases() -> None:
    for alias in ("local", "dev"):
        s = load_settings({"MEDBUDDY_INTEGRATION": alias})
        assert s.is_mock is True
    for alias in ("live", "production"):
        s = load_settings({"MEDBUDDY_INTEGRATION": alias})
        assert s.is_mock is False


def test_legacy_mock_external_services_true_maps_to_mock_mode() -> None:
    s = load_settings({"MOCK_EXTERNAL_SERVICES": "true"})
    assert s.integration_mode == IntegrationMode.MOCK
    assert s.is_mock is True


def test_legacy_mock_external_services_false_maps_to_real_mode() -> None:
    s = load_settings({"MOCK_EXTERNAL_SERVICES": "false"})
    assert s.integration_mode == IntegrationMode.REAL
    assert s.is_mock is False


def test_invalid_integration_mode_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="MEDBUDDY_INTEGRATION"):
        load_settings({"MEDBUDDY_INTEGRATION": "staging"})


def test_invalid_legacy_mock_external_services_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="MOCK_EXTERNAL_SERVICES"):
        load_settings({"MOCK_EXTERNAL_SERVICES": "maybe"})


def test_debug_defaults_to_false() -> None:
    s = load_settings({})
    assert s.debug is False


def test_debug_true_from_env() -> None:
    s = load_settings({"DEBUG": "true"})
    assert s.debug is True
