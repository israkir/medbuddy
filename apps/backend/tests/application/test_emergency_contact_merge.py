"""Merge helper + multi-contact notification behavior for emergency contacts."""

from __future__ import annotations

import pytest

from medbuddy.application.profile.emergency_contacts import (
    emergency_contacts_hint_all,
    merge_emergency_contacts,
)
from medbuddy.config import load_settings
from medbuddy.integrations.mocks.users import MockUserData


def test_merge_into_empty_marks_last_input_as_primary() -> None:
    out = merge_emergency_contacts(
        [],
        [
            {
                "channel_type": "phone",
                "channel_value": "0900000000",
                "relationship": "son",
            },
            {
                "channel_type": "phone",
                "channel_value": "0911111111",
                "relationship": "daughter",
            },
        ],
    )
    assert len(out) == 2
    assert out[0]["is_primary"] is True
    assert out[0]["channel_value"] == "0911111111"
    assert out[1]["is_primary"] is False
    assert out[1]["channel_value"] == "0900000000"


def test_merge_appends_and_demotes_old_primary() -> None:
    existing = [
        {
            "channel_type": "phone",
            "channel_value": "0900000000",
            "relationship": "son",
            "is_primary": True,
        },
    ]
    new = [
        {
            "channel_type": "line",
            "channel_value": "kathy_line",
            "relationship": "daughter",
        }
    ]
    out = merge_emergency_contacts(existing, new)
    assert len(out) == 2
    assert out[0]["channel_type"] == "line"
    assert out[0]["channel_value"] == "kathy_line"
    assert out[0]["is_primary"] is True
    assert out[1]["channel_type"] == "phone"
    assert out[1]["is_primary"] is False


def test_merge_dedupes_same_channel_and_refreshes_primary() -> None:
    existing = [
        {
            "channel_type": "phone",
            "channel_value": "0900000000",
            "relationship": "son",
            "is_primary": True,
        },
        {
            "channel_type": "line",
            "channel_value": "kathy_line",
            "relationship": "daughter",
            "is_primary": False,
        },
    ]
    new = [
        {
            "channel_type": "phone",
            "channel_value": "0900000000",
            "relationship": "son",
            "contact_name": "Dan",
        }
    ]
    out = merge_emergency_contacts(existing, new)
    assert len(out) == 2
    primary = out[0]
    assert primary["channel_type"] == "phone"
    assert primary["channel_value"] == "0900000000"
    assert primary["is_primary"] is True
    assert primary.get("contact_name") == "Dan"
    other = out[1]
    assert other["channel_type"] == "line"
    assert other["is_primary"] is False


def test_emergency_contacts_hint_all_lists_each_contact_en() -> None:
    contacts = [
        {
            "channel_type": "line",
            "channel_value": "kathy_line",
            "relationship": "daughter",
            "is_primary": True,
        },
        {
            "channel_type": "phone",
            "channel_value": "0900000000",
            "relationship": "son",
            "is_primary": False,
        },
    ]
    hint = emergency_contacts_hint_all(contacts, locale="en")
    assert "daughter kathy_line" in hint
    assert "son 0900000000" in hint
    assert "; " in hint


def test_emergency_contacts_hint_all_uses_zh_separator() -> None:
    contacts = [
        {
            "channel_type": "phone",
            "channel_value": "0911111111",
            "relationship": "女兒",
            "is_primary": True,
        },
        {
            "channel_type": "phone",
            "channel_value": "0900000000",
            "relationship": "兒子",
            "is_primary": False,
        },
    ]
    hint = emergency_contacts_hint_all(contacts, locale="zh-TW")
    assert "女兒 0911111111" in hint
    assert "兒子 0900000000" in hint
    assert "；" in hint


@pytest.mark.asyncio
async def test_mock_store_appends_contacts_and_keeps_only_latest_primary() -> None:
    store = MockUserData(load_settings({}))
    await store.get_or_create_user("U-multi")
    await store.patch_user_profile(
        "U-multi",
        {
            "emergency_contacts": [
                {
                    "channel_type": "phone",
                    "channel_value": "0900000000",
                    "relationship": "son",
                    "is_primary": True,
                }
            ]
        },
    )
    await store.patch_user_profile(
        "U-multi",
        {
            "emergency_contacts": [
                {
                    "channel_type": "line",
                    "channel_value": "kathy_line",
                    "relationship": "daughter",
                }
            ]
        },
    )
    user = await store.get_or_create_user("U-multi")
    contacts = user["emergency_contacts"]
    assert len(contacts) == 2
    assert contacts[0]["channel_type"] == "line"
    assert contacts[0]["is_primary"] is True
    assert contacts[1]["channel_type"] == "phone"
    assert contacts[1]["is_primary"] is False
