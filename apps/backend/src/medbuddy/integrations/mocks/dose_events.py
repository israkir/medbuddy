"""Mock mixin: dose event methods for MockUserData."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from medbuddy.models.domain import (
    DoseEventPendingCandidate,
    DoseEventReminderPayload,
    MedicationRecord,
)
from medbuddy.reminders.prefs import (
    iter_dose_instants_for_medication,
    nudge_window_allows,
    reminder_prefs_from_metadata,
)
from medbuddy.core.locale import effective_user_locale
from medbuddy.core.timezone import effective_user_timezone

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


class MockDoseEventMixin:
    """Dose event methods for MockUserData."""

    # Provided by MockUserData.__init__
    _doses: dict[str, dict[str, Any]]
    _meds: dict[str, list[MedicationRecord]]

    # Provided by MockUserData._reminder_settings
    def _reminder_settings(self) -> Any: ...  # type: ignore[empty-body]

    # Provided by MockProfileMixin
    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]: ...  # type: ignore[empty-body]

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
                    "is_indefinite": bool(med.is_indefinite),
                    "scheduled_at": at,
                    "reminder_sent_at": None,
                    "taken_at": None,
                    "missed_at": None,
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
        if (
            d.get("reminder_sent_at") is not None
            or d.get("taken_at") is not None
            or d.get("missed_at") is not None
        ):
            return None
        return DoseEventReminderPayload(
            dose_event_id=dose_event_id,
            line_user_id=str(d["line_user_id"]),
            medication_id=str(d.get("medication_id") or ""),
            medication_name=str(d["name"]),
            dosage=str(d["dosage"]),
            schedule=str(d["schedule"]),
            scheduled_at=d["scheduled_at"],
            user_timezone=str(d["timezone"]),
            user_locale=str(d["user_locale"]),
            is_nudge=False,
            medication_is_indefinite=bool(d.get("is_indefinite", False)),
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
        if d.get("taken_at") is not None or d.get("missed_at") is not None:
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
            medication_id=str(d.get("medication_id") or ""),
            medication_name=str(d["name"]),
            dosage=str(d["dosage"]),
            schedule=str(d["schedule"]),
            scheduled_at=scheduled_at,
            user_timezone=tz_name,
            user_locale=str(d["user_locale"]),
            is_nudge=True,
            medication_is_indefinite=bool(d.get("is_indefinite", False)),
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
        if not d or d.get("taken_at") is not None or d.get("missed_at") is not None:
            return False
        if int(d.get("reminder_nudge_count") or 0) != expected_nudge_count:
            return False
        d["reminder_nudge_count"] = expected_nudge_count + 1
        d["last_nudge_at"] = datetime.now(UTC)
        return True

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
            if d.get("missed_at") is not None:
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
            and d.get("missed_at") is None
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

    async def mark_pending_doses_missed(
        self, line_user_id: str, *, notes: str | None = None
    ) -> int:
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
            and d.get("missed_at") is None
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
                d["missed_at"] = now
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
            and d.get("missed_at") is None
            and d["scheduled_at"] <= now
        ]
        candidates.sort(key=lambda c: c.scheduled_at, reverse=True)
        return candidates[: max(1, max_items)]

    async def list_upcoming_dose_events(
        self,
        line_user_id: str,
        *,
        from_utc: datetime,
        until_utc_exclusive: datetime,
        max_items: int = 96,
    ) -> list[DoseEventPendingCandidate]:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        uid = row["id"]
        fr = from_utc if from_utc.tzinfo else from_utc.replace(tzinfo=UTC)
        until = (
            until_utc_exclusive
            if until_utc_exclusive.tzinfo
            else until_utc_exclusive.replace(tzinfo=UTC)
        )
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
            and d.get("missed_at") is None
            and fr <= d["scheduled_at"] < until
        ]
        candidates.sort(key=lambda c: c.scheduled_at)
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
            and d.get("missed_at") is None
        ]

    async def list_patients_with_indefinite_medications(self) -> list[str]:
        await asyncio.sleep(0)
        out: list[str] = []
        for line_uid, meds in self._meds.items():
            if any(getattr(m, "is_indefinite", False) for m in meds):
                out.append(line_uid)
        return out

    async def count_future_dose_events(
        self, medication_id: str, *, now_utc: datetime | None = None
    ) -> int:
        await asyncio.sleep(0)
        now = now_utc if now_utc is not None else datetime.now(UTC)
        now = now if now.tzinfo else now.replace(tzinfo=UTC)
        n = 0
        for d in self._doses.values():
            if str(d.get("medication_id")) != medication_id:
                continue
            if d.get("taken_at") is not None or d.get("missed_at") is not None:
                continue
            sched = d.get("scheduled_at")
            if isinstance(sched, datetime) and sched > now:
                n += 1
        return n
