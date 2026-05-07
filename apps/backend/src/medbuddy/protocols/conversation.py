"""Conversation history store interface."""

from __future__ import annotations

from typing import Protocol

from medbuddy.models.domain import ConversationTurn


class ConversationStorePort(Protocol):
    async def get_recent_turns(
        self, line_user_id: str, max_turns: int
    ) -> list[ConversationTurn]: ...

    async def append_turn(self, line_user_id: str, turn: ConversationTurn) -> None: ...
