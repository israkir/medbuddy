"""Unit tests for Supabase-backed ports (client is mocked; no live project)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from medbuddy.config import load_settings
from medbuddy.integrations.persistence.supabase_client import create_supabase_client
from medbuddy.integrations.persistence.supabase_conversations import SupabaseConversationStore
from medbuddy.integrations.persistence.supabase_dose_events import _parse_ts
from medbuddy.integrations.persistence.supabase_profile import _user_row_to_dict
from medbuddy.integrations.persistence.supabase_stores import SupabaseUserData
from medbuddy.models.domain import ConversationTurn, MedicationDraft


def test_create_supabase_client_disables_http2(monkeypatch: pytest.MonkeyPatch) -> None:
    """postgrest-py defaults to HTTP/2; we pass httpx.Client(http2=False) for stability."""
    pytest.importorskip("supabase")

    kwargs_captured: dict = {}

    def fake_httpx_client(**kwargs: object) -> MagicMock:
        kwargs_captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr("httpx.Client", fake_httpx_client)
    monkeypatch.setattr("supabase.create_client", lambda *a, **k: MagicMock())

    create_supabase_client(
        load_settings(
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "anon-key",
            }
        )
    )
    assert kwargs_captured.get("http2") is False
    assert kwargs_captured.get("follow_redirects") is True


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
        "emergency_contacts",
        "health_notes",
        "onboarding_completed_at",
        "timezone",
        "locale",
    }
    assert d["timezone"] == "Asia/Taipei"
    assert d["locale"] == "zh-TW"
    assert d["emergency_contacts"] == []


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

    ud = SupabaseUserData(client, load_settings({}))
    out = await ud.get_or_create_user("ext-1")
    assert out["id"] == "00000000-0000-0000-0000-000000000001"
    client.table.assert_any_call("patients")
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

    ud = SupabaseUserData(client, load_settings({}))
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
        if name == "patients":
            return user_builder
        if name == "conversation_turns":
            return turn_builder
        return MagicMock()

    client = MagicMock()
    client.table.side_effect = table

    ud = SupabaseUserData(client, load_settings({}))
    store = SupabaseConversationStore(client, ud)
    at = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    await store.append_turn("ext-3", ConversationTurn(role="user", content="hi", at=at))
    turn_builder.insert.assert_called_once()
    call_kw = turn_builder.insert.call_args[0][0]
    assert call_kw["patient_id"] == "00000000-0000-0000-0000-000000000003"
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
                "instructions": None,
                "raw_metadata": {},
            }
        ]
    )

    def table(name: str) -> MagicMock:
        if name == "patients":
            return user_builder
        if name == "medications":
            return med_builder
        return MagicMock()

    client = MagicMock()
    client.table.side_effect = table

    ud = SupabaseUserData(client, load_settings({}))
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

    contacts_builder = MagicMock()
    contacts_builder.select.return_value = contacts_builder
    contacts_builder.eq.return_value = contacts_builder
    contacts_builder.neq.return_value = contacts_builder
    contacts_builder.order.return_value = contacts_builder
    contacts_builder.limit.return_value = contacts_builder
    contacts_builder.insert.return_value = contacts_builder
    contacts_builder.update.return_value = contacts_builder
    contacts_builder.delete.return_value = contacts_builder
    contacts_builder.execute.return_value = MagicMock(
        data=[{"id": "00000000-0000-0000-0000-0000000000aa"}]
    )

    client = MagicMock()

    def table(name: str) -> MagicMock:
        if name == "emergency_contacts":
            return contacts_builder
        return user_builder

    client.table.side_effect = table

    ud = SupabaseUserData(client, load_settings({}))
    out = await ud.save_onboarding_profile(
        "ext-onb",
        preferred_name="May",
        age_years=72,
        gender="female",
        emergency_contacts=[
            {"relationship": "son", "channel_type": "phone", "channel_value": "0912"}
        ],
        health_notes="DM",
        locale="en",
    )
    assert out["preferred_name"] == "May"
    assert out["age_years"] == 72
    assert out["gender"] == "female"
    user_builder.update.assert_called_once()
    upd = user_builder.update.call_args[0][0]
    assert upd["preferred_name"] == "May"
    assert upd["age_years"] == 72
    assert upd["gender"] == "female"
    assert upd["timezone"] == "Asia/Taipei"
    assert upd["locale"] == "en"
    contacts_builder.insert.assert_called_once()
    insert_payload = contacts_builder.insert.call_args[0][0]
    assert insert_payload["channel_type"] == "phone"
    assert insert_payload["channel_value"] == "0912"


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

    ud = SupabaseUserData(client, load_settings({}))
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
        if name == "patients":
            return user_builder
        if name == "medications":
            return med_builder
        return MagicMock()

    client = MagicMock()
    client.table.side_effect = table

    ud = SupabaseUserData(client, load_settings({}))
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

    ud = SupabaseUserData(client, load_settings({}))
    out = await ud.patch_user_profile("ext-g", {"gender": "male"})
    assert out["gender"] == "male"
    upd = user_builder.update.call_args[0][0]
    assert upd == {"gender": "male"}


@pytest.mark.asyncio
async def test_patch_user_profile_emergency_contacts_demotes_old_primary() -> None:
    """New emergency contact is appended; previously stored row is demoted to non-primary."""
    user_id = "00000000-0000-0000-0000-0000000000ab"
    patient_row = {
        "id": user_id,
        "external_user_id": "ext-merge",
        "preferred_name": None,
        "age_years": None,
        "gender": None,
        "health_notes": None,
        "onboarding_completed_at": None,
        "timezone": "Asia/Taipei",
        "locale": "zh-TW",
    }
    user_builder = MagicMock()
    user_builder.select.return_value = user_builder
    user_builder.eq.return_value = user_builder
    user_builder.limit.return_value = user_builder
    user_builder.update.return_value = user_builder
    user_builder.execute.return_value = MagicMock(data=[patient_row])

    contacts_builder = MagicMock()
    contacts_builder.select.return_value = contacts_builder
    contacts_builder.eq.return_value = contacts_builder
    contacts_builder.neq.return_value = contacts_builder
    contacts_builder.order.return_value = contacts_builder
    contacts_builder.limit.return_value = contacts_builder
    contacts_builder.insert.return_value = contacts_builder
    contacts_builder.update.return_value = contacts_builder

    existing_primary_id = "00000000-0000-0000-0000-0000000000cc"
    new_inserted_id = "00000000-0000-0000-0000-0000000000dd"
    existing_row = {
        "id": existing_primary_id,
        "contact_name": None,
        "relationship": "son",
        "channel_type": "phone",
        "channel_value": "0900000000",
        "is_primary": True,
        "notes": None,
        "source": "user",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    contacts_builder.execute.side_effect = [
        MagicMock(data=[existing_row]),
        MagicMock(data=[existing_row]),
        MagicMock(data=[{"id": new_inserted_id}]),
        MagicMock(data=[{"id": new_inserted_id}]),
        MagicMock(data=[]),
        MagicMock(data=[{"id": new_inserted_id}]),
        MagicMock(data=[existing_row]),
    ]

    client = MagicMock()

    def table(name: str) -> MagicMock:
        if name == "emergency_contacts":
            return contacts_builder
        return user_builder

    client.table.side_effect = table

    ud = SupabaseUserData(client, load_settings({}))
    await ud.patch_user_profile(
        "ext-merge",
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

    contacts_builder.insert.assert_called_once()
    insert_payload = contacts_builder.insert.call_args[0][0]
    assert insert_payload["channel_type"] == "line"
    assert insert_payload["channel_value"] == "kathy_line"
    assert insert_payload["is_primary"] is False

    update_calls = contacts_builder.update.call_args_list
    update_payloads = [c.args[0] for c in update_calls]
    assert any(
        p == {"is_primary": False} for p in update_payloads
    ), "expected demote-others update to set is_primary=False"
    assert any(
        p == {"is_primary": True} for p in update_payloads
    ), "expected promote-latest update to set is_primary=True"
