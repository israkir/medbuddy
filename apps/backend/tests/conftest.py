import pytest

from medbuddy.config import Settings, load_settings
from medbuddy.container import build_app_services


def make_mock_settings(**overrides) -> Settings:
    """Construct a Settings with all mock defaults for tests."""
    base = {
        "MEDBUDDY_INTEGRATION": "mock",
        "MEDBUDDY_LOCALE": "zh-TW",
        "LOG_LEVEL": "INFO",
        "LINE_CHANNEL_SECRET": "testsecret",
        "PUBLIC_BASE_URL": "http://test",
        "MEDBUDDY_PROFILE_COMPLETION_NUDGE_EVERY_N_USER_TURNS": "0",
    }
    base.update(overrides)
    return load_settings(base)


@pytest.fixture
def mock_settings() -> Settings:
    return make_mock_settings()


@pytest.fixture
def app_services(mock_settings: Settings):
    return build_app_services(mock_settings)
