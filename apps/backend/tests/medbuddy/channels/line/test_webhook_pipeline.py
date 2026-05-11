import base64
import hashlib
import hmac
import json
from typing import Any
from unittest.mock import patch

import pytest
import httpx
from httpx import ASGITransport, AsyncClient

from medbuddy.channels.line.orchestrator import handle_line_event
from medbuddy.main import app
from medbuddy.services import AppServices
from tests.helpers import make_mock_settings


class _FailingStt:
    async def transcribe_m4a(self, audio: bytes, *, language_code: str | None = None) -> str:
        raise httpx.HTTPError("stt unavailable")


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
async def test_webhook_signed_batch_returns_ok():
    """HTTP layer + signature validation; event parsing varies by Python/SDK."""
    ms = make_mock_settings(LINE_CHANNEL_SECRET="s3cret")
    app.state.services = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(ms)

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
    with patch("medbuddy.channels.line.routes.get_settings", return_value=ms):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/v1/line/webhook",
                content=raw,
                headers={"X-Line-Signature": sig},
            )
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_orchestrator_text_message_runs_assistant(mock_settings):
    """Text messages go straight to the assistant (mock LINE batch reply)."""
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
    assert line.loading_indicators == [{"user_id": "Uabc", "seconds": 30}]  # type: ignore[attr-defined]
    assert len(line.replies) == 1
    assert line.replies[0]["type"] == "batch"  # type: ignore[index]
    msgs = line.replies[0]["messages"]  # type: ignore[index]
    assert len(msgs) == 1
    assert msgs[0]["type"] == "text"


@pytest.mark.asyncio
async def test_orchestrator_audio_message_replies_text_after_stt(mock_settings):
    """Voice inbound: STT transcript → same assistant path → text + m4a (default audio_inbound)."""
    svc: AppServices = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)
    svc.line.seed_voice_message("m-audio", b"fake-m4a")  # type: ignore[attr-defined]

    await handle_line_event(
        {
            "type": "message",
            "replyToken": "rtoken",
            "source": {"userId": "Uabc", "type": "user"},
            "message": {"id": "m-audio", "type": "audio"},
            "timestamp": 1_704_000_000_000,
            "mode": "active",
            "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "deliveryContext": {"isRedelivery": False},
        },
        svc,
    )
    line = svc.line
    assert line.loading_indicators == [{"user_id": "Uabc", "seconds": 30}]  # type: ignore[attr-defined]
    assert len(line.replies) == 1
    msgs = line.replies[0]["messages"]  # type: ignore[index]
    assert len(msgs) == 2
    assert msgs[0]["type"] == "text"
    assert msgs[0]["text"]  # type: ignore[index]
    assert msgs[1]["type"] == "audio"
    assert "/v1/line/media/audio/" in str(msgs[1]["originalContentUrl"])  # type: ignore[index]


@pytest.mark.asyncio
async def test_orchestrator_audio_inbound_voice_off_sends_text_only(mock_settings):
    ms = make_mock_settings(MEDBUDDY_LINE_VOICE_REPLIES="off")
    svc: AppServices = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(ms)
    svc.line.seed_voice_message("m-audio", b"fake-m4a")  # type: ignore[attr-defined]

    await handle_line_event(
        {
            "type": "message",
            "replyToken": "rtoken",
            "source": {"userId": "Uabc", "type": "user"},
            "message": {"id": "m-audio", "type": "audio"},
            "timestamp": 1_704_000_000_000,
            "mode": "active",
            "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "deliveryContext": {"isRedelivery": False},
        },
        svc,
    )
    assert svc.line.loading_indicators == [{"user_id": "Uabc", "seconds": 30}]  # type: ignore[attr-defined]
    msgs = svc.line.replies[0]["messages"]  # type: ignore[index]
    assert len(msgs) == 1
    assert msgs[0]["type"] == "text"


@pytest.mark.asyncio
async def test_orchestrator_text_always_voice_sends_text_and_audio(mock_settings):
    ms = make_mock_settings(MEDBUDDY_LINE_VOICE_REPLIES="always")
    svc: AppServices = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(ms)

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
    assert svc.line.loading_indicators == [{"user_id": "Uabc", "seconds": 30}]  # type: ignore[attr-defined]
    msgs = svc.line.replies[0]["messages"]  # type: ignore[index]
    assert len(msgs) == 2
    assert msgs[0]["type"] == "text"
    assert msgs[1]["type"] == "audio"


@pytest.mark.asyncio
async def test_line_tts_audio_route_serves_blob(mock_settings):
    app.state.services = __import__(  # type: ignore[attr-defined]
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)
    svc: AppServices = app.state.services  # type: ignore[attr-defined]
    aid = svc.line_audio_blobs.put(b"test-bytes")
    transport = ASGITransport(app=app)
    with patch("medbuddy.channels.line.routes.get_settings", return_value=mock_settings):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/v1/line/media/audio/{aid}")
    assert r.status_code == 200
    assert r.content == b"test-bytes"


@pytest.mark.asyncio
async def test_follow_seeds_locale_from_line_profile_language(mock_settings):
    """LINE profile ``language`` updates stored locale before the scripted welcome."""
    svc: AppServices = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)
    uid = "U-follow-locale-en"
    svc.line.seed_user_profile(uid, {"userId": uid, "displayName": "Test", "language": "en"})  # type: ignore[attr-defined]

    await handle_line_event(
        {
            "type": "follow",
            "replyToken": "rt",
            "source": {"userId": uid, "type": "user"},
            "follow": {"isUnblocked": True},
            "timestamp": 1_704_000_000_000,
            "mode": "active",
            "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "deliveryContext": {"isRedelivery": False},
        },
        svc,
    )
    row = await svc.users.get_or_create_user(uid)
    assert row["locale"] == "en"
    msgs = svc.line.replies[-1]["messages"]  # type: ignore[index]
    assert msgs[0]["type"] == "text"
    assert str(msgs[0]["text"]).startswith("Welcome to MedBuddy")


