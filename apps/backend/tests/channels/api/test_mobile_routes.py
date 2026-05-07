from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from medbuddy.container import build_app_services
from medbuddy.main import app
from tests.helpers import make_mock_settings


def _mobile_headers(*, user: str = "app-test-user", bearer: str | None = None) -> dict[str, str]:
    h = {"X-App-User-Id": user}
    if bearer is not None:
        h["Authorization"] = f"Bearer {bearer}"
    return h


@pytest.mark.asyncio
async def test_app_channel_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/v1/app/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "channel": "standalone"}


@pytest.mark.asyncio
async def test_app_channel_info_includes_version_key():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/v1/app/info")
    assert r.status_code == 200
    data = r.json()
    assert data["channel"] == "standalone"
    assert "api_version" in data


@pytest.mark.asyncio
async def test_app_me_requires_app_user_id():
    ms = make_mock_settings()
    app.state.services = build_app_services(ms)
    with patch("medbuddy.channels.api.auth.get_settings", return_value=ms):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/v1/app/me")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_app_user_id"


@pytest.mark.asyncio
async def test_app_me_ok():
    ms = make_mock_settings()
    app.state.services = build_app_services(ms)
    with patch("medbuddy.channels.api.auth.get_settings", return_value=ms):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/v1/app/me", headers=_mobile_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["app_user_id"] == "app-test-user"
    assert data["onboarding_completed_at"] is None
    assert data["preferred_name"] is None
    assert data["timezone"] == "Asia/Taipei"
    assert data["locale"] == "zh-TW"


@pytest.mark.asyncio
async def test_app_bearer_rejects_wrong_token():
    ms = make_mock_settings(MEDBUDDY_MOBILE_BEARER_TOKEN="good")
    app.state.services = build_app_services(ms)
    with patch("medbuddy.channels.api.auth.get_settings", return_value=ms):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/v1/app/me", headers=_mobile_headers(bearer="bad"))
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_app_messages_ok():
    ms = make_mock_settings()
    app.state.services = build_app_services(ms)
    with patch("medbuddy.channels.api.auth.get_settings", return_value=ms):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/v1/app/messages",
                json={"text": "hello"},
                headers=_mobile_headers(user="u-msg-flow"),
            )
            assert r.status_code == 200
            assert "reply" in r.json()


@pytest.mark.asyncio
async def test_app_messages_voice_ok():
    ms = make_mock_settings()
    app.state.services = build_app_services(ms)
    with patch("medbuddy.channels.api.auth.get_settings", return_value=ms):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/v1/app/messages/voice",
                headers=_mobile_headers(user="u-voice-1"),
                files={"file": ("clip.m4a", b"fake-m4a-audio", "audio/mp4")},
            )
            assert r.status_code == 200
            data = r.json()
            assert "reply" in data
            assert "transcript" in data
            assert data["transcript"]


@pytest.mark.asyncio
async def test_app_messages_voice_empty_file():
    ms = make_mock_settings()
    app.state.services = build_app_services(ms)
    with patch("medbuddy.channels.api.auth.get_settings", return_value=ms):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/v1/app/messages/voice",
                headers=_mobile_headers(user="u-voice-empty"),
                files={"file": ("empty.m4a", b"", "audio/mp4")},
            )
            assert r.status_code == 422


@pytest.mark.asyncio
async def test_app_messages_validation_empty_text():
    ms = make_mock_settings()
    app.state.services = build_app_services(ms)
    with patch("medbuddy.channels.api.auth.get_settings", return_value=ms):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/v1/app/messages",
                json={"text": ""},
                headers=_mobile_headers(user="u-val"),
            )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_app_onboarding_saves_profile():
    ms = make_mock_settings()
    app.state.services = build_app_services(ms)
    with patch("medbuddy.channels.api.auth.get_settings", return_value=ms):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/v1/app/onboarding",
                json={
                    "preferred_name": "阿春",
                    "age_years": 68,
                    "gender": "female",
                    "emergency_contact": "女兒 0922",
                    "health_notes": "對青黴素過敏",
                    "timezone": "Asia/Taipei",
                    "locale": "zh-TW",
                },
                headers=_mobile_headers(user="onboarding-user-1"),
            )
    assert r.status_code == 200
    data = r.json()
    assert data["preferred_name"] == "阿春"
    assert data["age_years"] == 68
    assert data["gender"] == "female"
    assert data["onboarding_completed_at"] is not None
    assert data["timezone"] == "Asia/Taipei"
    assert data["locale"] == "zh-TW"

    with patch("medbuddy.channels.api.auth.get_settings", return_value=ms):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r2 = await client.get("/v1/app/me", headers=_mobile_headers(user="onboarding-user-1"))
    assert r2.status_code == 200
    assert r2.json()["preferred_name"] == "阿春"
