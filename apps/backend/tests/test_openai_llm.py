"""OpenAI LLM adapter wiring (mocked API client)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from medbuddy.llm.schemas import IntentClassification
from medbuddy.models.domain import Intent


@pytest.mark.asyncio
async def test_openai_interpret_user_turn_uses_structured_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from medbuddy.integrations import openai_llm as mod

    classification = IntentClassification(
        intent="list_medications",
        reasoning="user asked for list",
        record_pending_dose_as_taken=False,
        dose_adherence_note=None,
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
    turn = await llm.interpret_user_turn("what medications do I have")
    assert turn.intent == Intent.LIST_MEDICATIONS
    assert turn.record_pending_dose_as_taken is False
    assert turn.dose_adherence_note is None
    fake_client.chat.completions.parse.assert_called_once()


def test_recent_context_for_intent_includes_redacted_tail() -> None:
    from datetime import UTC, datetime

    from medbuddy.agents.medication_agent import _recent_context_for_intent
    from medbuddy.models.domain import ConversationTurn

    turns = [
        ConversationTurn(role="user", content="hi", at=datetime.now(UTC)),
        ConversationTurn(role="assistant", content="要設定幾天提醒？", at=datetime.now(UTC)),
    ]
    out = _recent_context_for_intent(turns)
    assert out is not None
    assert "assistant:" in out
    assert "提醒" in out


def test_map_intent_label_substring_fuzzy() -> None:
    from medbuddy.llm.intent_map import map_intent_label

    assert map_intent_label("add_medication") == Intent.ADD_MEDICATION
    assert map_intent_label("something add_medication extra") == Intent.ADD_MEDICATION
    assert map_intent_label("update_locale") == Intent.UPDATE_PROFILE
    assert map_intent_label("off_topic") == Intent.OFF_TOPIC
