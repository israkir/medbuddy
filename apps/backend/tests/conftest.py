import pytest

from medbuddy.config import Settings
from medbuddy.container import build_app_services
from tests.helpers import make_mock_settings


@pytest.fixture
def mock_settings() -> Settings:
    return make_mock_settings()


@pytest.fixture
def app_services(mock_settings: Settings):
    return build_app_services(mock_settings)
