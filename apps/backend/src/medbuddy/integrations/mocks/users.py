from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from medbuddy.config import Settings, get_settings
from medbuddy.models.domain import (
    DoseClarificationPending,
    DoseEventPendingCandidate,
    DoseEventReminderPayload,
    MedicationDraft,
    MedicationRecord,
)
from medbuddy.reminders.prefs import (
    iter_dose_instants_for_medication,
    reminder_blob_from_draft,
    reminder_prefs_from_metadata,
)
from medbuddy.protocols.ports import UserDataPort
from medbuddy.reminders.nudge_policy import nudge_window_allows
from medbuddy.user_locale import effective_user_locale, normalize_locale_patch
from medbuddy.user_timezone import effective_user_timezone, normalize_timezone_patch

_RECENT_TAKEN_DOSE_NOTE_HOURS = 48


def _merge_dose_event_notes(existing: str | None, addition: str) -> str:
    e = (existing or "").strip()
    a = addition.strip()
    if not a:
        return e[:500] if e else ""
    if not e:
        return a[:500]
    combined = f"{e} | {a}"
    return combined[:500]


def _default_profile_fields() -> dict[str, Any]:
    return {
        "preferred_name": None,
        "age_years": None,
        "gender": None,
        "emergency_contact": None,
        "health_notes": None,
        "onboarding_completed_at": None,
        "locale": "zh-TW",
    }


