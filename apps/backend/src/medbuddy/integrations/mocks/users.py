from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from medbuddy.models.domain import MedicationDraft, MedicationRecord
from medbuddy.protocols.ports import UserDataPort


def _default_profile_fields() -> dict[str, Any]:
    return {
        "preferred_name": None,
        "age_years": None,
        "emergency_contact": None,
        "health_notes": None,
        "onboarding_completed_at": None,
    }


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
                **_default_profile_fields(),
            }
            self._meds.setdefault(line_user_id, [])
        row = self._users[line_user_id]
        for k, v in _default_profile_fields().items():
            row.setdefault(k, v)
        return row

    async def save_onboarding_profile(
        self,
        line_user_id: str,
        *,
        preferred_name: str,
        age_years: int | None,
        emergency_contact: str | None,
        health_notes: str | None,
    ) -> dict[str, Any]:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        row["preferred_name"] = preferred_name.strip()
        row["age_years"] = age_years
        row["emergency_contact"] = (emergency_contact or "").strip() or None
        row["health_notes"] = (health_notes or "").strip() or None
        row["onboarding_completed_at"] = datetime.now(UTC)
        return row

    async def list_medications(self, line_user_id: str) -> list[MedicationRecord]:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        return list(self._meds.get(line_user_id, []))

    async def add_medication(self, line_user_id: str, draft: MedicationDraft) -> MedicationRecord:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        ins = (draft.instructions_zh or "").strip()
        rec = MedicationRecord(
            id=str(uuid.uuid4()),
            name=draft.name.strip(),
            dosage=draft.dosage.strip(),
            schedule=draft.schedule.strip(),
            instructions_zh=ins or None,
        )
        self._meds.setdefault(line_user_id, []).append(rec)
        return rec

    async def delete_medication(self, line_user_id: str, medication_id: str) -> bool:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        meds = self._meds.get(line_user_id, [])
        for i, m in enumerate(meds):
            if m.id == medication_id:
                del meds[i]
                return True
        return False

    def seed_medication(self, line_user_id: str, med: MedicationRecord) -> None:
        self._meds.setdefault(line_user_id, []).append(med)
