"""Delivery-time safety net: chronic-med push tops up the rolling window when low."""

from __future__ import annotations

import pytest

from medbuddy.container import build_app_services
from medbuddy.models.domain import MedicationDraft
from medbuddy.reminders.deliver import deliver_dose_reminder
from tests.helpers import make_mock_settings


def _count_future_for(svc, line_user_id: str, medication_id: str) -> int:
    n = 0
    for d in svc.users._doses.values():  # type: ignore[attr-defined]
        if d.get("line_user_id") != line_user_id:
            continue
        if str(d.get("medication_id")) != medication_id:
            continue
        if d.get("taken_at") is not None or d.get("missed_at") is not None:
            continue
        n += 1
    return n


@pytest.mark.asyncio
async def test_chronic_delivery_topup_fires_when_window_runs_low() -> None:
    """Fewer than threshold future events triggers a resync after the push succeeds."""
    settings = make_mock_settings(
        MEDBUDDY_REMINDER_HORIZON_DAYS="14",
        MEDBUDDY_CHRONIC_DELIVERY_TOPUP_THRESHOLD="3",
    )
    svc = build_app_services(settings)
    key = "U-chronic-topup"
    await svc.users.get_or_create_user(key)
    saved = await svc.users.add_medication(
        key,
        MedicationDraft(
            name="Losartan",
            dosage="50mg",
            schedule="QD",
            is_indefinite=True,
            daily_reminder_local_hhmm="08:00",
        ),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs) >= 2

    # Trim the window down to one future event so the push will see remaining<threshold.
    doses_map = svc.users._doses  # type: ignore[attr-defined]
    same_med = sorted(
        [(did, d) for did, d in doses_map.items() if str(d.get("medication_id")) == saved.id],
        key=lambda kv: kv[1]["scheduled_at"],
    )
    earliest_id = same_med[0][0]
    for did, d in same_med[1:]:
        del doses_map[did]
    assert _count_future_for(svc, key, saved.id) == 1

    sent = await deliver_dose_reminder(svc, earliest_id)
    assert sent is True
    # The push itself consumes the only future event (it is marked sent), and the
    # delivery-time top-up should refill the window via sync_and_enqueue_reminders.
    refilled = _count_future_for(svc, key, saved.id)
    assert refilled >= settings.reminder_horizon_days - 1


@pytest.mark.asyncio
async def test_topup_skipped_when_med_is_not_indefinite() -> None:
    """Finite meds never trigger the delivery-time resync."""
    settings = make_mock_settings(MEDBUDDY_CHRONIC_DELIVERY_TOPUP_THRESHOLD="3")
    svc = build_app_services(settings)
    key = "U-finite"
    await svc.users.get_or_create_user(key)
    saved = await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs) >= 1
    # Trim down to a single future event so we are also below threshold.
    doses_map = svc.users._doses  # type: ignore[attr-defined]
    same_med = sorted(
        [(did, d) for did, d in doses_map.items() if str(d.get("medication_id")) == saved.id],
        key=lambda kv: kv[1]["scheduled_at"],
    )
    earliest_id = same_med[0][0]
    for did, d in same_med[1:]:
        del doses_map[did]
    before = _count_future_for(svc, key, saved.id)
    assert before == 1

    sent = await deliver_dose_reminder(svc, earliest_id)
    assert sent is True
    # No top-up — the only future event is now marked sent, no new ones materialized.
    after = _count_future_for(svc, key, saved.id)
    assert after == 1


@pytest.mark.asyncio
async def test_topup_skipped_when_above_threshold() -> None:
    """When remaining future events >= threshold the top-up does nothing — no new ids appear."""
    settings = make_mock_settings(
        MEDBUDDY_REMINDER_HORIZON_DAYS="14",
        MEDBUDDY_CHRONIC_DELIVERY_TOPUP_THRESHOLD="3",
    )
    svc = build_app_services(settings)
    key = "U-chronic-above"
    await svc.users.get_or_create_user(key)
    saved = await svc.users.add_medication(
        key,
        MedicationDraft(
            name="Losartan",
            dosage="50mg",
            schedule="QD",
            is_indefinite=True,
            daily_reminder_local_hhmm="08:00",
        ),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs) >= 4

    doses_map = svc.users._doses  # type: ignore[attr-defined]
    same_med = sorted(
        [(did, d) for did, d in doses_map.items() if str(d.get("medication_id")) == saved.id],
        key=lambda kv: kv[1]["scheduled_at"],
    )
    earliest_id = same_med[0][0]
    pre_ids = {did for did, _ in same_med}

    sent = await deliver_dose_reminder(svc, earliest_id)
    assert sent is True

    post_ids = {did for did, d in doses_map.items() if str(d.get("medication_id")) == saved.id}
    # Threshold was not crossed — sync_and_enqueue_reminders must NOT have fired, so the
    # dose id set is unchanged (no rotation from a fresh sync).
    assert post_ids == pre_ids
