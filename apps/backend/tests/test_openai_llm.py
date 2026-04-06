"""OpenAI LLM adapter wiring (mocked API client)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from medbuddy.llm.schemas import IntentClassification
from medbuddy.models.domain import Intent


@pytest.mark.asyncio
async def test_openai_classify_intent_uses_structured_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from medbuddy.integrations import openai_llm as mod

    classification = IntentClassification(
        intent="list_medications", reasoning="user asked for list"
    )

    class FakeMsg:
        refusal = None
        parsed = classification
        content = None

    class FakeChoice:
        message = FakeMsg()

    class FakeResp:
        choices = [FakeChoice()]

    fake_client = MagicMock()
    fake_client.chat.completions.parse = MagicMock(return_value=FakeResp())
    monkeypatch.setattr(mod, "_OpenAIClient", lambda **kw: fake_client)

    llm = mod.OpenAILLM(api_key="sk-test", locale="en")
    intent = await llm.classify_intent("what medications do I have")
    assert intent == Intent.LIST_MEDICATIONS
    fake_client.chat.completions.parse.assert_called_once()


@pytest.mark.asyncio
async def test_map_intent_label_substring_fuzzy() -> None:
    from medbuddy.integrations.openai_llm import _map_intent_label

    assert _map_intent_label("add_medication") == Intent.ADD_MEDICATION
    assert _map_intent_label("something add_medication extra") == Intent.ADD_MEDICATION
    assert _map_intent_label("update_locale") == Intent.UPDATE_LOCALE
    assert _map_intent_label("off_topic") == Intent.OFF_TOPIC
