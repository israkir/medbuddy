"""Daily chronic-medication resync: only touches patients with indefinite meds."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from medbuddy.container import build_app_services
from medbuddy.models.domain import MedicationDraft
from medbuddy.reminders.chronic_resync import resync_all_indefinite_patients
from tests.helpers import make_mock_settings


@pytest.mark.asyncio
async def test_resync_touches_only_chronic_patients() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    chronic_key = "U-chronic"
    finite_key = "U-finite"
    await svc.users.get_or_create_user(chronic_key)
    await svc.users.get_or_create_user(finite_key)
    await svc.users.add_medication(
        chronic_key,
        MedicationDraft(
            name="Losartan",
            dosage="50mg",
            schedule="QD",
            is_indefinite=True,
            daily_reminder_local_hhmm="08:00",
        ),
    )
    await svc.users.add_medication(
        finite_key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )

    # Both users still have empty dose_events tables — nothing has materialized yet.
    n_resynced = await resync_all_indefinite_patients(svc)
    assert n_resynced == 1

    # Chronic user now has future dose_events; finite user is untouched.
    now = datetime.now(UTC)
    far = now + timedelta(days=settings.reminder_horizon_days + 1)
    chronic_doses = await svc.users.list_upcoming_dose_events(
        chronic_key, from_utc=now, until_utc_exclusive=far, max_items=200
    )
    finite_doses = await svc.users.list_upcoming_dose_events(
        finite_key, from_utc=now, until_utc_exclusive=far, max_items=200
    )
    assert len(chronic_doses) >= 1
    assert finite_doses == []


@pytest.mark.asyncio
async def test_resync_with_no_chronic_patients_is_zero() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    await svc.users.get_or_create_user("U-1")
    await svc.users.add_medication(
        "U-1",
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    n = await resync_all_indefinite_patients(svc)
    assert n == 0


@pytest.mark.asyncio
async def test_resync_refills_window_after_advance() -> None:
    """After the rolling window empties, resync repopulates new dose_events for the chronic med."""
    settings = make_mock_settings(MEDBUDDY_REMINDER_HORIZON_DAYS="3")
    svc = build_app_services(settings)
    key = "U-chronic-refill"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(
        key,
        MedicationDraft(
            name="Levothyroxine",
            dosage="50mcg",
            schedule="QD",
            is_indefinite=True,
            daily_reminder_local_hhmm="08:00",
        ),
    )
    initial = await svc.users.sync_upcoming_dose_events(key)
    assert len(initial) >= 1

    # Simulate the window emptying by deleting the in-memory doses for that user.
    doses_map = svc.users._doses  # type: ignore[attr-defined]
    for did, d in list(doses_map.items()):
        if d.get("line_user_id") == key:
            del doses_map[did]
    now = datetime.now(UTC)
    far = now + timedelta(days=settings.reminder_horizon_days + 1)
    assert (
        await svc.users.list_upcoming_dose_events(
            key, from_utc=now, until_utc_exclusive=far, max_items=200
        )
        == []
    )

    refilled = await resync_all_indefinite_patients(svc)
    assert refilled == 1
    after = await svc.users.list_upcoming_dose_events(
        key, from_utc=now, until_utc_exclusive=far, max_items=200
    )
    assert len(after) >= 1