class MockUserData(UserDataPort):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings
        self._users: dict[str, dict[str, Any]] = {}
        self._meds: dict[str, list[MedicationRecord]] = {}
        self._doses: dict[str, dict[str, Any]] = {}
        self._dose_clarification: dict[str, dict[str, Any] | None] = {}

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
        row.setdefault("locale", "zh-TW")
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
        locale: str = "zh-TW",
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
        row["locale"] = effective_user_locale(locale)
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
        if "locale" in fields:
            norm_loc = normalize_locale_patch(fields["locale"])
            if norm_loc is not None:
                row["locale"] = norm_loc
        return row

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
                    "notes": None,
                    "reminder_nudge_count": 0,
                    "last_nudge_at": None,
                    "timezone": tz_name,
                    "user_locale": effective_user_locale(row.get("locale")),
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
            user_locale=str(d["user_locale"]),
            is_nudge=False,
        )

    async def get_dose_event_for_nudge(
        self,
        dose_event_id: str,
        *,
        expected_nudge_count: int,
        max_nudges: int,
    ) -> DoseEventReminderPayload | None:
        await asyncio.sleep(0)
        if max_nudges <= 0 or expected_nudge_count >= max_nudges:
            return None
        d = self._doses.get(dose_event_id)
        if not d:
            return None
        if d.get("taken_at") is not None:
            return None
        if d.get("reminder_sent_at") is None:
            return None
        if int(d.get("reminder_nudge_count") or 0) != expected_nudge_count:
            return None
        scheduled_at = d["scheduled_at"]
        tz_name = str(d["timezone"])
        if not nudge_window_allows(scheduled_at, tz_name, now_utc=datetime.now(UTC)):
            return None
        return DoseEventReminderPayload(
            dose_event_id=dose_event_id,
            line_user_id=str(d["line_user_id"]),
            medication_name=str(d["name"]),
            dosage=str(d["dosage"]),
            schedule=str(d["schedule"]),
            scheduled_at=scheduled_at,
            user_timezone=tz_name,
            user_locale=str(d["user_locale"]),
            is_nudge=True,
        )

    async def try_mark_reminder_sent(self, dose_event_id: str) -> bool:
        await asyncio.sleep(0)
        d = self._doses.get(dose_event_id)
        if not d or d.get("reminder_sent_at") is not None:
            return False
        d["reminder_sent_at"] = datetime.now(UTC)
        return True

    async def try_increment_reminder_nudge(
        self, dose_event_id: str, *, expected_nudge_count: int
    ) -> bool:
        await asyncio.sleep(0)
        d = self._doses.get(dose_event_id)
        if not d or d.get("taken_at") is not None:
            return False
        if int(d.get("reminder_nudge_count") or 0) != expected_nudge_count:
            return False
        d["reminder_nudge_count"] = expected_nudge_count + 1
        d["last_nudge_at"] = datetime.now(UTC)
        return True

    async def get_dose_clarification_pending(
        self, line_user_id: str
    ) -> DoseClarificationPending | None:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        raw = self._dose_clarification.get(line_user_id)
        return DoseClarificationPending.from_json(raw) if raw else None

    async def set_dose_clarification_pending(
        self, line_user_id: str, pending: DoseClarificationPending | None
    ) -> None:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        self._dose_clarification[line_user_id] = pending.to_json() if pending else None

    async def mark_dose_events_taken(
        self,
        line_user_id: str,
        dose_event_ids: list[str],
        *,
        notes: str | None = None,
    ) -> int:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        uid = row["id"]
        now = datetime.now(UTC)
        note_val: str | None = None
        if notes is not None:
            nstrip = notes.strip()
            note_val = nstrip[:500] if nstrip else None
        n = 0
        for eid in dose_event_ids:
            d = self._doses.get(eid)
            if not d:
                continue
            if d["line_user_id"] != line_user_id or d["user_internal_id"] != uid:
                continue
            if d.get("taken_at") is not None:
                continue
            if d["scheduled_at"] > now:
                continue
            d["taken_at"] = now
            if note_val:
                d["notes"] = note_val
            n += 1
        return n

    async def append_note_to_dose_events(
        self,
        line_user_id: str,
        dose_event_ids: list[str],
        *,
        notes: str,
    ) -> int:
        await asyncio.sleep(0)
        addition = notes.strip()
        if not addition:
            return 0
        if len(addition) > 500:
            addition = addition[:500]
        row = await self.get_or_create_user(line_user_id)
        uid = row["id"]
        n = 0
        for eid in dose_event_ids:
            d = self._doses.get(eid)
            if not d:
                continue
            if d["line_user_id"] != line_user_id or d["user_internal_id"] != uid:
                continue
            if d.get("taken_at") is None:
                continue
            existing = d.get("notes")
            ex = existing.strip() if isinstance(existing, str) else ""
            merged = _merge_dose_event_notes(ex or None, addition)
            if merged:
                d["notes"] = merged
                n += 1
        return n

    async def mark_pending_doses_taken(self, line_user_id: str, *, notes: str | None = None) -> int:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        uid = row["id"]
        now = datetime.now(UTC)
        candidates = [
            d
            for d in self._doses.values()
            if d["line_user_id"] == line_user_id
            and d["user_internal_id"] == uid
            and d.get("taken_at") is None
            and d["scheduled_at"] <= now
        ]
        if not candidates:
            return 0
        target_ts = max(d["scheduled_at"] for d in candidates)
        note_val: str | None = None
        if notes is not None:
            nstrip = notes.strip()
            note_val = nstrip[:500] if nstrip else None
        n = 0
        for d in candidates:
            if d["scheduled_at"] == target_ts:
                d["taken_at"] = now
                if note_val:
                    d["notes"] = note_val
                n += 1
        return n

    async def list_pending_dose_candidates(
        self, line_user_id: str, *, max_items: int = 5
    ) -> list[DoseEventPendingCandidate]:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        uid = row["id"]
        now = datetime.now(UTC)
        candidates = [
            DoseEventPendingCandidate(
                dose_event_id=did,
                medication_name=str(d["name"]),
                dosage=str(d["dosage"]),
                schedule=str(d["schedule"]),
                scheduled_at=d["scheduled_at"],
            )
            for did, d in self._doses.items()
            if d["line_user_id"] == line_user_id
            and d["user_internal_id"] == uid
            and d.get("taken_at") is None
            and d["scheduled_at"] <= now
        ]
        candidates.sort(key=lambda c: c.scheduled_at, reverse=True)
        return candidates[: max(1, max_items)]

    async def list_recent_taken_dose_candidates(
        self, line_user_id: str, *, max_items: int = 5
    ) -> list[DoseEventPendingCandidate]:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        uid = row["id"]
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=_RECENT_TAKEN_DOSE_NOTE_HOURS)
        candidates = [
            DoseEventPendingCandidate(
                dose_event_id=did,
                medication_name=str(d["name"]),
                dosage=str(d["dosage"]),
                schedule=str(d["schedule"]),
                scheduled_at=d["scheduled_at"],
            )
            for did, d in self._doses.items()
            if d["line_user_id"] == line_user_id
            and d["user_internal_id"] == uid
            and d.get("taken_at") is not None
            and d["taken_at"] >= cutoff
        ]
        candidates.sort(key=lambda c: c.scheduled_at, reverse=True)
        return candidates[: max(1, max_items)]

    async def append_note_to_recent_taken_dose(self, line_user_id: str, *, notes: str) -> int:
        await asyncio.sleep(0)
        addition = notes.strip()
        if not addition:
            return 0
        if len(addition) > 500:
            addition = addition[:500]
        row = await self.get_or_create_user(line_user_id)
        uid = row["id"]
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=_RECENT_TAKEN_DOSE_NOTE_HOURS)
        taken = [
            d
            for d in self._doses.values()
            if d["line_user_id"] == line_user_id
            and d["user_internal_id"] == uid
            and d.get("taken_at") is not None
            and d["taken_at"] >= cutoff
        ]
        if not taken:
            return 0
        taken.sort(key=lambda d: (d["taken_at"], d["scheduled_at"]), reverse=True)
        target_ts = taken[0]["scheduled_at"]
        to_update = [d for d in taken if d["scheduled_at"] == target_ts]
        if not to_update:
            return 0
        first_existing: str | None = None
        for d in to_update:
            n = d.get("notes")
            if isinstance(n, str) and n.strip():
                first_existing = n.strip()
                break
        merged = _merge_dose_event_notes(first_existing, addition)
        if not merged:
            return 0
        for d in to_update:
            d["notes"] = merged
        return len(to_update)

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
