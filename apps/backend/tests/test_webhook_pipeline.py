import base64
import hashlib
import hmac
import json
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from medbuddy.channels.line.orchestrator import handle_line_event
from medbuddy.main import app
from medbuddy.engine.types import AppServices


def _line_webhook_event(**fields: Any) -> dict[str, Any]:
    """Minimal valid shell for ``line-bot-sdk`` webhook ``Event`` models (tests only)."""
    base = {
        "timestamp": 1_704_000_000_000,
        "mode": "active",
        "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "deliveryContext": {"isRedelivery": False},
    }
    base.update(fields)
    return base


@pytest.mark.asyncio
async def test_webhook_signed_batch_returns_ok(mock_settings):
    """HTTP layer + signature validation; event parsing varies by Python/SDK."""
    mock_settings.line_channel_secret = "s3cret"
    app.state.services = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)

    body = {
        "events": [
            _line_webhook_event(
                type="message",
                replyToken="rtoken",
                source={"userId": "Uabc", "type": "user"},
                message={"id": "m1", "type": "text", "text": "你好"},
            ),
        ]
    }
    raw = json.dumps(body).encode("utf-8")
    mac = hmac.new(b"s3cret", raw, hashlib.sha256).digest()
    sig = base64.b64encode(mac).decode("ascii")

    transport = ASGITransport(app=app)
    with patch("medbuddy.channels.line.routes.get_settings", return_value=mock_settings):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/v1/line/webhook",
                content=raw,
                headers={"X-Line-Signature": sig},
            )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_orchestrator_text_message_replies(mock_settings):
    """Drive orchestrator with a full event dict (same shape ``handle_line_event`` expects)."""
    mock_settings.mock_external_services = True
    svc: AppServices = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)

    await handle_line_event(
        {
            "type": "message",
            "replyToken": "rtoken",
            "source": {"userId": "Uabc", "type": "user"},
            "message": {"id": "m1", "type": "text", "text": "你好"},
            "timestamp": 1_704_000_000_000,
            "mode": "active",
            "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "deliveryContext": {"isRedelivery": False},
        },
        svc,
    )
    line = svc.line
    assert hasattr(line, "replies")
    assert len(line.replies) >= 1


@pytest.mark.asyncio
async def test_follow_does_not_auto_reply(mock_settings):
    mock_settings.line_channel_secret = ""
    app.state.services = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)

    body = {
        "events": [
            _line_webhook_event(
                type="follow",
                replyToken="rt",
                source={"userId": "Ux", "type": "user"},
                follow={"isUnblocked": True},
            ),
        ]
    }
    raw = json.dumps(body).encode("utf-8")
    transport = ASGITransport(app=app)
    with patch("medbuddy.channels.line.routes.get_settings", return_value=mock_settings):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/v1/line/webhook", content=raw)
    assert r.status_code == 200
    svc: AppServices = app.state.services
    assert svc.line.replies == []  # type: ignore[attr-defined]
