from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from medbuddy.container import build_app_services
from medbuddy.main import app


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
async def test_app_me_requires_app_user_id(mock_settings):
    mock_settings.mock_external_services = True
    mock_settings.mobile_bearer_token = ""
    app.state.services = build_app_services(mock_settings)
    with patch("medbuddy.channels.mobile.auth.get_settings", return_value=mock_settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/v1/app/me")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_app_user_id"


@pytest.mark.asyncio
async def test_app_me_ok(mock_settings):
    mock_settings.mock_external_services = True
    mock_settings.mobile_bearer_token = ""
    app.state.services = build_app_services(mock_settings)
    with patch("medbuddy.channels.mobile.auth.get_settings", return_value=mock_settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/v1/app/me", headers=_mobile_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["app_user_id"] == "app-test-user"
    assert data["consent_accepted"] is False


@pytest.mark.asyncio
async def test_app_bearer_rejects_wrong_token(mock_settings):
    mock_settings.mock_external_services = True
    mock_settings.mobile_bearer_token = "good"
    app.state.services = build_app_services(mock_settings)
    with patch("medbuddy.channels.mobile.auth.get_settings", return_value=mock_settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get(
                "/v1/app/me",
                headers=_mobile_headers(bearer="bad"),
            )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_app_messages_requires_consent_then_replies(mock_settings):
    mock_settings.mock_external_services = True
    mock_settings.mobile_bearer_token = ""
    app.state.services = build_app_services(mock_settings)
    with patch("medbuddy.channels.mobile.auth.get_settings", return_value=mock_settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r0 = await client.post(
                "/v1/app/messages",
                json={"text": "hello"},
                headers=_mobile_headers(user="u-consent-flow"),
            )
            assert r0.status_code == 403
            assert r0.json()["detail"]["code"] == "consent_required"

            r1 = await client.post(
                "/v1/app/consent",
                json={"accepted": True},
                headers=_mobile_headers(user="u-consent-flow"),
            )
            assert r1.status_code == 204

            r2 = await client.post(
                "/v1/app/messages",
                json={"text": "hello"},
                headers=_mobile_headers(user="u-consent-flow"),
            )
            assert r2.status_code == 200
            assert "reply" in r2.json()


@pytest.mark.asyncio
async def test_app_messages_validation_empty_text(mock_settings):
    mock_settings.mock_external_services = True
    mock_settings.mobile_bearer_token = ""
    app.state.services = build_app_services(mock_settings)
    with patch("medbuddy.channels.mobile.auth.get_settings", return_value=mock_settings):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/v1/app/consent",
                json={"accepted": True},
                headers=_mobile_headers(user="u-val"),
            )
            r = await client.post(
                "/v1/app/messages",
                json={"text": ""},
                headers=_mobile_headers(user="u-val"),
            )
    assert r.status_code == 422
