from __future__ import annotations

import asyncio
import uuid
from typing import Any

from medbuddy.models.domain import MedicationRecord
from medbuddy.protocols.ports import UserDataPort


class MockUserData(UserDataPort):
    def __init__(self) -> None:
        self._users: dict[str, dict[str, Any]] = {}
        self._meds: dict[str, list[MedicationRecord]] = {}

    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]:
        await asyncio.sleep(0)
        if line_user_id not in self._users:
            self._users[line_user_id] = {
                "id": str(uuid.uuid4()),
                "line_user_id": line_user_id,
                "consent_accepted": False,
            }
            self._meds[line_user_id] = []
        return self._users[line_user_id]

    async def set_consent(self, line_user_id: str, accepted: bool) -> None:
        await asyncio.sleep(0)
        u = await self.get_or_create_user(line_user_id)
        u["consent_accepted"] = accepted

    async def list_medications(self, line_user_id: str) -> list[MedicationRecord]:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        return list(self._meds.get(line_user_id, []))

    def seed_medication(self, line_user_id: str, med: MedicationRecord) -> None:
        self._meds.setdefault(line_user_id, []).append(med)
