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


_MED_SELECT_COLUMNS = "id, name, dosage, schedule, instructions, is_indefinite, raw_metadata"


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
        is_indefinite=bool(row.get("is_indefinite", False)),
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
                .select(_MED_SELECT_COLUMNS)
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
            "is_indefinite": bool(draft.is_indefinite),
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

    async def delete_all_medications(self, line_user_id: str) -> int:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]

        def q() -> Any:
            return self._client.table("medications").delete().eq("patient_id", uid).execute()

        resp = await _run_q(q)
        rows = resp.data or []
        n = len(rows)
        log.info("DB medications.delete_all: patient_id=%s deleted=%d", uid, n)
        return n

    async def merge_medication_raw_metadata(
        self,
        line_user_id: str,
        medication_id: str,
        reminder_patch: dict[str, Any],
        *,
        set_indefinite: bool | None = None,
    ) -> MedicationRecord | None:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]

        def select_one() -> Any:
            return (
                self._client.table("medications")
                .select(_MED_SELECT_COLUMNS)
                .eq("patient_id", uid)
                .eq("id", medication_id)
                .limit(1)
                .execute()
            )

        resp = await _run_q(select_one)
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        raw = row.get("raw_metadata")
        if not isinstance(raw, dict):
            raw = {}
        rem = raw.get("reminder")
        if not isinstance(rem, dict):
            rem = {}
        rem_merged = {**rem, **reminder_patch}
        raw_merged = {**raw, "reminder": rem_merged}
        payload: dict[str, Any] = {"raw_metadata": raw_merged}
        if set_indefinite is not None:
            payload["is_indefinite"] = bool(set_indefinite)

        def upd() -> Any:
            return (
                self._client.table("medications")
                .update(payload)
                .eq("patient_id", uid)
                .eq("id", medication_id)
                .execute()
            )

        uresp = await _run_q(upd)
        urows = uresp.data or []
        if not urows:
            return None
        return _med_row_to_record(urows[0])

    async def bulk_disable_reminders(
        self,
        line_user_id: str,
        *,
        medication_id: str | None = None,
    ) -> int:
        meds = await self.list_medications(line_user_id)
        if medication_id is not None:
            meds = [m for m in meds if m.id == medication_id]
        n = 0
        for m in meds:
            updated = await self.merge_medication_raw_metadata(
                line_user_id,
                m.id,
                {
                    "materialize_daily": False,
                    "horizon_days": None,
                    "needs_horizon_confirmation": False,
                },
            )
            if updated is not None:
                n += 1
        log.info(
            "DB medications.bulk_disable_reminders: user=%s med_filter=%s patched=%d",
            line_user_id,
            medication_id or "all",
            n,
        )
        return n

    async def list_patients_with_indefinite_medications(self) -> list[str]:
        """Return ``external_user_id`` values for patients with at least one chronic med.

        Used by the daily chronic-resync cron. Service-role key bypasses RLS.
        """

        def q_med_patients() -> Any:
            return (
                self._client.table("medications")
                .select("patient_id")
                .eq("is_indefinite", True)
                .execute()
            )

        resp = await _run_q(q_med_patients)
        rows = resp.data or []
        patient_ids: list[str] = []
        seen: set[str] = set()
        for r in rows:
            pid = str(r.get("patient_id") or "")
            if pid and pid not in seen:
                seen.add(pid)
                patient_ids.append(pid)
        if not patient_ids:
            return []

        def q_patients() -> Any:
            return (
                self._client.table("patients")
                .select("external_user_id")
                .in_("id", patient_ids)
                .execute()
            )

        presp = await _run_q(q_patients)
        prows = presp.data or []
        return [str(r["external_user_id"]) for r in prows if r.get("external_user_id")]

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
