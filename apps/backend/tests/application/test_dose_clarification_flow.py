"""End-to-end tests for persisted dose disambiguation and deterministic follow-ups."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from tests.helpers import make_mock_settings
from medbuddy.container import build_app_services
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.models.domain import Intent, MedicationDraft


@pytest.mark.asyncio
async def test_assistant_resolves_pending_dose_with_choice_one() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-dose-clarify-pick-1"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    await svc.users.add_medication(
        key, MedicationDraft(name="Metformin", dosage="500mg", schedule="BID")
    )
    await svc.users.add_medication(
        key, MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD")
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    aspir_id: str | None = None
    met_id: str | None = None
    for dose_id, _ in jobs:
        name = str(svc.users._doses[dose_id]["name"]).lower()  # noqa: SLF001
        if name == "aspirin" and aspir_id is None:
            aspir_id = dose_id
        if name == "metformin" and met_id is None:
            met_id = dose_id
    assert aspir_id and met_id
    svc.users._doses[met_id]["scheduled_at"] = datetime.now(UTC) - timedelta(
        hours=2
    )  # noqa: SLF001
    svc.users._doses[aspir_id]["scheduled_at"] = datetime.now(UTC) - timedelta(
        hours=1
    )  # noqa: SLF001

    svc.llm = MockLLM(intent=Intent.CONFIRM_DOSE, record_pending_dose_as_taken=True, locale="en")
    r1 = (await run_assistant_text_turn(svc, user_key=key, user_text="I took it")).reply
    assert "which one" in r1.lower()
    assert await svc.users.get_dose_clarification_pending(key) is not None

    svc.llm = MockLLM(
        intent=Intent.GENERAL_QUESTION, record_pending_dose_as_taken=False, locale="en"
    )
    r2 = (await run_assistant_text_turn(svc, user_key=key, user_text="2")).reply
    assert "marked" in r2.lower()
    assert await svc.users.get_dose_clarification_pending(key) is None
    assert svc.users._doses[met_id].get("taken_at") is not None  # noqa: SLF001
    assert svc.users._doses[aspir_id].get("taken_at") is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_assistant_resolves_pending_dose_all() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-dose-clarify-all"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    await svc.users.add_medication(
        key, MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD")
    )
    await svc.users.add_medication(
        key, MedicationDraft(name="Metformin", dosage="500mg", schedule="BID")
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    ids: list[str] = []
    for dose_id, _ in jobs:
        name = str(svc.users._doses[dose_id]["name"]).lower()  # noqa: SLF001
        if name in ("aspirin", "metformin") and dose_id not in ids:
            ids.append(dose_id)
        if len(ids) >= 2:
            break
    assert len(ids) == 2
    past = datetime.now(UTC) - timedelta(hours=1)
    for i in ids:
        svc.users._doses[i]["scheduled_at"] = past  # noqa: SLF001

    svc.llm = MockLLM(intent=Intent.CONFIRM_DOSE, record_pending_dose_as_taken=True, locale="en")
    await run_assistant_text_turn(svc, user_key=key, user_text="I took it")

    svc.llm = MockLLM(
        intent=Intent.GENERAL_QUESTION, record_pending_dose_as_taken=False, locale="en"
    )
    r2 = (await run_assistant_text_turn(svc, user_key=key, user_text="all")).reply
    assert "marked" in r2.lower()
    for i in ids:
        assert svc.users._doses[i].get("taken_at") is not None  # noqa: SLF001


@pytest.mark.asyncio
async def test_assistant_invalid_clarification_keeps_pending() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-dose-clarify-invalid"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    await svc.users.add_medication(
        key, MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD")
    )
    await svc.users.add_medication(
        key, MedicationDraft(name="Metformin", dosage="500mg", schedule="BID")
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    id_a: str | None = None
    id_b: str | None = None
    for dose_id, _ in jobs:
        name = str(svc.users._doses[dose_id]["name"]).lower()  # noqa: SLF001
        if name == "aspirin" and id_a is None:
            id_a = dose_id
        if name == "metformin" and id_b is None:
            id_b = dose_id
    assert id_a and id_b
    past = datetime.now(UTC) - timedelta(hours=1)
    svc.users._doses[id_a]["scheduled_at"] = past  # noqa: SLF001
    svc.users._doses[id_b]["scheduled_at"] = past  # noqa: SLF001

    svc.llm = MockLLM(intent=Intent.CONFIRM_DOSE, record_pending_dose_as_taken=True, locale="en")
    await run_assistant_text_turn(svc, user_key=key, user_text="I took it")

    svc.llm = MockLLM(
        intent=Intent.GENERAL_QUESTION, record_pending_dose_as_taken=False, locale="en"
    )
    r2 = (await run_assistant_text_turn(svc, user_key=key, user_text="99")).reply
    assert "numbers" in r2.lower() or "1" in r2.lower()
    assert await svc.users.get_dose_clarification_pending(key) is not None


@pytest.mark.asyncio
async def test_assistant_unrelated_message_clears_pending_clarification() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-dose-clarify-clear"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    await svc.users.add_medication(
        key, MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD")
    )
    await svc.users.add_medication(
        key, MedicationDraft(name="Metformin", dosage="500mg", schedule="BID")
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    id_a: str | None = None
    id_b: str | None = None
    for dose_id, _ in jobs:
        name = str(svc.users._doses[dose_id]["name"]).lower()  # noqa: SLF001
        if name == "aspirin" and id_a is None:
            id_a = dose_id
        if name == "metformin" and id_b is None:
            id_b = dose_id
    assert id_a and id_b
    past = datetime.now(UTC) - timedelta(hours=1)
    svc.users._doses[id_a]["scheduled_at"] = past  # noqa: SLF001
    svc.users._doses[id_b]["scheduled_at"] = past  # noqa: SLF001

    svc.llm = MockLLM(intent=Intent.CONFIRM_DOSE, record_pending_dose_as_taken=True, locale="en")
    await run_assistant_text_turn(svc, user_key=key, user_text="I took it")
    assert await svc.users.get_dose_clarification_pending(key) is not None

    svc.llm = MockLLM(
        intent=Intent.GENERAL_QUESTION, record_pending_dose_as_taken=False, locale="en"
    )
    await run_assistant_text_turn(svc, user_key=key, user_text="tell me a joke")
    assert await svc.users.get_dose_clarification_pending(key) is None
