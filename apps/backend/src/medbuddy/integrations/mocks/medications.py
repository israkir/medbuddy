"""Mock mixin: medication CRUD methods for MockUserData."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from medbuddy.models.domain import MedicationDraft, MedicationRecord
from medbuddy.reminders.prefs import reminder_blob_from_draft


class MockMedicationMixin:
    """Medication CRUD methods for MockUserData."""

    # Provided by MockUserData.__init__
    _meds: dict[str, list[MedicationRecord]]

    # Provided by MockProfileMixin
    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]: ...  # type: ignore[empty-body]

    async def list_medications(self, line_user_id: str) -> list[MedicationRecord]:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        return list(self._meds.get(line_user_id, []))

    async def add_medication(self, line_user_id: str, draft: MedicationDraft) -> MedicationRecord:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        ins = (draft.instructions or "").strip()
        rec = MedicationRecord(
            id=str(uuid.uuid4()),
            name=draft.name.strip(),
            dosage=draft.dosage.strip(),
            schedule=draft.schedule.strip(),
            instructions=ins or None,
            raw_metadata={"reminder": reminder_blob_from_draft(draft)},
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

    async def patch_medication(
        self, line_user_id: str, medication_id: str, fields: dict[str, Any]
    ) -> MedicationRecord | None:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        meds = self._meds.get(line_user_id, [])
        for i, m in enumerate(meds):
            if m.id != medication_id:
                continue
            name = m.name
            dosage = m.dosage
            schedule = m.schedule
            instructions = m.instructions
            if "name" in fields and isinstance(fields["name"], str) and fields["name"].strip():
                name = fields["name"].strip()
            if (
                "dosage" in fields
                and isinstance(fields["dosage"], str)
                and fields["dosage"].strip()
            ):
                dosage = fields["dosage"].strip()
            if (
                "schedule" in fields
                and isinstance(fields["schedule"], str)
                and fields["schedule"].strip()
            ):
                schedule = fields["schedule"].strip()
            if "instructions" in fields:
                raw = fields["instructions"]
                if raw is None:
                    instructions = None
                elif isinstance(raw, str):
                    instructions = raw.strip() or None
            updated = MedicationRecord(
                id=m.id,
                name=name,
                dosage=dosage,
                schedule=schedule,
                instructions=instructions,
                raw_metadata=dict(m.raw_metadata),
            )
            meds[i] = updated
            return updated
        return None
