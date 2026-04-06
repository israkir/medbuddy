from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from medbuddy.config import Settings, get_settings
from medbuddy.models.domain import DoseEventReminderPayload, MedicationDraft, MedicationRecord
from medbuddy.reminders.prefs import (
    iter_dose_instants_for_medication,
    reminder_blob_from_draft,
    reminder_prefs_from_metadata,
)
from medbuddy.protocols.ports import UserDataPort
from medbuddy.user_timezone import effective_user_timezone, normalize_timezone_patch


def _default_profile_fields() -> dict[str, Any]:
    return {
        "preferred_name": None,
        "age_years": None,
        "gender": None,
        "emergency_contact": None,
        "health_notes": None,
        "onboarding_completed_at": None,
    }


class MockUserData(UserDataPort):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings
        self._users: dict[str, dict[str, Any]] = {}
        self._meds: dict[str, list[MedicationRecord]] = {}
        self._doses: dict[str, dict[str, Any]] = {}

    def _reminder_settings(self) -> Settings:
        return self._settings if self._settings is not None else get_settings()

    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]:
        await asyncio.sleep(0)
        if line_user_id not in self._users:
            self._users[line_user_id] = {
                "id": str(uuid.uuid4()),
                "line_user_id": line_user_id,
                "timezone": "Asia/Taipei",
                **_default_profile_fields(),
            }
            self._meds.setdefault(line_user_id, [])
        row = self._users[line_user_id]
        for k, v in _default_profile_fields().items():
            row.setdefault(k, v)
        row.setdefault("timezone", "Asia/Taipei")
        return row

    async def save_onboarding_profile(
        self,
        line_user_id: str,
        *,
        preferred_name: str,
        age_years: int | None,
        gender: str | None,
        emergency_contact: str | None,
        health_notes: str | None,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        row["preferred_name"] = preferred_name.strip()
        row["age_years"] = age_years
        row["gender"] = gender
        row["emergency_contact"] = (emergency_contact or "").strip() or None
        row["health_notes"] = (health_notes or "").strip() or None
        row["onboarding_completed_at"] = datetime.now(UTC)
        row["timezone"] = effective_user_timezone(timezone)
        return row

    async def patch_user_profile(self, line_user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        if "preferred_name" in fields:
            pn = fields["preferred_name"]
            if isinstance(pn, str) and pn.strip():
                row["preferred_name"] = pn.strip()
        if "age_years" in fields:
            age = fields["age_years"]
            if age is None:
                row["age_years"] = None
            elif isinstance(age, int) and 0 <= age <= 120:
                row["age_years"] = age
            elif isinstance(age, float) and age.is_integer():
                ai = int(age)
                if 0 <= ai <= 120:
                    row["age_years"] = ai
        if "gender" in fields:
            raw_g = fields["gender"]
            if raw_g is None:
                row["gender"] = None
            elif isinstance(raw_g, str):
                g = raw_g.strip().lower()
                allowed = {"female", "male", "non_binary", "prefer_not_say", "other"}
                if g in allowed:
                    row["gender"] = g
        for key in ("emergency_contact", "health_notes"):
            if key in fields:
                raw = fields[key]
                if raw is None:
                    row[key] = None
                elif isinstance(raw, str):
                    row[key] = raw.strip() or None
        if "timezone" in fields:
            norm = normalize_timezone_patch(fields["timezone"])
            if norm is not None:
                row["timezone"] = norm
            elif fields["timezone"] is None:
                row["timezone"] = None
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

    async def sync_upcoming_dose_events(self, line_user_id: str) -> list[tuple[str, datetime]]:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        uid = row["id"]
        rem = self._reminder_settings()
        tz_name = effective_user_timezone(str(row.get("timezone")) if row.get("timezone") else None)
        meds = list(self._meds.get(line_user_id, []))
        now = datetime.now(UTC)
        to_del = [
            did
            for did, d in self._doses.items()
            if d["user_internal_id"] == uid and d["scheduled_at"] > now
        ]
        for did in to_del:
            del self._doses[did]

        if not meds:
            return []
        out: list[tuple[str, datetime]] = []
        for med in meds:
            prefs = reminder_prefs_from_metadata(med.raw_metadata)
            instants = iter_dose_instants_for_medication(
                prefs,
                tz_name=tz_name,
                default_local_hhmm=rem.reminder_default_local_time,
                default_horizon_days=rem.reminder_horizon_days,
                now_utc=now,
            )
            for at in instants:
                did = str(uuid.uuid4())
                self._doses[did] = {
                    "id": did,
                    "line_user_id": line_user_id,
                    "user_internal_id": uid,
                    "medication_id": med.id,
                    "name": med.name,
                    "dosage": med.dosage,
                    "schedule": med.schedule,
                    "scheduled_at": at,
                    "reminder_sent_at": None,
                    "taken_at": None,
                    "timezone": tz_name,
                }
                out.append((did, at))
        return out

    async def get_dose_event_for_reminder(
        self, dose_event_id: str
    ) -> DoseEventReminderPayload | None:
        await asyncio.sleep(0)
        d = self._doses.get(dose_event_id)
        if not d:
            return None
        if d.get("reminder_sent_at") is not None or d.get("taken_at") is not None:
            return None
        return DoseEventReminderPayload(
            dose_event_id=dose_event_id,
            line_user_id=str(d["line_user_id"]),
            medication_name=str(d["name"]),
            dosage=str(d["dosage"]),
            schedule=str(d["schedule"]),
            scheduled_at=d["scheduled_at"],
            user_timezone=str(d["timezone"]),
        )

    async def try_mark_reminder_sent(self, dose_event_id: str) -> bool:
        await asyncio.sleep(0)
        d = self._doses.get(dose_event_id)
        if not d or d.get("reminder_sent_at") is not None:
            return False
        d["reminder_sent_at"] = datetime.now(UTC)
        return True

    async def list_dose_event_ids_for_reconcile(self, *, before_utc: datetime) -> list[str]:
        await asyncio.sleep(0)
        b = before_utc if before_utc.tzinfo else before_utc.replace(tzinfo=UTC)
        return [
            did
            for did, d in self._doses.items()
            if d["scheduled_at"] <= b
            and d.get("reminder_sent_at") is None
            and d.get("taken_at") is None
        ]

    def seed_medication(self, line_user_id: str, med: MedicationRecord) -> None:
        self._meds.setdefault(line_user_id, []).append(med)
