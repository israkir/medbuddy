"""Tests for marking doses taken via ConfirmDoseTool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from medbuddy.agents.tools.confirm_dose import ConfirmDoseTool
from tests.helpers import make_mock_settings
from medbuddy.container import build_app_services
from medbuddy.models.domain import MedicationDraft


@pytest.mark.asyncio
async def test_confirm_dose_records_pending_and_replies() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-confirm-dose"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert jobs
    dose_id, _ = jobs[0]
    past = datetime.now(UTC) - timedelta(hours=2)
    svc.users._doses[dose_id]["scheduled_at"] = past  # noqa: SLF001 — test shim for mock store

    tool = ConfirmDoseTool()
    r1 = await tool.run(
        svc=svc,
        user_key=key,
        user_text="I took my meds",
        locale="en",
        record_pending_dose_as_taken=True,
    )
    assert "marked" in r1.reply.lower() or "1" in r1.reply

    r2 = await tool.run(
        svc=svc,
        user_key=key,
        user_text="I took my meds",
        locale="en",
        record_pending_dose_as_taken=True,
    )
    assert "don’t see" in r2.reply or "don't see" in r2.reply.lower()


@pytest.mark.asyncio
async def test_confirm_dose_saves_note_on_dose_event() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-confirm-dose-note"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert jobs
    dose_id, _ = jobs[0]
    past = datetime.now(UTC) - timedelta(hours=2)
    svc.users._doses[dose_id]["scheduled_at"] = past  # noqa: SLF001

    tool = ConfirmDoseTool()
    r = await tool.run(
        svc=svc,
        user_key=key,
        user_text="I took it but got a headache",
        locale="en",
        record_pending_dose_as_taken=True,
        dose_adherence_note="Headache after dose",
    )
    assert "headache" in r.reply.lower()
    assert svc.users._doses[dose_id].get("notes") == "Headache after dose"  # noqa: SLF001


@pytest.mark.asyncio
async def test_confirm_dose_appends_note_when_already_taken() -> None:
    """Follow-up side-effect text must persist on the dose row after pending was cleared."""
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-confirm-dose-followup-note"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Majesik", dosage="100mg", schedule="QD"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert jobs
    dose_id, _ = jobs[0]
    past = datetime.now(UTC) - timedelta(hours=2)
    svc.users._doses[dose_id]["scheduled_at"] = past  # noqa: SLF001

    tool = ConfirmDoseTool()
    r1 = await tool.run(
        svc=svc,
        user_key=key,
        user_text="I took it",
        locale="en",
        record_pending_dose_as_taken=True,
    )
    assert "marked" in r1.reply.lower() or "1" in r1.reply

    r2 = await tool.run(
        svc=svc,
        user_key=key,
        user_text="btw when I took it I had a headache, note it for my doctor",
        locale="en",
        record_pending_dose_as_taken=False,
        dose_adherence_note="Headache after dose",
    )
    assert "headache" in r2.reply.lower()
    assert svc.users._doses[dose_id].get("notes") == "Headache after dose"  # noqa: SLF001


@pytest.mark.asyncio
async def test_confirm_dose_asks_disambiguation_when_multiple_candidates() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-confirm-dose-ambiguous"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Metformin", dosage="500mg", schedule="BID"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs) >= 2
    aspirin_dose_id: str | None = None
    metformin_dose_id: str | None = None
    for dose_id, _ in jobs:
        name = str(svc.users._doses[dose_id]["name"]).lower()  # noqa: SLF001
        if name == "aspirin" and aspirin_dose_id is None:
            aspirin_dose_id = dose_id
        if name == "metformin" and metformin_dose_id is None:
            metformin_dose_id = dose_id
    assert aspirin_dose_id is not None
    assert metformin_dose_id is not None
    past = datetime.now(UTC) - timedelta(hours=1)
    svc.users._doses[aspirin_dose_id]["scheduled_at"] = past  # noqa: SLF001
    svc.users._doses[metformin_dose_id]["scheduled_at"] = past  # noqa: SLF001

    tool = ConfirmDoseTool()
    r = await tool.run(
        svc=svc,
        user_key=key,
        user_text="I took it",
        locale="en",
        user_row={"timezone": "Asia/Taipei"},
        record_pending_dose_as_taken=True,
    )
    assert "which one did you take" in r.reply.lower()
    assert "aspirin" in r.reply.lower()
    assert "metformin" in r.reply.lower()
    assert svc.users._doses[aspirin_dose_id].get("taken_at") is None  # noqa: SLF001
    assert svc.users._doses[metformin_dose_id].get("taken_at") is None  # noqa: SLF001


@pytest.mark.asyncio
async def test_confirm_dose_note_asks_disambiguation_when_multiple_recent_taken() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-confirm-dose-note-ambiguous"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Metformin", dosage="500mg", schedule="BID"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs) >= 2
    aspirin_dose_id: str | None = None
    metformin_dose_id: str | None = None
    for dose_id, _ in jobs:
        name = str(svc.users._doses[dose_id]["name"]).lower()  # noqa: SLF001
        if name == "aspirin" and aspirin_dose_id is None:
            aspirin_dose_id = dose_id
        if name == "metformin" and metformin_dose_id is None:
            metformin_dose_id = dose_id
    assert aspirin_dose_id is not None
    assert metformin_dose_id is not None
    taken_at = datetime.now(UTC) - timedelta(minutes=30)
    svc.users._doses[aspirin_dose_id]["taken_at"] = taken_at  # noqa: SLF001
    svc.users._doses[metformin_dose_id]["taken_at"] = taken_at  # noqa: SLF001

    tool = ConfirmDoseTool()
    r = await tool.run(
        svc=svc,
        user_key=key,
        user_text="Please note I had mild dizziness",
        locale="en",
        user_row={"timezone": "Asia/Taipei"},
        record_pending_dose_as_taken=False,
        dose_adherence_note="Mild dizziness",
    )
    assert "which dose should i attach this note to" in r.reply.lower()
    assert "aspirin" in r.reply.lower()
    assert "metformin" in r.reply.lower()
    assert svc.users._doses[aspirin_dose_id].get("notes") is None  # noqa: SLF001
    assert svc.users._doses[metformin_dose_id].get("notes") is None  # noqa: SLF001
