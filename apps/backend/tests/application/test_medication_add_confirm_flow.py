"""Pending confirmation when an add-medication draft omits dose, schedule, or notes."""

from __future__ import annotations

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.config import Settings
from medbuddy.container import build_app_services
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.models.domain import Intent, MedicationDraft


@pytest.mark.asyncio
async def test_add_medication_incomplete_triggers_confirm_then_yes_saves() -> None:
    settings = Settings(mock_external_services=True)
    svc = build_app_services(settings)
    key = "U-med-add-confirm"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    draft = MedicationDraft(
        name="Vitamin D",
        dosage="Unspecified",
        schedule="Unspecified",
        instructions=None,
    )
    svc.llm = MockLLM(intent=Intent.ADD_MEDICATION, medication_draft=draft, locale="en")
    r1 = await run_assistant_text_turn(svc, user_key=key, user_text="add vitamin d")
    assert "vitamin d" in r1.lower()
    assert "yes" in r1.lower()
    pending = await svc.users.get_medication_add_confirmation_pending(key)
    assert pending is not None
    assert pending.draft.name == "Vitamin D"

    svc.llm = MockLLM(intent=Intent.GENERAL_QUESTION, locale="en")
    r2 = await run_assistant_text_turn(svc, user_key=key, user_text="yes")
    assert "vitamin" in r2.lower() or "saved" in r2.lower()
    meds = await svc.users.list_medications(key)
    assert len(meds) == 1
    assert meds[0].name == "Vitamin D"
    assert await svc.users.get_medication_add_confirmation_pending(key) is None


@pytest.mark.asyncio
async def test_add_medication_incomplete_no_cancel_clears_pending() -> None:
    settings = Settings(mock_external_services=True)
    svc = build_app_services(settings)
    key = "U-med-add-cancel"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    draft = MedicationDraft(
        name="Zinc",
        dosage="Unspecified",
        schedule="daily",
        instructions=None,
    )
    svc.llm = MockLLM(intent=Intent.ADD_MEDICATION, medication_draft=draft, locale="en")
    await run_assistant_text_turn(svc, user_key=key, user_text="track zinc")
    assert await svc.users.get_medication_add_confirmation_pending(key) is not None

    svc.llm = MockLLM(intent=Intent.GENERAL_QUESTION, locale="en")
    r2 = await run_assistant_text_turn(svc, user_key=key, user_text="no")
    assert "didn" in r2.lower() or "add" in r2.lower()
    assert len(await svc.users.list_medications(key)) == 0
    assert await svc.users.get_medication_add_confirmation_pending(key) is None


@pytest.mark.asyncio
async def test_add_medication_complete_skips_confirm() -> None:
    settings = Settings(mock_external_services=True)
    svc = build_app_services(settings)
    key = "U-med-add-full"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    draft = MedicationDraft(
        name="Aspirin",
        dosage="100mg",
        schedule="QD",
        instructions="after breakfast",
    )
    svc.llm = MockLLM(intent=Intent.ADD_MEDICATION, medication_draft=draft, locale="en")
    await run_assistant_text_turn(
        svc, user_key=key, user_text="aspirin 100mg once daily after breakfast"
    )
    assert await svc.users.get_medication_add_confirmation_pending(key) is None
    meds = await svc.users.list_medications(key)
    assert len(meds) == 1
