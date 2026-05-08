"""Orchestrator receives recent user/assistant turns in complete_chat_with_tools messages."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from medbuddy.agents.orchestrator import (
    orchestrator_prior_messages,
    recent_conversation_for_medication_extraction,
)
from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.container import build_app_services
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.models.domain import ConversationTurn, Intent
from tests.helpers import make_mock_settings


def test_orchestrator_prior_messages_tail_cap() -> None:
    turns = [
        ConversationTurn(role="user", content="first", at=datetime.now(UTC)),
        ConversationTurn(role="assistant", content="second", at=datetime.now(UTC)),
        ConversationTurn(role="user", content="third", at=datetime.now(UTC)),
    ]
    assert len(orchestrator_prior_messages(turns, max_turns=1)) == 1
    assert orchestrator_prior_messages(turns, max_turns=1)[0]["content"] == "third"
    assert len(orchestrator_prior_messages(turns, max_turns=2)) == 2


def test_recent_conversation_for_medication_extraction_formats_tail() -> None:
    turns = [
        ConversationTurn(
            role="user", content="remind vitamin C in one minute", at=datetime.now(UTC)
        ),
        ConversationTurn(
            role="assistant",
            content="Your vitamin C is at 04:16; want a new one in 1 minute?",
            at=datetime.now(UTC),
        ),
    ]
    out = recent_conversation_for_medication_extraction(turns, max_turns=8)
    assert out is not None
    assert "user:" in out
    assert "assistant:" in out
    assert "vitamin c" in out.lower()


def test_orchestrator_prior_messages_redacts_pii() -> None:
    turns = [
        ConversationTurn(role="user", content="Reach me at 0912345678", at=datetime.now(UTC)),
    ]
    out = orchestrator_prior_messages(turns, max_turns=5)
    assert len(out) == 1
    assert "0912345678" not in out[0]["content"]


@pytest.mark.asyncio
async def test_complete_chat_with_tools_includes_prior_turns() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-orch-prior-msgs"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    now = datetime.now(UTC)
    await svc.conversations.append_turn(
        key, ConversationTurn(role="user", content="What meds am I on?", at=now)
    )
    await svc.conversations.append_turn(
        key,
        ConversationTurn(role="assistant", content="You take metformin 500mg.", at=now),
    )

    captured: list[list[dict[str, Any]]] = []

    async def spy_complete(
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str, None]:
        captured.append(messages)
        _ = tools
        return ("Understood.", None)

    llm = MockLLM(intent=Intent.GENERAL_QUESTION, locale="en")
    llm.complete_chat_with_tools = spy_complete  # type: ignore[method-assign]
    svc.llm = llm

    await run_assistant_text_turn(svc, user_key=key, user_text="Should I take it with food?")

    assert captured, "complete_chat_with_tools should run"
    first = captured[0]
    roles = [m.get("role") for m in first]
    assert roles[0] == "system"
    assert roles[-1] == "user"
    blob = "\n".join(str(m.get("content")) for m in first)
    assert "metformin" in blob.lower()
    assert "Should I take it with food?" in blob


@pytest.mark.asyncio
async def test_mock_llm_orchestrator_step_resets_each_turn_with_history() -> None:
    """Regression: first hop must reset _orch_step even when len(messages) > 2."""
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-mock-orch-reset"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    now = datetime.now(UTC)
    await svc.conversations.append_turn(key, ConversationTurn(role="user", content="hi", at=now))
    await svc.conversations.append_turn(
        key, ConversationTurn(role="assistant", content="hello", at=now)
    )

    llm = MockLLM(intent=Intent.ADD_MEDICATION, locale="en")
    svc.llm = llm

    await run_assistant_text_turn(svc, user_key=key, user_text="add aspirin")

    assert getattr(llm, "_orch_step", 0) >= 1
