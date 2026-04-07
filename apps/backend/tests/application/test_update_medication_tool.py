from __future__ import annotations

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.config import Settings
from medbuddy.container import build_app_services
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.llm.schemas import MedicationUpdateResolution
from medbuddy.models.domain import Intent, MedicationDraft


@pytest.mark.asyncio
async def test_update_medication_updates_dosage_schedule_and_instructions() -> None:
    settings = Settings(mock_external_services=True)
    svc = build_app_services(settings)
    key = "U-update-medication-fields"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    saved = await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="daily", instructions=None),
    )
    svc.llm = MockLLM(
        intent=Intent.UPDATE_MEDICATION,
        locale="en",
        medication_update=MedicationUpdateResolution(
            medication_id=saved.id,
            name=None,
            dosage="81mg",
            schedule="after breakfast",
            instructions="avoid tea right after dose",
            clear_instructions=False,
        ),
    )
    reply = await run_assistant_text_turn(
        svc,
        user_key=key,
        user_text="update my aspirin to 81mg after breakfast and note avoid tea right after dose",
    )
    meds = await svc.users.list_medications(key)
    assert len(meds) == 1
    assert meds[0].dosage == "81mg"
    assert meds[0].schedule == "after breakfast"
    assert meds[0].instructions == "avoid tea right after dose"
    assert "updated aspirin" in reply.lower()
    assert "upcoming 3 days" in reply.lower()


@pytest.mark.asyncio
async def test_update_medication_can_clear_instructions() -> None:
    settings = Settings(mock_external_services=True)
    svc = build_app_services(settings)
    key = "U-update-medication-clear-note"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    saved = await svc.users.add_medication(
        key,
        MedicationDraft(
            name="Aspirin",
            dosage="100mg",
            schedule="daily",
            instructions="take with food",
        ),
    )
    svc.llm = MockLLM(
        intent=Intent.UPDATE_MEDICATION,
        locale="en",
        medication_update=MedicationUpdateResolution(
            medication_id=saved.id,
            name=None,
            dosage=None,
            schedule=None,
            instructions=None,
            clear_instructions=True,
        ),
    )
    await run_assistant_text_turn(
        svc,
        user_key=key,
        user_text="remove the note from my aspirin",
    )
    meds = await svc.users.list_medications(key)
    assert meds[0].instructions is None
