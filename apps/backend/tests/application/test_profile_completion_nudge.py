"""Profile completion footer nudges when onboarding fields are missing."""

from __future__ import annotations

import pytest

from medbuddy.application.profile_completion_nudge import append_profile_completion_nudge_if_due
from medbuddy.container import build_app_services
from tests.helpers import make_mock_settings


@pytest.mark.asyncio
async def test_profile_nudge_appends_when_due_and_gaps_exist() -> None:
    settings = make_mock_settings(MEDBUDDY_PROFILE_COMPLETION_NUDGE_EVERY_N_USER_TURNS="1")
    svc = build_app_services(settings)
    uid = "u-nudge-1"
    row = await svc.users.get_or_create_user(uid)

    out = append_profile_completion_nudge_if_due(
        settings=svc.settings,
        user_key=uid,
        user_row=row,
        reply="Added your reminder.",
        locale="en",
        history_before_latest_user_message=[],
    )
    assert "💡" in out
    assert "Added your reminder." in out
    assert out.startswith("Added your reminder.")


def test_profile_nudge_skips_when_interval_zero() -> None:
    settings = make_mock_settings(MEDBUDDY_PROFILE_COMPLETION_NUDGE_EVERY_N_USER_TURNS="0")
    svc = build_app_services(settings)
    row = {
        "preferred_name": None,
        "age_years": None,
        "gender": None,
        "health_notes": None,
        "emergency_contact": None,
    }
    out = append_profile_completion_nudge_if_due(
        settings=svc.settings,
        user_key="u",
        user_row=row,
        reply="OK",
        locale="en",
        history_before_latest_user_message=[],
    )
    assert out == "OK"


def test_profile_nudge_skips_when_profile_complete() -> None:
    settings = make_mock_settings(MEDBUDDY_PROFILE_COMPLETION_NUDGE_EVERY_N_USER_TURNS="1")
    svc = build_app_services(settings)
    row = {
        "preferred_name": "Mei",
        "age_years": 70,
        "gender": "female",
        "health_notes": "NKDA",
        "emergency_contact": "son 0912000333",
    }
    out = append_profile_completion_nudge_if_due(
        settings=svc.settings,
        user_key="u",
        user_row=row,
        reply="OK",
        locale="en",
        history_before_latest_user_message=[],
    )
    assert out == "OK"
