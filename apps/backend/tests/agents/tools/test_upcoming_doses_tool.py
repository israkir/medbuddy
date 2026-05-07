"""ListUpcomingDosesTool reads dose_events in time order."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from medbuddy.agents.tools.upcoming_doses import ListUpcomingDosesTool
from tests.helpers import make_mock_settings
from medbuddy.container import build_app_services
from medbuddy.integrations.mocks.users import MockUserData
from medbuddy.models.domain import MedicationDraft
from medbuddy.reminders.upcoming_display import upcoming_schedule_window_utc


@pytest.mark.asyncio
async def test_upcoming_doses_tool_lists_ordered_pending() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    assert isinstance(svc.users, MockUserData)
    key = "u-upcoming"
    await svc.users.get_or_create_user(key)
    draft = MedicationDraft(
        name="Aspirin",
        dosage="100mg",
        schedule="once daily",
        daily_reminder_local_hhmm="09:00",
    )
    await svc.users.add_medication(key, draft)
    await svc.users.sync_upcoming_dose_events(key)

    tool = ListUpcomingDosesTool()
    user_row = await svc.users.get_or_create_user(key)
    user_row = dict(user_row)
    user_row["timezone"] = "UTC"
    out = await tool.run(svc=svc, user_key=key, user_row=user_row, locale="en")
    assert "Aspirin" in out.reply
    assert "09:00" in out.reply or "100mg" in out.reply


@pytest.mark.asyncio
async def test_list_upcoming_dose_events_respects_window() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    assert isinstance(svc.users, MockUserData)
    key = "u-window"
    row = await svc.users.get_or_create_user(key)
    uid = row["id"]
    # Inject dose_events manually (bypass medication row / sync)
    now = datetime.now(UTC)
    inside = now + timedelta(hours=2)
    far = now + timedelta(days=10)
    svc.users._doses["e1"] = {  # noqa: SLF001
        "line_user_id": key,
        "user_internal_id": uid,
        "name": "Med",
        "dosage": "1",
        "schedule": "daily",
        "scheduled_at": inside,
        "taken_at": None,
        "missed_at": None,
    }
    svc.users._doses["e2"] = {  # noqa: SLF001
        "line_user_id": key,
        "user_internal_id": uid,
        "name": "Med",
        "dosage": "1",
        "schedule": "daily",
        "scheduled_at": far,
        "taken_at": None,
        "missed_at": None,
    }
    start, end = upcoming_schedule_window_utc("UTC", now, horizon_days=7)
    rows = await svc.users.list_upcoming_dose_events(
        key, from_utc=start, until_utc_exclusive=end, max_items=50
    )
    ids = {r.dose_event_id for r in rows}
    assert "e1" in ids
    assert "e2" not in ids


def test_map_intent_upcoming_doses() -> None:
    from medbuddy.llm.intent_map import map_intent_label
    from medbuddy.models.domain import Intent

    assert map_intent_label("upcoming_doses") == Intent.UPCOMING_DOSES
