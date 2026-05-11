from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.application.pending.reminder_horizon_resolve import (
    _parse_horizon_days,
    try_resolve_pending_reminder_horizon,
)
from medbuddy.container import build_app_services
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.llm.schemas import MedicationUpdateResolution
from medbuddy.models.domain import Intent, MedicationDraft, ReminderHorizonPending
from tests.helpers import make_mock_settings

# ---------------------------------------------------------------------------
# Unit tests for _parse_horizon_days
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        # digit + unit
        ("7 days", 7),
        ("5 days", 5),
        ("3 天", 3),
        ("14日", 14),
        # word numerals
        ("seven days", 7),
        ("five days", 5),
        ("fourteen days", 14),
        ("七天", 7),
        ("三天", 3),
        # week shortcuts
        ("1 week", 7),
        ("two weeks", 14),
        ("一週", 7),
        # bare integers
        ("7", 7),
        ("  7  ", 7),
        ("yes 7", 7),
        ("about 7 please", None),  # digit in middle of message w/o unit = no match
        # out-of-range
        ("0 days", None),
        ("100 days", None),
        # non-matches
        ("I'm not sure", None),
        ("", None),
    ],
)
def test_parse_horizon_days(text: str, expected: int | None) -> None:
    assert _parse_horizon_days(text) == expected


# ---------------------------------------------------------------------------
# Expired pending returns an ack string instead of None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_horizon_pending_returns_ack() -> None:
    settings = make_mock_settings(MEDBUDDY_LOCALE="en")
    svc = build_app_services(settings)
    key = "U-reminder-horizon-expired-ack"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})

    saved = await svc.users.add_medication(
        key,
        MedicationDraft(
            name="Vitamin C",
            dosage="500mg",
            schedule="once daily",
            needs_horizon_confirmation=True,
        ),
    )
    await svc.users.set_reminder_horizon_pending(
        key,
        ReminderHorizonPending(
            medication_id=saved.id,
            medication_name=saved.name,
            # already expired
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        ),
    )

    reply = await try_resolve_pending_reminder_horizon(
        svc, user_key=key, user_text="7 days", locale="en"
    )
    assert reply is not None
    assert "expired" in reply.lower() or "Vitamin C" in reply
    # Pending state must be cleared
    assert await svc.users.get_reminder_horizon_pending(key) is None


# ---------------------------------------------------------------------------
# Word-numeral "seven days" resolves correctly end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_word_numeral_seven_days_resolves() -> None:
    settings = make_mock_settings(MEDBUDDY_LOCALE="en")
    svc = build_app_services(settings)
    key = "U-reminder-horizon-word-numeral"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en", "timezone": "Asia/Taipei"})

    saved = await svc.users.add_medication(
        key,
        MedicationDraft(
            name="Aspirin",
            dosage="100mg",
            schedule="once daily after breakfast",
            needs_horizon_confirmation=True,
        ),
    )
    await svc.users.set_reminder_horizon_pending(
        key,
        ReminderHorizonPending(
            medication_id=saved.id,
            medication_name=saved.name,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        ),
    )

    reply = await try_resolve_pending_reminder_horizon(
        svc, user_key=key, user_text="seven days", locale="en"
    )
    assert reply is not None
    assert "7 day" in reply.lower() or "seven" in reply.lower()
    assert await svc.users.get_reminder_horizon_pending(key) is None


@pytest.mark.asyncio
async def test_update_then_horizon_days_materializes_dose_events() -> None:
    settings = make_mock_settings(MEDBUDDY_LOCALE="en")
    svc = build_app_services(settings)
    key = "U-reminder-horizon-update-then-days"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en", "timezone": "Asia/Taipei"})

    saved = await svc.users.add_medication(
        key,
        MedicationDraft(
            name="Vitamin C",
            dosage="Unspecified",
            schedule="Unspecified",
            needs_horizon_confirmation=True,
        ),
    )
    await svc.users.set_reminder_horizon_pending(
        key,
        ReminderHorizonPending(
            medication_id=saved.id,
            medication_name=saved.name,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        ),
    )

    svc.llm = MockLLM(
        intent=Intent.UPDATE_MEDICATION,
        locale="en",
        medication_update=MedicationUpdateResolution(
            medication_id=saved.id,
            name=None,
            dosage="100mg",
            schedule="every day at noon",
            instructions=None,
            clear_instructions=False,
        ),
    )
    await run_assistant_text_turn(svc, user_key=key, user_text="everyday 100mg one pill at noon")
    assert await svc.users.get_reminder_horizon_pending(key) is not None

    svc.llm = MockLLM(intent=Intent.GENERAL_QUESTION, locale="en")
    reply = (await run_assistant_text_turn(svc, user_key=key, user_text="7 days")).reply
    assert "7 day" in reply.lower()
    assert await svc.users.get_reminder_horizon_pending(key) is None

    meds = await svc.users.list_medications(key)
    assert len(meds) == 1
    reminder = meds[0].raw_metadata.get("reminder") or {}
    assert reminder.get("needs_horizon_confirmation") is False
    assert reminder.get("materialize_daily") is True
    assert reminder.get("horizon_days") == 7

    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert len(jobs) > 0


@pytest.mark.asyncio
async def test_horizon_merge_failure_keeps_pending_and_returns_none() -> None:
    settings = make_mock_settings(MEDBUDDY_LOCALE="en")
    svc = build_app_services(settings)
    key = "U-reminder-horizon-merge-fail"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})

    saved = await svc.users.add_medication(
        key,
        MedicationDraft(
            name="Vitamin C",
            dosage="Unspecified",
            schedule="Unspecified",
            needs_horizon_confirmation=True,
        ),
    )
    await svc.users.set_reminder_horizon_pending(
        key,
        ReminderHorizonPending(
            medication_id=saved.id,
            medication_name=saved.name,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        ),
    )

    async def _merge_fail(
        line_user_id: str, medication_id: str, reminder_patch: dict[str, object]
    ) -> None:
        _ = (line_user_id, medication_id, reminder_patch)
        return None

    svc.users.merge_medication_raw_metadata = _merge_fail  # type: ignore[method-assign]

    reply = await try_resolve_pending_reminder_horizon(
        svc,
        user_key=key,
        user_text="7 days",
        locale="en",
    )
    assert reply is None
    assert await svc.users.get_reminder_horizon_pending(key) is not None
