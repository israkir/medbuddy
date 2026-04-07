"""Shared routes: internal-media wiring via ``AppServices.internal_media``."""

from __future__ import annotations

from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient

from medbuddy.container import build_app_services
from medbuddy.integrations.local_public_storage import LocalPublicObjectStorage
from medbuddy.main import app


@pytest.mark.asyncio
async def test_internal_media_404_when_not_wired(mock_settings) -> None:
    mock_settings.mock_external_services = True
    app.state.services = build_app_services(mock_settings)
    assert app.state.services.internal_media is None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/internal-media/foo")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_internal_media_serves_blob_when_wired(mock_settings) -> None:
    mock_settings.mock_external_services = True
    base = build_app_services(mock_settings)
    storage = LocalPublicObjectStorage(public_base_url="http://test")
    app.state.services = replace(base, internal_media=storage)

    url = await storage.upload_temp_audio(
        data=b"hello-audio",
        content_type="audio/mpeg",
        suffix=".mp3",
    )
    file_id = url.rsplit("/internal-media/", 1)[-1]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/internal-media/{file_id}")

    assert r.status_code == 200
    assert r.content == b"hello-audio"
