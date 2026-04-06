"""Off-topic messages get a fixed refusal without compose_reply."""

from __future__ import annotations

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.config import Settings


@pytest.mark.asyncio
async def test_off_topic_refusal_english_mock() -> None:
    settings = Settings(mock_external_services=True)
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
    key = "U-off-topic-en"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    reply = await run_assistant_text_turn(svc, user_key=key, user_text="What's the weather today?")
    assert "medication" in reply.lower() or "medicine" in reply.lower()
    assert "help with that topic" in reply.lower()


@pytest.mark.asyncio
async def test_off_topic_refusal_zh_mock() -> None:
    settings = Settings(mock_external_services=True)
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
    key = "U-off-topic-zh"
    await svc.users.get_or_create_user(key)
    reply = await run_assistant_text_turn(svc, user_key=key, user_text="今天天氣怎麼樣")
    assert "用藥" in reply or "藥" in reply
    assert "無法" in reply or "協助" in reply
