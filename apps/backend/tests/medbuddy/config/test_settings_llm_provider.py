"""LLM_PROVIDER setting — defaults, accepted values, and error on invalid."""

from __future__ import annotations

import pytest

from medbuddy.config import LlmProvider, get_settings, load_settings
from medbuddy.core.errors import ConfigError


@pytest.fixture(autouse=True)
def _clear_settings_lru_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_llm_provider_defaults_to_gemini() -> None:
    s = load_settings({})
    assert s.llm_provider == LlmProvider.GEMINI


def test_llm_provider_openai_is_accepted() -> None:
    s = load_settings({"LLM_PROVIDER": "openai"})
    assert s.llm_provider == LlmProvider.OPENAI


def test_invalid_llm_provider_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="LLM_PROVIDER"):
        load_settings({"LLM_PROVIDER": "cohere"})
