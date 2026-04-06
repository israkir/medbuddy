"""Settings behavior on Render (RENDER=true)."""

import pytest

from medbuddy.config import Settings


def test_without_render_mock_env_can_enable_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("MOCK_EXTERNAL_SERVICES", "true")
    monkeypatch.delenv("MEDBUDDY_INTEGRATION", raising=False)
    s = Settings()
    assert s.mock_external_services is True


def test_render_overrides_mocks_even_when_env_requests_mocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("MOCK_EXTERNAL_SERVICES", "true")
    monkeypatch.delenv("MEDBUDDY_INTEGRATION", raising=False)
    s = Settings()
    assert s.mock_external_services is False
    assert s.debug is False


def test_render_overrides_medbuddy_integration_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("MEDBUDDY_INTEGRATION", "mock")
    monkeypatch.setenv("MOCK_EXTERNAL_SERVICES", "true")
    s = Settings()
    assert s.medbuddy_integration == "real"
    assert s.mock_external_services is False


def test_debug_alias_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("MOCK_EXTERNAL_SERVICES", "true")
    s = Settings()
    assert s.debug is True
