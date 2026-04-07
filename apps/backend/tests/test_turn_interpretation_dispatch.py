"""MedicationAgent uses structured adherence slots, not intent name alone."""

from __future__ import annotations

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.config import Settings
from medbuddy.container import build_app_services
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.models.domain import Intent


@pytest.mark.asyncio
async def test_confirm_dose_intent_without_adherence_slots_does_not_mark_dose() -> None:
    settings = Settings(mock_external_services=True)
    svc = build_app_services(settings)
    svc.llm = MockLLM(
        intent=Intent.CONFIRM_DOSE,
        record_pending_dose_as_taken=False,
        locale="en",
    )
    key = "U-interpret-no-adherence"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    reply = await run_assistant_text_turn(
        svc, user_key=key, user_text="yes headache is still bothering"
    )
    assert "marked" not in reply.lower()
    assert "(test mode)" in reply.lower() or "Got it:" in reply
