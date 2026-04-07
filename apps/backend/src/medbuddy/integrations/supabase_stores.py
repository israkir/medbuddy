"""Supabase (Postgres) implementations of user and conversation persistence."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from medbuddy.config import Settings
from medbuddy.models.domain import (
    ConversationTurn,
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
from medbuddy.protocols.ports import ConversationStorePort, UserDataPort
from medbuddy.reminders.nudge_policy import nudge_window_allows
from medbuddy.user_locale import effective_user_locale, normalize_locale_patch
from medbuddy.user_timezone import effective_user_timezone, normalize_timezone_patch

log = logging.getLogger(__name__)

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


def _parse_ts(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(s)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    msg = f"Unsupported timestamp value from DB: {type(value)}"
    raise TypeError(msg)


def _user_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "line_user_id": row["external_user_id"],
        "preferred_name": row.get("preferred_name"),
        "age_years": row.get("age_years"),
        "gender": row.get("gender"),
        "emergency_contact": row.get("emergency_contact"),
        "health_notes": row.get("health_notes"),
        "onboarding_completed_at": row.get("onboarding_completed_at"),
        "timezone": row.get("timezone") or "Asia/Taipei",
        "locale": effective_user_locale(row.get("locale")),
    }


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


def create_supabase_client(settings: Settings) -> Any:
    """Build the Supabase sync client.

    postgrest-py defaults to ``httpx.Client(..., http2=True)``. HTTP/2 can raise
    ``RemoteProtocolError`` / ``ConnectionTerminated`` against some hosts or proxies;
    we use HTTP/1.1 for the shared httpx client instead.
    """
    import httpx
    from postgrest.constants import DEFAULT_POSTGREST_CLIENT_TIMEOUT
    from supabase import ClientOptions, create_client

    http_client = httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(DEFAULT_POSTGREST_CLIENT_TIMEOUT),
        http2=False,
    )
    options = ClientOptions(httpx_client=http_client)
    return create_client(settings.supabase_url, settings.supabase_publishable_key, options)


def _run_q(fn: Any) -> Any:
    return asyncio.to_thread(fn)


class SupabaseUserData(UserDataPort):
    """Users + medications backed by Supabase Postgres."""

    def __init__(self, client: Any, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def _select_user_row(self, external_user_id: str) -> dict[str, Any] | None:
        def q() -> Any:
            return (
                self._client.table("patients")
                .select(
                    "id, external_user_id, preferred_name, age_years, gender, "
                    "emergency_contact, health_notes, onboarding_completed_at, timezone, locale"
                )
                .eq("external_user_id", external_user_id)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return rows[0] if rows else None

    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]:
        row = await self._select_user_row(line_user_id)
        if row:
            return _user_row_to_dict(row)

        def insert() -> Any:
            return (
                self._client.table("patients").insert({"external_user_id": line_user_id}).execute()
            )

        try:
            resp = await _run_q(insert)
        except Exception as e:  # noqa: BLE001 — PostgREST / httpx errors vary by version
            msg = str(e).lower()
            if "duplicate" in msg or "unique" in msg or "23505" in msg:
                row = await self._select_user_row(line_user_id)
                if row:
                    return _user_row_to_dict(row)
            log.warning("Supabase user insert failed: %s", e)
            raise

        rows = resp.data or []
        if not rows:
            row = await self._select_user_row(line_user_id)
            if not row:
                msg = "Supabase insert returned no row"
                raise RuntimeError(msg)
            return _user_row_to_dict(row)
        return _user_row_to_dict(rows[0])

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
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "preferred_name": preferred_name.strip(),
            "age_years": age_years,
            "gender": gender,
            "emergency_contact": (emergency_contact or "").strip() or None,
            "health_notes": (health_notes or "").strip() or None,
            "onboarding_completed_at": now.isoformat(),
            "timezone": effective_user_timezone(timezone),
            "locale": effective_user_locale(locale),
        }

        def upd() -> Any:
            return self._client.table("patients").update(payload).eq("id", uid).execute()

        await _run_q(upd)
        row = await self._select_user_row(line_user_id)
        if not row:
            msg = "Supabase user row missing after onboarding update"
            raise RuntimeError(msg)
        return _user_row_to_dict(row)

    async def patch_user_profile(self, line_user_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        payload: dict[str, Any] = {}
        if "preferred_name" in fields:
            pn = fields["preferred_name"]
            if isinstance(pn, str) and pn.strip():
                payload["preferred_name"] = pn.strip()
        if "age_years" in fields:
            age = fields["age_years"]
            if age is None:
                payload["age_years"] = None
            elif isinstance(age, int) and 0 <= age <= 120:
                payload["age_years"] = age
            elif isinstance(age, float) and age.is_integer():
                ai = int(age)
                if 0 <= ai <= 120:
                    payload["age_years"] = ai
        if "gender" in fields:
            raw_g = fields["gender"]
            if raw_g is None:
                payload["gender"] = None
            elif isinstance(raw_g, str):
                g = raw_g.strip().lower()
                allowed = {"female", "male", "non_binary", "prefer_not_say", "other"}
                if g in allowed:
                    payload["gender"] = g
        for key in ("emergency_contact", "health_notes"):
            if key in fields:
                raw = fields[key]
                if raw is None:
                    payload[key] = None
                elif isinstance(raw, str):
                    payload[key] = raw.strip() or None
        if "timezone" in fields:
            norm = normalize_timezone_patch(fields["timezone"])
            if norm is not None:
                payload["timezone"] = norm
            elif fields["timezone"] is None:
                payload["timezone"] = None
        if "locale" in fields:
            norm_loc = normalize_locale_patch(fields["locale"])
            if norm_loc is not None:
                payload["locale"] = norm_loc
        if not payload:
            return user

        def upd() -> Any:
            return self._client.table("patients").update(payload).eq("id", uid).execute()

        await _run_q(upd)
        row = await self._select_user_row(line_user_id)
        if not row:
            msg = "Supabase user row missing after profile patch"
            raise RuntimeError(msg)
        return _user_row_to_dict(row)

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
        return len(rows) > 0

    async def sync_upcoming_dose_events(self, line_user_id: str) -> list[tuple[str, datetime]]:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        tz_name = effective_user_timezone(str(user["timezone"]) if user.get("timezone") else None)
        meds = await self.list_medications(line_user_id)
        now = datetime.now(UTC)
        cutoff = now.isoformat()

        def delete_future() -> Any:
            return (
                self._client.table("dose_events")
                .delete()
                .eq("patient_id", uid)
                .gt("scheduled_at", cutoff)
                .execute()
            )

        await _run_q(delete_future)

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
                .select("id, patient_id, medication_id, scheduled_at, reminder_sent_at, taken_at")
                .eq("id", dose_event_id)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q_dose)
        drows = resp.data or []
        if not drows:
            return None
        dr = drows[0]
        if dr.get("reminder_sent_at") is not None or dr.get("taken_at") is not None:
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
                .select("name, dosage, schedule")
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
            medication_name=str(m["name"]),
            dosage=str(m["dosage"]),
            schedule=str(m["schedule"]),
            scheduled_at=scheduled_at,
            user_timezone=tz_name,
            user_locale=user_locale,
            is_nudge=False,
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
                    "taken_at, reminder_nudge_count"
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
        if dr.get("taken_at") is not None:
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
                .select("name, dosage, schedule")
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
            medication_name=str(m["name"]),
            dosage=str(m["dosage"]),
            schedule=str(m["schedule"]),
            scheduled_at=scheduled_at,
            user_timezone=tz_name,
            user_locale=user_locale,
            is_nudge=True,
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
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
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
                .execute()
            )

        uresp = await _run_q(q_update)
        updated = uresp.data or []
        return len(updated)

    async def list_pending_dose_candidates(
        self, line_user_id: str, *, max_items: int = 5
    ) -> list[DoseEventPendingCandidate]:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        now_iso = datetime.now(UTC).isoformat()
        limit = max(1, max_items)

        def q_rows() -> Any:
            return (
                self._client.table("dose_events")
                .select("id, scheduled_at, medications(name, dosage, schedule)")
                .eq("patient_id", uid)
                .is_("taken_at", "null")
                .lte("scheduled_at", now_iso)
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

    async def get_dose_clarification_pending(
        self, line_user_id: str
    ) -> DoseClarificationPending | None:
        def q() -> Any:
            return (
                self._client.table("patients")
                .select("pending_agent_clarification")
                .eq("external_user_id", line_user_id)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        if not rows:
            return None
        raw = rows[0].get("pending_agent_clarification")
        return DoseClarificationPending.from_json(raw)

    async def set_dose_clarification_pending(
        self, line_user_id: str, pending: DoseClarificationPending | None
    ) -> None:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        payload = {"pending_agent_clarification": pending.to_json() if pending else None}

        def u() -> Any:
            return self._client.table("patients").update(payload).eq("id", uid).execute()

        await _run_q(u)

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
                    .lte("scheduled_at", now_iso)
                    .execute()
                )

            uresp = await _run_q(q)
            rows = uresp.data or []
            total += len(rows)
        return total

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
        return len(updated)

    async def list_dose_event_ids_for_reconcile(self, *, before_utc: datetime) -> list[str]:
        b = before_utc if before_utc.tzinfo else before_utc.replace(tzinfo=UTC)

        def q() -> Any:
            return (
                self._client.table("dose_events")
                .select("id")
                .lte("scheduled_at", b.isoformat())
                .is_("reminder_sent_at", "null")
                .is_("taken_at", "null")
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return [str(r["id"]) for r in rows]


class SupabaseConversationStore(ConversationStorePort):
    """Conversation turns keyed by the same external user id as ``SupabaseUserData``."""

    def __init__(self, client: Any, users: SupabaseUserData) -> None:
        self._client = client
        self._users = users

    async def get_recent_turns(self, line_user_id: str, max_turns: int) -> list[ConversationTurn]:
        user = await self._users.get_or_create_user(line_user_id)
        uid = user["id"]
        if max_turns <= 0:
            return []

        def q() -> Any:
            return (
                self._client.table("conversation_turns")
                .select("role, content, created_at")
                .eq("patient_id", uid)
                .order("created_at", desc=True)
                .limit(max_turns)
                .execute()
            )

        resp = await _run_q(q)
        rows = list(reversed(resp.data or []))
        return [
            ConversationTurn(role=r["role"], content=r["content"], at=_parse_ts(r["created_at"]))
            for r in rows
        ]

    async def append_turn(self, line_user_id: str, turn: ConversationTurn) -> None:
        user = await self._users.get_or_create_user(line_user_id)
        uid = user["id"]
        at = turn.at
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        payload = {
            "patient_id": uid,
            "role": turn.role,
            "content": turn.content,
            "created_at": at.isoformat(),
        }

        def q() -> Any:
            return self._client.table("conversation_turns").insert(payload).execute()

        await _run_q(q)
