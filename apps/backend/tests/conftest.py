import pytest

from medbuddy.config import Settings
from medbuddy.container import build_app_services


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        mock_external_services=True,
        line_channel_secret="testsecret",
        public_base_url="http://test",
    )


@pytest.fixture
def app_services(mock_settings: Settings):
    return build_app_services(mock_settings)
