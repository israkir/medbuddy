"""Supabase mixin: medication CRUD methods for SupabaseUserData."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from medbuddy.models.domain import MedicationDraft, MedicationRecord
from medbuddy.reminders.prefs import reminder_blob_from_draft

log = logging.getLogger(__name__)


def _run_q(fn: Any) -> Any:
    return asyncio.to_thread(fn)


def _med_row_to_record(row: dict[str, Any]) -> MedicationRecord:
    raw = row.get("raw_metadata")
    if not isinstance(raw, dict):
        raw = {}
    ins = row.get("instructions")
    return MedicationRecord(
        id=str(row["id"]),
        name=row["name"],
        dosage=row["dosage"],
        schedule=row["schedule"],
        instructions=ins if isinstance(ins, str) or ins is None else str(ins),
        raw_metadata=raw,
    )


class SupabaseMedicationMixin:
    """Medication CRUD methods for SupabaseUserData."""

    # Provided by SupabaseUserData.__init__
    _client: Any

    # Provided by SupabaseProfileMixin
    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]: ...  # type: ignore[empty-body]

    async def list_medications(self, line_user_id: str) -> list[MedicationRecord]:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]

        def q() -> Any:
            return (
                self._client.table("medications")
                .select("id, name, dosage, schedule, instructions, raw_metadata")
                .eq("patient_id", uid)
                .order("id")
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return [_med_row_to_record(r) for r in rows]

    async def add_medication(self, line_user_id: str, draft: MedicationDraft) -> MedicationRecord:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        ins = (draft.instructions or "").strip()
        payload: dict[str, Any] = {
            "patient_id": uid,
            "name": draft.name.strip(),
            "dosage": draft.dosage.strip(),
            "schedule": draft.schedule.strip(),
            "instructions": ins or None,
            "raw_metadata": {"reminder": reminder_blob_from_draft(draft)},
        }

        def insert() -> Any:
            return self._client.table("medications").insert(payload).execute()

        resp = await _run_q(insert)
        rows = resp.data or []
        if not rows:
            msg = "Supabase medication insert returned no row"
            raise RuntimeError(msg)
        log.info("DB medications.add: patient_id=%s inserted=1", uid)
        return _med_row_to_record(rows[0])

    async def delete_medication(self, line_user_id: str, medication_id: str) -> bool:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]

        def q() -> Any:
            return (
                self._client.table("medications")
                .delete()
                .eq("patient_id", uid)
                .eq("id", medication_id)
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        log.info("DB medications.delete: patient_id=%s deleted=%d", uid, len(rows))
        return len(rows) > 0

    async def patch_medication(
        self, line_user_id: str, medication_id: str, fields: dict[str, Any]
    ) -> MedicationRecord | None:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        payload: dict[str, Any] = {}
        if "name" in fields and isinstance(fields["name"], str):
            v = fields["name"].strip()
            if v:
                payload["name"] = v
        if "dosage" in fields and isinstance(fields["dosage"], str):
            v = fields["dosage"].strip()
            if v:
                payload["dosage"] = v
        if "schedule" in fields and isinstance(fields["schedule"], str):
            v = fields["schedule"].strip()
            if v:
                payload["schedule"] = v
        if "instructions" in fields:
            raw = fields["instructions"]
            if raw is None:
                payload["instructions"] = None
            elif isinstance(raw, str):
                payload["instructions"] = raw.strip() or None
        if not payload:
            return None

        def upd() -> Any:
            return (
                self._client.table("medications")
                .update(payload)
                .eq("patient_id", uid)
                .eq("id", medication_id)
                .execute()
            )

        resp = await _run_q(upd)
        rows = resp.data or []
        log.info("DB medications.patch: patient_id=%s updated=%d", uid, len(rows))
        if not rows:
            return None
        return _med_row_to_record(rows[0])
