"""Orchestrator executes bulk medication / reminder tools."""

from __future__ import annotations

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.container import build_app_services
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.llm.agent_types import ChatToolCall
from medbuddy.models.domain import Intent, MedicationDraft
from tests.helpers import make_mock_settings


@pytest.mark.asyncio
async def test_remove_all_medications_tool_clears_list() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-bulk-remove-all"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD", instructions=None),
    )
    llm = MockLLM(intent=Intent.REMOVE_MEDICATION, locale="en")
    _orch_n = {"n": 0}

    async def complete_chat_with_tools(
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ):
        _ = (messages, tools)
        _orch_n["n"] += 1
        if _orch_n["n"] == 1:
            return (
                None,
                [
                    ChatToolCall(
                        id="t1",
                        name="remove_all_medications",
                        arguments="{}",
                    )
                ],
            )
        return ("Cleared your medication list.", None)

    llm.complete_chat_with_tools = complete_chat_with_tools  # type: ignore[method-assign]
    svc.llm = llm

    out = (await run_assistant_text_turn(svc, user_key=key, user_text="clear all my meds")).reply
    assert len(await svc.users.list_medications(key)) == 0
    assert "cleared" in out.lower() or "removed" in out.lower()


@pytest.mark.asyncio
async def test_simulate_notify_sets_metadata_flag() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-simulate-notify"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(
        key,
        {"locale": "en", "emergency_contact": "daughter 0912345678"},
    )

    llm = MockLLM(intent=Intent.GENERAL_QUESTION, locale="en")
    _sim_n = {"n": 0}

    async def complete_chat_with_tools(
        *,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]],
    ):
        _ = (messages, tools)
        _sim_n["n"] += 1
        if _sim_n["n"] == 1:
            return (
                None,
                [
                    ChatToolCall(
                        id="n1",
                        name="simulate_notify_emergency_contact",
                        arguments='{"reason": "dizzy and vomiting"}',
                    )
                ],
            )
        return (
            "Please rest; if symptoms worsen, seek urgent care. (Simulation: contact would be notified.)",
            None,
        )

    llm.complete_chat_with_tools = complete_chat_with_tools  # type: ignore[method-assign]
    svc.llm = llm

    turn = await run_assistant_text_turn(svc, user_key=key, user_text="I feel dizzy and vomiting")
    assert turn.metadata.get("simulated_emergency_notification") is True
    assert "simulation" in turn.reply.lower() or "0912345678" in turn.reply
