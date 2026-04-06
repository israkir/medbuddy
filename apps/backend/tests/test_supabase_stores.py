"""Unit tests for Supabase-backed ports (client is mocked; no live project)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from medbuddy.integrations.supabase_stores import (
    SupabaseConversationStore,
    SupabaseUserData,
    _parse_ts,
    _user_row_to_dict,
)
from medbuddy.models.domain import ConversationTurn


def test_user_row_to_dict_maps_external_id_to_line_user_id_key() -> None:
    d = _user_row_to_dict(
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "external_user_id": "U-line",
            "consent_accepted": True,
        }
    )
    assert d["id"] == "11111111-1111-1111-1111-111111111111"
    assert d["line_user_id"] == "U-line"
    assert d["consent_accepted"] is True


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
                "consent_accepted": False,
            }
        ]
    )
    client.table.return_value = builder

    ud = SupabaseUserData(client)
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
                    "consent_accepted": False,
                }
            ]
        ),
    ]
    client.table.return_value = builder

    ud = SupabaseUserData(client)
    out = await ud.get_or_create_user("ext-2")
    assert out["id"] == "00000000-0000-0000-0000-000000000002"
    builder.insert.assert_called_once()


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
                "consent_accepted": True,
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

    ud = SupabaseUserData(client)
    store = SupabaseConversationStore(client, ud)
    at = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    await store.append_turn("ext-3", ConversationTurn(role="user", content="hi", at=at))
    turn_builder.insert.assert_called_once()
    call_kw = turn_builder.insert.call_args[0][0]
    assert call_kw["user_id"] == "00000000-0000-0000-0000-000000000003"
    assert call_kw["role"] == "user"
    assert call_kw["content"] == "hi"
