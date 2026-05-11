"""Tests for LINE push reminder delivery and idempotency."""

from __future__ import annotations

import pytest

from medbuddy.core.i18n import t
from tests.helpers import make_mock_settings
from medbuddy.container import build_app_services
from medbuddy.models.domain import MedicationDraft
from medbuddy.reminders.deliver import deliver_dose_reminder


@pytest.mark.asyncio
async def test_deliver_sends_line_push_and_marks_sent() -> None:
    settings = make_mock_settings(MEDBUDDY_REMINDER_EDUCATION_CTA_EVERY_N_DAYS="1")
    svc = build_app_services(settings)
    key = "U-test-line"
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
    assert svc.line.pushes[0]["to_user_id"] == key
    push_text = svc.line.pushes[0]["messages"][0]["text"]
    assert "Aspirin" in push_text
    assert t("reminder.education_cta", locale="zh-TW") in push_text

    again = await deliver_dose_reminder(svc, dose_id)
    assert again is False
    assert len(svc.line.pushes) == 1


@pytest.mark.asyncio
async def test_deliver_skips_when_dose_already_marked_missed() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-test-line-missed"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs) >= 1
    dose_id, _ = jobs[0]
    svc.users._doses[dose_id]["missed_at"] = True  # noqa: SLF001

    sent = await deliver_dose_reminder(svc, dose_id)
    assert sent is False
    assert len(svc.line.pushes) == 0


@pytest.mark.asyncio
async def test_deliver_skips_stale_dose_id_after_second_sync() -> None:
    """Bare sync replaces dose_events UUIDs; deferred jobs keyed by old ids must no-op."""
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-test-stale-dose-id"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    jobs1 = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs1) >= 1
    stale_id, _ = jobs1[0]

    jobs2 = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs2) >= 1
    new_id, _ = jobs2[0]
    assert new_id != stale_id

    skip = await deliver_dose_reminder(svc, stale_id)
    assert skip is False
    assert len(svc.line.pushes) == 0

    ok = await deliver_dose_reminder(svc, new_id)
    assert ok is True
    assert len(svc.line.pushes) == 1
