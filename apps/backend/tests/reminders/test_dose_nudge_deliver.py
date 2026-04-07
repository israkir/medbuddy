"""Tests for follow-up dose reminder nudges."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from medbuddy.config import Settings
from medbuddy.container import build_app_services
from medbuddy.models.domain import MedicationDraft
from medbuddy.reminders.deliver import deliver_dose_reminder, deliver_dose_reminder_nudge


@pytest.mark.asyncio
async def test_nudge_sends_after_primary_and_increments_count() -> None:
    settings = Settings(
        mock_external_services=True,
        reminder_nudge_intervals_minutes=[60],
    )
    svc = build_app_services(settings)
    key = "U-nudge-test"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs) >= 1
    dose_id, _ = jobs[0]

    sent = await deliver_dose_reminder(svc, dose_id)
    assert sent is True
    assert len(svc.line.pushes) == 1

    n = await deliver_dose_reminder_nudge(svc, dose_id, 0)
    assert n is True
    assert len(svc.line.pushes) == 2
    assert (
        "Follow-up" in svc.line.pushes[1]["messages"][0]["text"]
        or "再次提醒" in svc.line.pushes[1]["messages"][0]["text"]
    )

    again = await deliver_dose_reminder_nudge(svc, dose_id, 0)
    assert again is False
    assert len(svc.line.pushes) == 2


@pytest.mark.asyncio
async def test_nudge_skips_when_taken() -> None:
    settings = Settings(
        mock_external_services=True,
        reminder_nudge_intervals_minutes=[60],
    )
    svc = build_app_services(settings)
    key = "U-nudge-taken"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    dose_id, _ = jobs[0]
    svc.users._doses[dose_id]["scheduled_at"] = datetime.now(UTC) - timedelta(
        hours=1
    )  # noqa: SLF001
    await deliver_dose_reminder(svc, dose_id)
    n0 = await svc.users.mark_pending_doses_taken(key)
    assert n0 >= 1

    n = await deliver_dose_reminder_nudge(svc, dose_id, 0)
    assert n is False
    assert len(svc.line.pushes) == 1
