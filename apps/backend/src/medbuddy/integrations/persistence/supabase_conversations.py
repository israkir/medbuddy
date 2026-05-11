"""Supabase implementation of ConversationStorePort."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from medbuddy.models.domain import ConversationTurn
from medbuddy.protocols import ConversationStorePort

log = logging.getLogger(__name__)


def _run_q(fn: Any) -> Any:
    return asyncio.to_thread(fn)


def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(s)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    msg = f"Unsupported timestamp value from DB: {type(value)}"
    raise TypeError(msg)


class SupabaseConversationStore(ConversationStorePort):
    """Conversation turns keyed by the same external user id as ``SupabaseUserData``."""

    def __init__(self, client: Any, users: Any) -> None:
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
                .eq("patient_id", uid)
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
            "patient_id": uid,
            "role": turn.role,
            "content": turn.content,
            "created_at": at.isoformat(),
        }

        def q() -> Any:
            return self._client.table("conversation_turns").insert(payload).execute()

        await _run_q(q)
        log.info("DB conversation_turns.append: patient_id=%s role=%s", uid, turn.role)

    async def purge_turns_older_than(self, before_utc: datetime) -> int:
        """Delete conversation turns older than *before_utc*. Returns the number of rows deleted."""
        cutoff = before_utc if before_utc.tzinfo else before_utc.replace(tzinfo=UTC)
        cutoff_iso = cutoff.isoformat()

        def q() -> Any:
            return (
                self._client.table("conversation_turns")
                .delete()
                .lt("created_at", cutoff_iso)
                .execute()
            )

        resp = await _run_q(q)
        deleted = len(resp.data or [])
        log.info("conversation_turns.purge: deleted=%d before=%s", deleted, cutoff_iso)
        return deleted
