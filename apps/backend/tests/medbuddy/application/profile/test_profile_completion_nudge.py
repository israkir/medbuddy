"""Profile completion footer nudges when onboarding fields are missing."""

from __future__ import annotations

import pytest

from medbuddy.application.profile.profile_completion_nudge import (
    append_profile_completion_nudge_if_due,
)
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
        active_health_condition_count=0,
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
        "emergency_contact": None,
    }
    out = append_profile_completion_nudge_if_due(
        settings=svc.settings,
        user_key="u",
        user_row=row,
        reply="OK",
        locale="en",
        history_before_latest_user_message=[],
        active_health_condition_count=0,
    )
    assert out == "OK"


def test_profile_nudge_skips_when_profile_complete() -> None:
    settings = make_mock_settings(MEDBUDDY_PROFILE_COMPLETION_NUDGE_EVERY_N_USER_TURNS="1")
    svc = build_app_services(settings)
    row = {
        "preferred_name": "Mei",
        "age_years": 70,
        "gender": "female",
        "emergency_contacts": [
            {
                "contact_name": "Son",
                "relationship": "son",
                "channel_type": "phone",
                "channel_value": "0912000333",
                "is_primary": True,
            }
        ],
    }
    out = append_profile_completion_nudge_if_due(
        settings=svc.settings,
        user_key="u",
        user_row=row,
        reply="OK",
        locale="en",
        history_before_latest_user_message=[],
        active_health_condition_count=1,
    )
    assert out == "OK"
