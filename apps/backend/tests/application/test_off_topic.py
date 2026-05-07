"""Off-topic messages get a fixed refusal without compose_reply."""

from __future__ import annotations

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from tests.helpers import make_mock_settings
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.models.domain import Intent


@pytest.mark.asyncio
async def test_off_topic_refusal_english_mock() -> None:
    settings = make_mock_settings()
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
    svc.llm = MockLLM(intent=Intent.OFF_TOPIC)
    key = "U-off-topic-en"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    reply = await run_assistant_text_turn(svc, user_key=key, user_text="What's the weather today?")
    assert "medication" in reply.lower() or "medicine" in reply.lower()
    assert "best fit" in reply.lower() or "fit for" in reply.lower()


@pytest.mark.asyncio
async def test_off_topic_refusal_zh_mock() -> None:
    settings = make_mock_settings()
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
    svc.llm = MockLLM(intent=Intent.OFF_TOPIC)
    key = "U-off-topic-zh"
    await svc.users.get_or_create_user(key)
    reply = await run_assistant_text_turn(svc, user_key=key, user_text="今天天氣怎麼樣")
    assert "用藥" in reply or "藥" in reply
    assert "適合" in reply or "聊聊" in reply
