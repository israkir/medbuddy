"""Supabase (Postgres) implementations of user and conversation persistence."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from medbuddy.config import Settings
from medbuddy.models.domain import ConversationTurn, MedicationDraft, MedicationRecord
from medbuddy.protocols.ports import ConversationStorePort, UserDataPort

log = logging.getLogger(__name__)


def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(s)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    msg = f"Unsupported timestamp value from DB: {type(value)}"
    raise TypeError(msg)


def _user_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "line_user_id": row["external_user_id"],
    }


def _med_row_to_record(row: dict[str, Any]) -> MedicationRecord:
    raw = row.get("raw_metadata")
    if not isinstance(raw, dict):
        raw = {}
    ins = row.get("instructions_zh")
    return MedicationRecord(
        id=str(row["id"]),
        name=row["name"],
        dosage=row["dosage"],
        schedule=row["schedule"],
        instructions_zh=ins if isinstance(ins, str) or ins is None else str(ins),
        raw_metadata=raw,
    )


def create_supabase_client(settings: Settings) -> Any:
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_publishable_key)


def _run_q(fn: Any) -> Any:
    return asyncio.to_thread(fn)


class SupabaseUserData(UserDataPort):
    """Users + medications backed by Supabase Postgres."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def _select_user_row(self, external_user_id: str) -> dict[str, Any] | None:
        def q() -> Any:
            return (
                self._client.table("users")
                .select("id, external_user_id")
                .eq("external_user_id", external_user_id)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return rows[0] if rows else None

    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]:
        row = await self._select_user_row(line_user_id)
        if row:
            return _user_row_to_dict(row)

        def insert() -> Any:
            return self._client.table("users").insert({"external_user_id": line_user_id}).execute()

        try:
            resp = await _run_q(insert)
        except Exception as e:  # noqa: BLE001 — PostgREST / httpx errors vary by version
            msg = str(e).lower()
            if "duplicate" in msg or "unique" in msg or "23505" in msg:
                row = await self._select_user_row(line_user_id)
                if row:
                    return _user_row_to_dict(row)
            log.warning("Supabase user insert failed: %s", e)
            raise

        rows = resp.data or []
        if not rows:
            row = await self._select_user_row(line_user_id)
            if not row:
                msg = "Supabase insert returned no row"
                raise RuntimeError(msg)
            return _user_row_to_dict(row)
        return _user_row_to_dict(rows[0])

    async def list_medications(self, line_user_id: str) -> list[MedicationRecord]:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]

        def q() -> Any:
            return (
                self._client.table("medications")
                .select("id, name, dosage, schedule, instructions_zh, raw_metadata")
                .eq("user_id", uid)
                .order("id")
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return [_med_row_to_record(r) for r in rows]

    async def add_medication(self, line_user_id: str, draft: MedicationDraft) -> MedicationRecord:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        ins = (draft.instructions_zh or "").strip()
        payload: dict[str, Any] = {
            "user_id": uid,
            "name": draft.name.strip(),
            "dosage": draft.dosage.strip(),
            "schedule": draft.schedule.strip(),
            "instructions_zh": ins or None,
            "raw_metadata": {},
        }

        def insert() -> Any:
            return self._client.table("medications").insert(payload).execute()

        resp = await _run_q(insert)
        rows = resp.data or []
        if not rows:
            msg = "Supabase medication insert returned no row"
            raise RuntimeError(msg)
        return _med_row_to_record(rows[0])

    async def delete_medication(self, line_user_id: str, medication_id: str) -> bool:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]

        def q() -> Any:
            return (
                self._client.table("medications")
                .delete()
                .eq("user_id", uid)
                .eq("id", medication_id)
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return len(rows) > 0


class SupabaseConversationStore(ConversationStorePort):
    """Conversation turns keyed by the same external user id as ``SupabaseUserData``."""

    def __init__(self, client: Any, users: SupabaseUserData) -> None:
        self._client = client
        self._users = users

    async def get_recent_turns(self, line_user_id: str, max_turns: int) -> list[ConversationTurn]:
        user = await self._users.get_or_create_user(line_user_id)
        uid = user["id"]
        if max_turns <= 0:
            return []

        def q() -> Any:
            return (
                self._client.table("conversation_turns")
                .select("role, content, created_at")
                .eq("user_id", uid)
                .order("created_at", desc=True)
                .limit(max_turns)
                .execute()
            )

        resp = await _run_q(q)
        rows = list(reversed(resp.data or []))
        return [
            ConversationTurn(role=r["role"], content=r["content"], at=_parse_ts(r["created_at"]))
            for r in rows
        ]

    async def append_turn(self, line_user_id: str, turn: ConversationTurn) -> None:
        user = await self._users.get_or_create_user(line_user_id)
        uid = user["id"]
        at = turn.at
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        payload = {
            "user_id": uid,
            "role": turn.role,
            "content": turn.content,
            "created_at": at.isoformat(),
        }

        def q() -> Any:
            return self._client.table("conversation_turns").insert(payload).execute()

        await _run_q(q)
