import os

import pytest

# ``medbuddy.reminders.worker`` resolves ``WorkerSettings.redis_settings`` at import time.
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/15")

from medbuddy.config import Settings
from medbuddy.container import build_app_services
from tests.helpers import make_mock_settings


@pytest.fixture
def mock_settings() -> Settings:
    return make_mock_settings()


@pytest.fixture
def app_services(mock_settings: Settings):
    return build_app_services(mock_settings)
