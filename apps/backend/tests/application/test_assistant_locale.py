"""Assistant turn uses per-user locale and chat-driven locale updates."""

from __future__ import annotations

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.config import Settings
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.models.domain import Intent


@pytest.mark.asyncio
async def test_assistant_updates_locale_on_request() -> None:
    settings = Settings(mock_external_services=True)
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
    svc.llm = MockLLM(intent=Intent.UPDATE_PROFILE, profile_patch={"locale": "en"})
    key = "U-locale-switch"
    row = await svc.users.get_or_create_user(key)
    assert row.get("locale") == "zh-TW"

    reply = await run_assistant_text_turn(svc, user_key=key, user_text="switch to English")
    assert "English" in reply or "english" in reply.lower()
    row2 = await svc.users.get_or_create_user(key)
    assert row2.get("locale") == "en"


@pytest.mark.asyncio
async def test_assistant_locale_llm_fallback_paraphrase() -> None:
    """Classifier returns update_profile; extract_profile_patch supplies target locale."""
    settings = Settings(mock_external_services=True)
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
    svc.llm = MockLLM(intent=Intent.UPDATE_PROFILE, profile_patch={"locale": "en"})
    key = "U-locale-paraphrase"
    await svc.users.get_or_create_user(key)
    reply = await run_assistant_text_turn(
        svc, user_key=key, user_text="I prefer English replies from now on"
    )
    assert "English" in reply or "english" in reply.lower()
    row = await svc.users.get_or_create_user(key)
    assert row.get("locale") == "en"


@pytest.mark.asyncio
async def test_assistant_unchanged_when_already_english() -> None:
    settings = Settings(mock_external_services=True)
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
    svc.llm = MockLLM(intent=Intent.UPDATE_PROFILE, profile_patch={"locale": "en"})
    key = "U-locale-en"
    await svc.users.patch_user_profile(key, {"locale": "en"})
    reply = await run_assistant_text_turn(svc, user_key=key, user_text="use English")
    assert "already" in reply.lower() or "English" in reply


@pytest.mark.asyncio
async def test_assistant_updates_timezone_via_profile_intent() -> None:
    settings = Settings(mock_external_services=True)
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
    svc.llm = MockLLM(intent=Intent.UPDATE_PROFILE, profile_patch={"timezone": "America/New_York"})
    key = "U-timezone-switch"
    await svc.users.get_or_create_user(key)
    reply = await run_assistant_text_turn(
        svc, user_key=key, user_text="my timezone is New York now"
    )
    assert "America/New_York" in reply
    row = await svc.users.get_or_create_user(key)
    assert row.get("timezone") == "America/New_York"
