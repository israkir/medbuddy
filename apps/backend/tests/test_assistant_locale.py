"""Assistant turn uses per-user locale and chat-driven locale updates."""

from __future__ import annotations

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.config import Settings


@pytest.mark.asyncio
async def test_assistant_updates_locale_on_request() -> None:
    settings = Settings(mock_external_services=True)
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
    key = "U-locale-switch"
    row = await svc.users.get_or_create_user(key)
    assert row.get("locale") == "zh-TW"

    reply = await run_assistant_text_turn(svc, user_key=key, user_text="switch to English")
    assert "English" in reply or "english" in reply.lower()
    row2 = await svc.users.get_or_create_user(key)
    assert row2.get("locale") == "en"


@pytest.mark.asyncio
async def test_assistant_locale_llm_fallback_paraphrase() -> None:
    """Regex misses paraphrases; classifier + extract_locale_intent supplies target."""
    settings = Settings(mock_external_services=True)
    from medbuddy.container import build_app_services

    svc = build_app_services(settings)
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
    key = "U-locale-en"
    await svc.users.patch_user_profile(key, {"locale": "en"})
    reply = await run_assistant_text_turn(svc, user_key=key, user_text="use English")
    assert "already" in reply.lower() or "English" in reply
