"""load_settings() raises ConfigError on invalid env-var values."""

from __future__ import annotations

import pytest

from medbuddy.config import load_settings
from medbuddy.core.errors import ConfigError


def test_invalid_locale_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="MEDBUDDY_LOCALE"):
        load_settings({"MEDBUDDY_LOCALE": "fr"})


def test_invalid_integration_mode_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="MEDBUDDY_INTEGRATION"):
        load_settings({"MEDBUDDY_INTEGRATION": "staging"})


def test_invalid_llm_provider_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="LLM_PROVIDER"):
        load_settings({"LLM_PROVIDER": "anthropic"})


def test_invalid_debug_bool_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="DEBUG"):
        load_settings({"DEBUG": "maybe"})


def test_dose_clarification_ttl_below_min_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="MEDBUDDY_DOSE_CLARIFICATION_TTL_SECONDS"):
        load_settings({"MEDBUDDY_DOSE_CLARIFICATION_TTL_SECONDS": "59"})


def test_valid_minimal_env_produces_mock_settings() -> None:
    s = load_settings({})
    assert s.is_mock is True
    assert s.locale == "zh-TW"
    assert s.log_level == "INFO"
    assert s.debug is False
