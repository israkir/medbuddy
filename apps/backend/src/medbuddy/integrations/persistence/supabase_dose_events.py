"""Supabase mixin: dose event methods for SupabaseUserData."""

from __future__ import annotations

import asyncio
import logging
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

log = logging.getLogger(__name__)

_RECENT_TAKEN_DOSE_NOTE_HOURS = 48


def _run_q(fn: Any) -> Any:
    return asyncio.to_thread(fn)


def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(s)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    msg = f"Unsupported timestamp value from DB: {type(value)}"
    raise TypeError(msg)


def _merge_dose_event_notes(existing: str | None, addition: str) -> str:
    e = (existing or "").strip()
    a = addition.strip()
    if not a:
        return e[:500] if e else ""
    if not e:
        return a[:500]
    combined = f"{e} | {a}"
    return combined[:500]


class SupabaseDoseEventMixin:
    """Dose event methods for SupabaseUserData."""

    # Provided by SupabaseUserData.__init__
    _client: Any
    _settings: Any

    # Provided by SupabaseProfileMixin
    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]: ...  # type: ignore[empty-body]

    # Provided by SupabaseMedicationMixin
    async def list_medications(self, line_user_id: str) -> list[MedicationRecord]: ...  # type: ignore[empty-body]

    async def sync_upcoming_dose_events(self, line_user_id: str) -> list[tuple[str, datetime]]:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        tz_name = effective_user_timezone(str(user["timezone"]) if user.get("timezone") else None)
        meds = await self.list_medications(line_user_id)
        now = datetime.now(UTC)
        cutoff = now.isoformat()

        # Collect medication IDs that already have at least one past dose_event so that
        # one-time first_reminder_in_minutes reminders are not re-created on every sync.
        def q_past_meds() -> Any:
            return (
                self._client.table("dose_events")
                .select("medication_id")
                .eq("patient_id", uid)
                .lte("scheduled_at", cutoff)
                .execute()
            )

        past_resp = await _run_q(q_past_meds)
        meds_with_past_events: set[str] = {str(r["medication_id"]) for r in (past_resp.data or [])}

        def delete_future() -> Any:
            return (
                self._client.table("dose_events")
                .delete()
                .eq("patient_id", uid)
                .gt("scheduled_at", cutoff)
                .execute()
            )

        await _run_q(delete_future)
        log.info("DB dose_events.sync: patient_id=%s deleted_future=1batch", uid)

        if not meds:
            return []

        rows: list[dict[str, Any]] = []
        for med in meds:
            prefs = reminder_prefs_from_metadata(med.raw_metadata)
            instants = iter_dose_instants_for_medication(
                prefs,
                tz_name=tz_name,
                default_local_hhmm=self._settings.reminder_default_local_time,
                default_horizon_days=self._settings.reminder_horizon_days,
                now_utc=now,
                skip_first_reminder=str(med.id) in meds_with_past_events,
            )
            for at in instants:
                rows.append(
                    {
                        "patient_id": uid,
                        "medication_id": med.id,
                        "scheduled_at": at.isoformat(),
                    }
                )
        if not rows:
            return []

        def insert() -> Any:
            return self._client.table("dose_events").insert(rows).execute()

        resp = await _run_q(insert)
        inserted = resp.data or []
        log.info(
            "DB dose_events.sync: patient_id=%s inserted=%d meds=%d",
            uid,
            len(inserted),
            len(meds),
        )
        out: list[tuple[str, datetime]] = []
        for r in inserted:
            out.append((str(r["id"]), _parse_ts(r["scheduled_at"])))
        return out

    async def get_dose_event_for_reminder(
        self, dose_event_id: str
    ) -> DoseEventReminderPayload | None:
        def q_dose() -> Any:
            return (
                self._client.table("dose_events")
                .select(
                    "id, patient_id, medication_id, scheduled_at, reminder_sent_at, taken_at, missed_at"
                )
                .eq("id", dose_event_id)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q_dose)
        drows = resp.data or []
        if not drows:
            return None
        dr = drows[0]
        if (
            dr.get("reminder_sent_at") is not None
            or dr.get("taken_at") is not None
            or dr.get("missed_at") is not None
        ):
            return None
        uid = str(dr["patient_id"])
        mid = str(dr["medication_id"])
        scheduled_at = _parse_ts(dr["scheduled_at"])

        def q_user() -> Any:
            return (
                self._client.table("patients")
                .select("external_user_id, timezone, locale")
                .eq("id", uid)
                .limit(1)
                .execute()
            )

        uresp = await _run_q(q_user)
        urows = uresp.data or []
        if not urows:
            return None
        line_uid = str(urows[0]["external_user_id"])
        tz_raw = urows[0].get("timezone")
        tz_name = effective_user_timezone(str(tz_raw) if tz_raw else None)
        loc_raw = urows[0].get("locale")
        user_locale = effective_user_locale(str(loc_raw) if loc_raw else None)

        def q_med() -> Any:
            return (
                self._client.table("medications")
                .select("name, dosage, schedule, is_indefinite")
                .eq("id", mid)
                .limit(1)
                .execute()
            )

        mresp = await _run_q(q_med)
        mrows = mresp.data or []
        if not mrows:
            return None
        m = mrows[0]
        return DoseEventReminderPayload(
            dose_event_id=dose_event_id,
            line_user_id=line_uid,
            medication_id=mid,
            medication_name=str(m["name"]),
            dosage=str(m["dosage"]),
            schedule=str(m["schedule"]),
            scheduled_at=scheduled_at,
            user_timezone=tz_name,
            user_locale=user_locale,
            is_nudge=False,
            medication_is_indefinite=bool(m.get("is_indefinite", False)),
        )

    async def get_dose_event_for_nudge(
        self,
        dose_event_id: str,
        *,
        expected_nudge_count: int,
        max_nudges: int,
    ) -> DoseEventReminderPayload | None:
        if max_nudges <= 0 or expected_nudge_count >= max_nudges:
            return None

        def q_dose() -> Any:
            return (
                self._client.table("dose_events")
                .select(
                    "id, patient_id, medication_id, scheduled_at, reminder_sent_at, "
                    "taken_at, missed_at, reminder_nudge_count"
                )
                .eq("id", dose_event_id)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q_dose)
        drows = resp.data or []
        if not drows:
            return None
        dr = drows[0]
        if dr.get("taken_at") is not None or dr.get("missed_at") is not None:
            return None
        if dr.get("reminder_sent_at") is None:
            return None
        if int(dr.get("reminder_nudge_count") or 0) != expected_nudge_count:
            return None
        uid = str(dr["patient_id"])
        mid = str(dr["medication_id"])
        scheduled_at = _parse_ts(dr["scheduled_at"])
        now_utc = datetime.now(UTC)

        def q_user() -> Any:
            return (
                self._client.table("patients")
                .select("external_user_id, timezone, locale")
                .eq("id", uid)
                .limit(1)
                .execute()
            )

        uresp = await _run_q(q_user)
        urows = uresp.data or []
        if not urows:
            return None
        line_uid = str(urows[0]["external_user_id"])
        tz_raw = urows[0].get("timezone")
        tz_name = effective_user_timezone(str(tz_raw) if tz_raw else None)
        loc_raw = urows[0].get("locale")
        user_locale = effective_user_locale(str(loc_raw) if loc_raw else None)
        if not nudge_window_allows(scheduled_at, tz_name, now_utc=now_utc):
            return None

        def q_med() -> Any:
            return (
                self._client.table("medications")
                .select("name, dosage, schedule, is_indefinite")
                .eq("id", mid)
                .limit(1)
                .execute()
            )

        mresp = await _run_q(q_med)
        mrows = mresp.data or []
        if not mrows:
            return None
        m = mrows[0]
        return DoseEventReminderPayload(
            dose_event_id=dose_event_id,
            line_user_id=line_uid,
            medication_id=mid,
            medication_name=str(m["name"]),
            dosage=str(m["dosage"]),
            schedule=str(m["schedule"]),
            scheduled_at=scheduled_at,
            user_timezone=tz_name,
            user_locale=user_locale,
            is_nudge=True,
            medication_is_indefinite=bool(m.get("is_indefinite", False)),
        )

    async def try_mark_reminder_sent(self, dose_event_id: str) -> bool:
        now = datetime.now(UTC)
        payload = {"reminder_sent_at": now.isoformat()}

        def q() -> Any:
            return (
                self._client.table("dose_events")
                .update(payload)
                .eq("id", dose_event_id)
                .is_("reminder_sent_at", "null")
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        log.info(
            "DB dose_events.mark_reminder_sent: dose_event_id=%s updated=%d",
            dose_event_id,
            len(rows),
        )
        return len(rows) > 0

    async def try_increment_reminder_nudge(
        self, dose_event_id: str, *, expected_nudge_count: int
    ) -> bool:
        now = datetime.now(UTC)
        payload = {
            "reminder_nudge_count": expected_nudge_count + 1,
            "last_nudge_at": now.isoformat(),
        }

        def q() -> Any:
            return (
                self._client.table("dose_events")
                .update(payload)
                .eq("id", dose_event_id)
                .eq("reminder_nudge_count", expected_nudge_count)
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        log.info(
            "DB dose_events.increment_nudge: dose_event_id=%s expected=%d updated=%d",
            dose_event_id,
            expected_nudge_count,
            len(rows),
        )
        return len(rows) > 0

    async def mark_pending_doses_taken(self, line_user_id: str, *, notes: str | None = None) -> int:
        """Set ``taken_at`` on the most recent past pending dose instant (all meds at that time)."""
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        now = datetime.now(UTC)
        now_iso = now.isoformat()

        def q_latest() -> Any:
            return (
                self._client.table("dose_events")
                .select("scheduled_at")
                .eq("patient_id", uid)
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .lte("scheduled_at", now_iso)
                .order("scheduled_at", desc=True)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q_latest)
        rows = resp.data or []
        if not rows:
            return 0
        target_ts = rows[0]["scheduled_at"]

        payload: dict[str, Any] = {"taken_at": now_iso}
        if notes is not None:
            n = notes.strip()
            if len(n) > 500:
                n = n[:500]
            if n:
                payload["notes"] = n

        def q_update() -> Any:
            return (
                self._client.table("dose_events")
                .update(payload)
                .eq("patient_id", uid)
                .eq("scheduled_at", target_ts)
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .execute()
            )

        uresp = await _run_q(q_update)
        updated = uresp.data or []
        log.info("DB dose_events.mark_pending_taken: patient_id=%s updated=%d", uid, len(updated))
        return len(updated)

    async def list_pending_dose_candidates(
        self, line_user_id: str, *, max_items: int = 4
    ) -> list[DoseEventPendingCandidate]:
        """Return pending dose events within the last 48 hours, most recent first.

        The 48-hour window matches the reconcile staleness threshold so events cleaned
        up by the reconcile job never appear here as spurious candidates.
        """
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        now = datetime.now(UTC)
        now_iso = now.isoformat()
        window_iso = (now - timedelta(hours=48)).isoformat()
        limit = max(1, max_items)

        def q_rows() -> Any:
            return (
                self._client.table("dose_events")
                .select("id, scheduled_at, last_nudge_at, medications(name, dosage, schedule)")
                .eq("patient_id", uid)
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .lte("scheduled_at", now_iso)
                .gte("scheduled_at", window_iso)
                .order("scheduled_at", desc=True)
                .limit(limit)
                .execute()
            )

        resp = await _run_q(q_rows)
        rows = resp.data or []
        out: list[DoseEventPendingCandidate] = []
        for r in rows:
            med = r.get("medications")
            if isinstance(med, list):
                med = med[0] if med else None
            if not isinstance(med, dict):
                continue
            raw_nudge = r.get("last_nudge_at")
            out.append(
                DoseEventPendingCandidate(
                    dose_event_id=str(r["id"]),
                    medication_name=str(med.get("name") or ""),
                    dosage=str(med.get("dosage") or ""),
                    schedule=str(med.get("schedule") or ""),
                    scheduled_at=_parse_ts(r["scheduled_at"]),
                    last_nudge_at=_parse_ts(raw_nudge) if raw_nudge else None,
                )
            )
        return out

    async def list_upcoming_dose_events(
        self,
        line_user_id: str,
        *,
        from_utc: datetime,
        until_utc_exclusive: datetime,
        max_items: int = 96,
    ) -> list[DoseEventPendingCandidate]:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        a = from_utc if from_utc.tzinfo else from_utc.replace(tzinfo=UTC)
        b = (
            until_utc_exclusive
            if until_utc_exclusive.tzinfo
            else until_utc_exclusive.replace(tzinfo=UTC)
        )
        from_iso = a.isoformat()
        until_iso = b.isoformat()
        limit = max(1, max_items)

        def q_rows() -> Any:
            return (
                self._client.table("dose_events")
                .select("id, scheduled_at, medications(name, dosage, schedule)")
                .eq("patient_id", uid)
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .gte("scheduled_at", from_iso)
                .lt("scheduled_at", until_iso)
                .order("scheduled_at", desc=False)
                .limit(limit)
                .execute()
            )

        resp = await _run_q(q_rows)
        rows = resp.data or []
        out: list[DoseEventPendingCandidate] = []
        for r in rows:
            med = r.get("medications")
            if isinstance(med, list):
                med = med[0] if med else None
            if not isinstance(med, dict):
                continue
            out.append(
                DoseEventPendingCandidate(
                    dose_event_id=str(r["id"]),
                    medication_name=str(med.get("name") or ""),
                    dosage=str(med.get("dosage") or ""),
                    schedule=str(med.get("schedule") or ""),
                    scheduled_at=_parse_ts(r["scheduled_at"]),
                )
            )
        return out

    async def list_recent_taken_dose_candidates(
        self, line_user_id: str, *, max_items: int = 5
    ) -> list[DoseEventPendingCandidate]:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        cutoff_iso = (
            datetime.now(UTC) - timedelta(hours=_RECENT_TAKEN_DOSE_NOTE_HOURS)
        ).isoformat()
        limit = max(1, max_items)

        def q_rows() -> Any:
            return (
                self._client.table("dose_events")
                .select("id, scheduled_at, medications(name, dosage, schedule)")
                .eq("patient_id", uid)
                .not_.is_("taken_at", "null")
                .gte("taken_at", cutoff_iso)
                .order("taken_at", desc=True)
                .limit(limit)
                .execute()
            )

        resp = await _run_q(q_rows)
        rows = resp.data or []
        out: list[DoseEventPendingCandidate] = []
        for r in rows:
            med = r.get("medications")
            if isinstance(med, list):
                med = med[0] if med else None
            if not isinstance(med, dict):
                continue
            out.append(
                DoseEventPendingCandidate(
                    dose_event_id=str(r["id"]),
                    medication_name=str(med.get("name") or ""),
                    dosage=str(med.get("dosage") or ""),
                    schedule=str(med.get("schedule") or ""),
                    scheduled_at=_parse_ts(r["scheduled_at"]),
                )
            )
        return out

    async def mark_dose_events_taken(
        self,
        line_user_id: str,
        dose_event_ids: list[str],
        *,
        notes: str | None = None,
    ) -> int:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        now_iso = datetime.now(UTC).isoformat()
        payload: dict[str, Any] = {"taken_at": now_iso}
        if notes is not None:
            n = notes.strip()
            if len(n) > 500:
                n = n[:500]
            if n:
                payload["notes"] = n
        total = 0
        for eid in dose_event_ids:

            def q(eid: str = eid) -> Any:
                return (
                    self._client.table("dose_events")
                    .update(payload)
                    .eq("id", eid)
                    .eq("patient_id", uid)
                    .is_("taken_at", "null")
                    .is_("missed_at", "null")
                    .lte("scheduled_at", now_iso)
                    .execute()
                )

            uresp = await _run_q(q)
            rows = uresp.data or []
            total += len(rows)
        log.info(
            "DB dose_events.mark_taken_by_ids: patient_id=%s requested=%d updated=%d",
            uid,
            len(dose_event_ids),
            total,
        )
        return total

    async def mark_pending_doses_missed(
        self, line_user_id: str, *, notes: str | None = None
    ) -> int:
        """Set ``missed_at`` on the most recent past pending dose instant (all meds at that time)."""
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        now = datetime.now(UTC)
        now_iso = now.isoformat()

        def q_latest() -> Any:
            return (
                self._client.table("dose_events")
                .select("scheduled_at")
                .eq("patient_id", uid)
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .lte("scheduled_at", now_iso)
                .order("scheduled_at", desc=True)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q_latest)
        rows = resp.data or []
        if not rows:
            return 0
        target_ts = rows[0]["scheduled_at"]

        payload: dict[str, Any] = {"missed_at": now_iso}
        if notes is not None:
            n = notes.strip()
            if len(n) > 500:
                n = n[:500]
            if n:
                payload["notes"] = n

        def q_update() -> Any:
            return (
                self._client.table("dose_events")
                .update(payload)
                .eq("patient_id", uid)
                .eq("scheduled_at", target_ts)
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .execute()
            )

        uresp = await _run_q(q_update)
        updated = uresp.data or []
        log.info("DB dose_events.mark_pending_missed: patient_id=%s updated=%d", uid, len(updated))
        return len(updated)

    async def append_note_to_dose_events(
        self,
        line_user_id: str,
        dose_event_ids: list[str],
        *,
        notes: str,
    ) -> int:
        addition = notes.strip()
        if not addition:
            return 0
        if len(addition) > 500:
            addition = addition[:500]
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        total = 0
        for eid in dose_event_ids:

            def q_sel(eid: str = eid) -> Any:
                return (
                    self._client.table("dose_events")
                    .select("notes")
                    .eq("id", eid)
                    .eq("patient_id", uid)
                    .not_.is_("taken_at", "null")
                    .limit(1)
                    .execute()
                )

            sresp = await _run_q(q_sel)
            srows = sresp.data or []
            if not srows:
                continue
            existing_notes: str | None = None
            raw_n = srows[0].get("notes")
            if isinstance(raw_n, str) and raw_n.strip():
                existing_notes = raw_n.strip()
            merged = _merge_dose_event_notes(existing_notes, addition)
            if not merged:
                continue
            merged_final = merged

            def q_upd(eid: str = eid, merged_final: str = merged_final) -> Any:
                return (
                    self._client.table("dose_events")
                    .update({"notes": merged_final})
                    .eq("id", eid)
                    .eq("patient_id", uid)
                    .not_.is_("taken_at", "null")
                    .execute()
                )

            uresp = await _run_q(q_upd)
            total += len(uresp.data or [])
        log.info(
            "DB dose_events.append_note_by_ids: patient_id=%s requested=%d updated=%d",
            uid,
            len(dose_event_ids),
            total,
        )
        return total

    async def append_note_to_recent_taken_dose(self, line_user_id: str, *, notes: str) -> int:
        """Attach ``notes`` to the dose instant with the latest ``taken_at`` (within 48h)."""
        addition = notes.strip()
        if not addition:
            return 0
        if len(addition) > 500:
            addition = addition[:500]

        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        now = datetime.now(UTC)
        cutoff = now - timedelta(hours=_RECENT_TAKEN_DOSE_NOTE_HOURS)
        cutoff_iso = cutoff.isoformat()

        def q_latest() -> Any:
            return (
                self._client.table("dose_events")
                .select("scheduled_at")
                .eq("patient_id", uid)
                .not_.is_("taken_at", "null")
                .gte("taken_at", cutoff_iso)
                .order("taken_at", desc=True)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q_latest)
        rows = resp.data or []
        if not rows:
            return 0
        target_ts = rows[0]["scheduled_at"]

        def q_existing() -> Any:
            return (
                self._client.table("dose_events")
                .select("notes")
                .eq("patient_id", uid)
                .eq("scheduled_at", target_ts)
                .not_.is_("taken_at", "null")
                .limit(1)
                .execute()
            )

        eresp = await _run_q(q_existing)
        erows = eresp.data or []
        existing_notes: str | None = None
        if erows:
            raw = erows[0].get("notes")
            if isinstance(raw, str) and raw.strip():
                existing_notes = raw.strip()

        merged = _merge_dose_event_notes(existing_notes, addition)
        if not merged:
            return 0

        def q_update() -> Any:
            return (
                self._client.table("dose_events")
                .update({"notes": merged})
                .eq("patient_id", uid)
                .eq("scheduled_at", target_ts)
                .not_.is_("taken_at", "null")
                .execute()
            )

        uresp = await _run_q(q_update)
        updated = uresp.data or []
        log.info(
            "DB dose_events.append_note_recent_taken: patient_id=%s updated=%d",
            uid,
            len(updated),
        )
        return len(updated)

    _RECONCILE_FRESH_HOURS = 48

    async def mark_stale_dose_events_missed(self, *, before_utc: datetime) -> int:
        """Bulk-close dose events older than RECONCILE_FRESH_HOURS with all-null status."""
        b = before_utc if before_utc.tzinfo else before_utc.replace(tzinfo=UTC)
        stale_cutoff = (b - timedelta(hours=self._RECONCILE_FRESH_HOURS)).isoformat()

        def q() -> Any:
            return (
                self._client.table("dose_events")
                .update({"missed_at": b.isoformat()})
                .lte("scheduled_at", stale_cutoff)
                .is_("reminder_sent_at", "null")
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .execute()
            )

        resp = await _run_q(q)
        updated = resp.data or []
        log.info("DB dose_events.stale_missed: closed=%d", len(updated))
        return len(updated)

    async def count_future_dose_events(
        self, medication_id: str, *, now_utc: datetime | None = None
    ) -> int:
        """Count pending dose rows for one med whose ``scheduled_at`` is strictly in the future."""
        now = now_utc if now_utc is not None else datetime.now(UTC)
        now_iso = (now if now.tzinfo else now.replace(tzinfo=UTC)).isoformat()

        def q() -> Any:
            return (
                self._client.table("dose_events")
                .select("id", count="exact")
                .eq("medication_id", medication_id)
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .gt("scheduled_at", now_iso)
                .execute()
            )

        resp = await _run_q(q)
        cnt = getattr(resp, "count", None)
        if isinstance(cnt, int):
            return cnt
        return len(resp.data or [])

    async def list_dose_event_ids_for_reconcile(self, *, before_utc: datetime) -> list[str]:
        """Return IDs of recently-missed dose events (within RECONCILE_FRESH_HOURS) for re-enqueueing."""
        b = before_utc if before_utc.tzinfo else before_utc.replace(tzinfo=UTC)
        fresh_cutoff = (b - timedelta(hours=self._RECONCILE_FRESH_HOURS)).isoformat()

        def q() -> Any:
            return (
                self._client.table("dose_events")
                .select("id")
                .lte("scheduled_at", b.isoformat())
                .gte("scheduled_at", fresh_cutoff)
                .is_("reminder_sent_at", "null")
                .is_("taken_at", "null")
                .is_("missed_at", "null")
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return [str(r["id"]) for r in rows]
