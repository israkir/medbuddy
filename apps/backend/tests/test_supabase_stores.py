"""Unit tests for Supabase-backed ports (client is mocked; no live project)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from medbuddy.config import Settings
from medbuddy.integrations.supabase_stores import (
    SupabaseConversationStore,
    SupabaseUserData,
    _parse_ts,
    _user_row_to_dict,
)
from medbuddy.models.domain import ConversationTurn, MedicationDraft


def test_user_row_to_dict_maps_external_id_to_line_user_id_key() -> None:
    d = _user_row_to_dict(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "external_user_id": "U-line",
        }
    )
    assert d["id"] == "11111111-1111-1111-1111-111111111111"
    assert d["line_user_id"] == "U-line"
    assert d["preferred_name"] is None
    assert d["gender"] is None
    assert d["onboarding_completed_at"] is None
    assert set(d.keys()) == {
        "id",
        "line_user_id",
        "preferred_name",
        "age_years",
        "gender",
        "emergency_contact",
        "health_notes",
        "onboarding_completed_at",
        "timezone",
    }
    assert d["timezone"] == "Asia/Taipei"


def test_parse_ts_iso_z() -> None:
    t = _parse_ts("2026-04-07T12:00:00Z")
    assert t.tzinfo is not None
    assert t.year == 2026


@pytest.mark.asyncio
async def test_get_or_create_user_uses_existing_row() -> None:
    client = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.limit.return_value = builder
    builder.execute.return_value = MagicMock(
        data=[
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "external_user_id": "ext-1",
            }
        ]
    )
    client.table.return_value = builder

    ud = SupabaseUserData(client, Settings())
    out = await ud.get_or_create_user("ext-1")
    assert out["id"] == "00000000-0000-0000-0000-000000000001"
    client.table.assert_called_with("users")
    builder.insert.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_user_inserts_when_missing() -> None:
    client = MagicMock()
    builder = MagicMock()
    builder.select.return_value = builder
    builder.eq.return_value = builder
    builder.limit.return_value = builder
    builder.insert.return_value = builder
    builder.execute.side_effect = [
        MagicMock(data=[]),
        MagicMock(
            data=[
                {
                    "id": "00000000-0000-0000-0000-000000000002",
                    "external_user_id": "ext-2",
                }
            ]
        ),
    ]
    client.table.return_value = builder

    ud = SupabaseUserData(client, Settings())
    out = await ud.get_or_create_user("ext-2")
    assert out["id"] == "00000000-0000-0000-0000-000000000002"
    builder.insert.assert_called_once()
    ins = builder.insert.call_args[0][0]
    assert ins == {"external_user_id": "ext-2"}


@pytest.mark.asyncio
async def test_append_turn_inserts_with_resolved_user_id() -> None:
    user_builder = MagicMock()
    user_builder.select.return_value = user_builder
    user_builder.eq.return_value = user_builder
    user_builder.limit.return_value = user_builder
    user_builder.execute.return_value = MagicMock(
        data=[
            {
                "id": "00000000-0000-0000-0000-000000000003",
                "external_user_id": "ext-3",
            }
        ]
    )

    turn_builder = MagicMock()
    turn_builder.insert.return_value = turn_builder
    turn_builder.execute.return_value = MagicMock(data=[{"id": 1}])

    def table(name: str) -> MagicMock:
        if name == "users":
            return user_builder
        if name == "conversation_turns":
            return turn_builder
        return MagicMock()

    client = MagicMock()
    client.table.side_effect = table

    ud = SupabaseUserData(client, Settings())
    store = SupabaseConversationStore(client, ud)
    at = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    await store.append_turn("ext-3", ConversationTurn(role="user", content="hi", at=at))
    turn_builder.insert.assert_called_once()
    call_kw = turn_builder.insert.call_args[0][0]
    assert call_kw["user_id"] == "00000000-0000-0000-0000-000000000003"
    assert call_kw["role"] == "user"
    assert call_kw["content"] == "hi"
    assert call_kw["created_at"] == at.isoformat()


@pytest.mark.asyncio
async def test_add_medication_inserts_row() -> None:
    user_builder = MagicMock()
    user_builder.select.return_value = user_builder
    user_builder.eq.return_value = user_builder
    user_builder.limit.return_value = user_builder
    user_builder.execute.return_value = MagicMock(
        data=[
            {
                "id": "00000000-0000-0000-0000-000000000010",
                "external_user_id": "ext-med",
            }
        ]
    )

    med_builder = MagicMock()
    med_builder.insert.return_value = med_builder
    med_builder.execute.return_value = MagicMock(
        data=[
            {
                "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "name": "Aspirin",
                "dosage": "100mg",
                "schedule": "after meal",
                "instructions_zh": None,
                "raw_metadata": {},
            }
        ]
    )

    def table(name: str) -> MagicMock:
        if name == "users":
            return user_builder
        if name == "medications":
            return med_builder
        return MagicMock()

    client = MagicMock()
    client.table.side_effect = table

    ud = SupabaseUserData(client, Settings())
    rec = await ud.add_medication(
        "ext-med",
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="after meal"),
    )
    assert rec.name == "Aspirin"
    med_builder.insert.assert_called_once()


@pytest.mark.asyncio
async def test_save_onboarding_profile_updates_row() -> None:
    user_builder = MagicMock()
    user_builder.select.return_value = user_builder
    user_builder.eq.return_value = user_builder
    user_builder.limit.return_value = user_builder
    user_builder.update.return_value = user_builder
    user_builder.execute.side_effect = [
        MagicMock(
            data=[
                {
                    "id": "00000000-0000-0000-0000-000000000099",
                    "external_user_id": "ext-onb",
                    "preferred_name": None,
                    "age_years": None,
                    "gender": None,
                    "emergency_contact": None,
                    "health_notes": None,
                    "onboarding_completed_at": None,
                }
            ]
        ),
        MagicMock(data=[{"id": "00000000-0000-0000-0000-000000000099"}]),
        MagicMock(
            data=[
                {
                    "id": "00000000-0000-0000-0000-000000000099",
                    "external_user_id": "ext-onb",
                    "preferred_name": "May",
                    "age_years": 72,
                    "gender": "female",
                    "emergency_contact": "son 0912",
                    "health_notes": "DM",
                    "onboarding_completed_at": "2026-04-07T12:00:00+00:00",
                }
            ]
        ),
    ]

    client = MagicMock()
    client.table.return_value = user_builder

    ud = SupabaseUserData(client, Settings())
    out = await ud.save_onboarding_profile(
        "ext-onb",
        preferred_name="May",
        age_years=72,
        gender="female",
        emergency_contact="son 0912",
        health_notes="DM",
    )
    assert out["preferred_name"] == "May"
    assert out["age_years"] == 72
    assert out["gender"] == "female"
    user_builder.update.assert_called_once()
    upd = user_builder.update.call_args[0][0]
    assert upd["preferred_name"] == "May"
    assert upd["age_years"] == 72
    assert upd["gender"] == "female"


@pytest.mark.asyncio
async def test_patch_user_profile_merges_fields() -> None:
    user_builder = MagicMock()
    user_builder.select.return_value = user_builder
    user_builder.eq.return_value = user_builder
    user_builder.limit.return_value = user_builder
    user_builder.update.return_value = user_builder
    user_builder.execute.side_effect = [
        MagicMock(
            data=[
                {
                    "id": "00000000-0000-0000-0000-000000000088",
                    "external_user_id": "ext-patch",
                    "preferred_name": None,
                    "age_years": None,
                    "emergency_contact": None,
                    "health_notes": None,
                    "onboarding_completed_at": None,
                }
            ]
        ),
        MagicMock(data=[{"id": "00000000-0000-0000-0000-000000000088"}]),
        MagicMock(
            data=[
                {
                    "id": "00000000-0000-0000-0000-000000000088",
                    "external_user_id": "ext-patch",
                    "preferred_name": "Lin",
                    "age_years": 68,
                    "emergency_contact": None,
                    "health_notes": None,
                    "onboarding_completed_at": None,
                }
            ]
        ),
    ]

    client = MagicMock()
    client.table.return_value = user_builder

    ud = SupabaseUserData(client, Settings())
    out = await ud.patch_user_profile(
        "ext-patch",
        {"preferred_name": "Lin", "age_years": 68},
    )
    assert out["preferred_name"] == "Lin"
    assert out["age_years"] == 68
    user_builder.update.assert_called_once()
    upd = user_builder.update.call_args[0][0]
    assert upd == {"preferred_name": "Lin", "age_years": 68}


@pytest.mark.asyncio
async def test_delete_medication_deletes_when_match() -> None:
    user_builder = MagicMock()
    user_builder.select.return_value = user_builder
    user_builder.eq.return_value = user_builder
    user_builder.limit.return_value = user_builder
    user_builder.execute.return_value = MagicMock(
        data=[
            {
                "id": "00000000-0000-0000-0000-000000000011",
                "external_user_id": "ext-del",
            }
        ]
    )

    med_builder = MagicMock()
    med_builder.delete.return_value = med_builder
    med_builder.eq.return_value = med_builder
    med_builder.execute.return_value = MagicMock(
        data=[{"id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}]
    )

    def table(name: str) -> MagicMock:
        if name == "users":
            return user_builder
        if name == "medications":
            return med_builder
        return MagicMock()

    client = MagicMock()
    client.table.side_effect = table

    ud = SupabaseUserData(client, Settings())
    ok = await ud.delete_medication("ext-del", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    assert ok is True
    med_builder.delete.assert_called_once()


@pytest.mark.asyncio
async def test_patch_user_profile_accepts_gender() -> None:
    user_builder = MagicMock()
    user_builder.select.return_value = user_builder
    user_builder.eq.return_value = user_builder
    user_builder.limit.return_value = user_builder
    user_builder.update.return_value = user_builder
    user_builder.execute.side_effect = [
        MagicMock(
            data=[
                {
                    "id": "00000000-0000-0000-0000-000000000077",
                    "external_user_id": "ext-g",
                    "preferred_name": None,
                    "age_years": None,
                    "gender": None,
                    "emergency_contact": None,
                    "health_notes": None,
                    "onboarding_completed_at": None,
                }
            ]
        ),
        MagicMock(data=[{"id": "00000000-0000-0000-0000-000000000077"}]),
        MagicMock(
            data=[
                {
                    "id": "00000000-0000-0000-0000-000000000077",
                    "external_user_id": "ext-g",
                    "preferred_name": None,
                    "age_years": None,
                    "gender": "male",
                    "emergency_contact": None,
                    "health_notes": None,
                    "onboarding_completed_at": None,
                }
            ]
        ),
    ]

    client = MagicMock()
    client.table.return_value = user_builder

    ud = SupabaseUserData(client, Settings())
    out = await ud.patch_user_profile("ext-g", {"gender": "male"})
    assert out["gender"] == "male"
    upd = user_builder.update.call_args[0][0]
    assert upd == {"gender": "male"}