@pytest.mark.asyncio
async def test_follow_sends_welcome_text(mock_settings):
    ms = make_mock_settings(LINE_CHANNEL_SECRET="")
    app.state.services = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(ms)

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
    with patch("medbuddy.channels.line.routes.get_settings", return_value=ms):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post("/v1/line/webhook", content=raw)
    assert r.status_code == 200
    svc: AppServices = app.state.services
    assert svc.line.replies[-1]["type"] == "batch"  # type: ignore[attr-defined]
    msgs = svc.line.replies[-1]["messages"]  # type: ignore[index]
    assert msgs[0]["type"] == "text"


@pytest.mark.asyncio
async def test_follow_seeds_zhtw_locale_from_line_profile_language(mock_settings):
    """LINE profile language 'zh-TW' stores zh-TW locale and sends Chinese welcome."""
    svc: AppServices = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)
    uid = "U-follow-locale-zh"
    svc.line.seed_user_profile(uid, {"userId": uid, "displayName": "測試", "language": "zh-TW"})  # type: ignore[attr-defined]

    await handle_line_event(
        {
            "type": "follow",
            "replyToken": "rt",
            "source": {"userId": uid, "type": "user"},
            "follow": {"isUnblocked": False},
            "timestamp": 1_704_000_000_000,
            "mode": "active",
            "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAA",
            "deliveryContext": {"isRedelivery": False},
        },
        svc,
    )
    row = await svc.users.get_or_create_user(uid)
    assert row["locale"] == "zh-TW"
    msgs = svc.line.replies[-1]["messages"]  # type: ignore[index]
    assert msgs[0]["type"] == "text"
    # zh-TW welcome should NOT start with the English opener
    assert not str(msgs[0]["text"]).startswith("Welcome to MedBuddy")


@pytest.mark.asyncio
async def test_follow_unknown_language_falls_back_to_default_locale(mock_settings):
    """LINE profile language tag not in supported set falls back to zh-TW (the default)."""
    svc: AppServices = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)
    uid = "U-follow-locale-ja"
    svc.line.seed_user_profile(uid, {"userId": uid, "displayName": "太郎", "language": "ja"})  # type: ignore[attr-defined]

    await handle_line_event(
        {
            "type": "follow",
            "replyToken": "rt",
            "source": {"userId": uid, "type": "user"},
            "follow": {"isUnblocked": False},
            "timestamp": 1_704_000_000_000,
            "mode": "active",
            "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAB",
            "deliveryContext": {"isRedelivery": False},
        },
        svc,
    )
    row = await svc.users.get_or_create_user(uid)
    # 'ja' is not supported → falls back to zh-TW
    assert row["locale"] == "zh-TW"
    msgs = svc.line.replies[-1]["messages"]  # type: ignore[index]
    assert msgs[0]["type"] == "text"
    assert not str(msgs[0]["text"]).startswith("Welcome to MedBuddy")


@pytest.mark.asyncio
async def test_follow_no_profile_language_uses_stored_locale(mock_settings):
    """If LINE profile has no language field, stored locale is unchanged."""
    svc: AppServices = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)
    uid = "U-follow-no-lang"
    # Profile without a language key
    svc.line.seed_user_profile(uid, {"userId": uid, "displayName": "User"})  # type: ignore[attr-defined]

    await handle_line_event(
        {
            "type": "follow",
            "replyToken": "rt",
            "source": {"userId": uid, "type": "user"},
            "follow": {"isUnblocked": False},
            "timestamp": 1_704_000_000_000,
            "mode": "active",
            "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAC",
            "deliveryContext": {"isRedelivery": False},
        },
        svc,
    )
    row = await svc.users.get_or_create_user(uid)
    # No language hint → default locale (zh-TW from mock_settings)
    assert row["locale"] == "zh-TW"
    msgs = svc.line.replies[-1]["messages"]  # type: ignore[index]
    assert msgs[0]["type"] == "text"


@pytest.mark.asyncio
async def test_orchestrator_audio_stt_error_replies_with_generic_error(mock_settings):
    svc: AppServices = __import__(
        "medbuddy.container",
        fromlist=["build_app_services"],
    ).build_app_services(mock_settings)
    svc.stt = _FailingStt()  # type: ignore[assignment]
    svc.line.seed_voice_message("m-audio", b"fake-m4a")  # type: ignore[attr-defined]

    await handle_line_event(
        {
            "type": "message",
            "replyToken": "rtoken",
            "source": {"userId": "Uabc", "type": "user"},
            "message": {"id": "m-audio", "type": "audio"},
            "timestamp": 1_704_000_000_000,
            "mode": "active",
            "webhookEventId": "01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "deliveryContext": {"isRedelivery": False},
        },
        svc,
    )
    line = svc.line
    assert hasattr(line, "replies")
    assert line.loading_indicators == [{"user_id": "Uabc", "seconds": 30}]  # type: ignore[attr-defined]
    assert len(line.replies) == 1
    reply = line.replies[0]["messages"][0]  # type: ignore[index]
    assert reply["type"] == "text"
    assert reply["text"]
