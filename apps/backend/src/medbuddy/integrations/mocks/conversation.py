from __future__ import annotations

import asyncio
from collections import defaultdict

from medbuddy.models.domain import ConversationTurn
from medbuddy.protocols import ConversationStorePort


class InMemoryConversationStore(ConversationStorePort):
    def __init__(self) -> None:
        self._turns: dict[str, list[ConversationTurn]] = defaultdict(list)

    async def get_recent_turns(self, line_user_id: str, max_turns: int) -> list[ConversationTurn]:
        await asyncio.sleep(0)
        turns = self._turns[line_user_id]
        return turns[-max_turns:] if max_turns else turns

    async def append_turn(self, line_user_id: str, turn: ConversationTurn) -> None:
        await asyncio.sleep(0)
        self._turns[line_user_id].append(turn)
