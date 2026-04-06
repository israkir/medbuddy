"""Supabase (Postgres) implementations of user and conversation persistence."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from medbuddy.config import Settings
from medbuddy.models.domain import (
    ConversationTurn,
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

log = logging.getLogger(__name__)


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
    }


def _med_row_to_record(row: dict[str, Any]) -> MedicationRecord:
    raw = row.get("raw_metadata")
    if not isinstance(raw, dict):
        raw = {}
    ins = row.get("instructions_zh")
    return MedicationRecord(
        id=str(row["id"]),
        name=row["name"],
        dosage=row["dosage"],
        schedule=row["schedule"],
        instructions_zh=ins if isinstance(ins, str) or ins is None else str(ins),
        raw_metadata=raw,
    )


def create_supabase_client(settings: Settings) -> Any:
    from supabase import create_client

    return create_client(settings.supabase_url, settings.supabase_publishable_key)


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
                self._client.table("users")
                .select(
                    "id, external_user_id, preferred_name, age_years, gender, "
                    "emergency_contact, health_notes, onboarding_completed_at, timezone"
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
            return self._client.table("users").insert({"external_user_id": line_user_id}).execute()

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
        }

        def upd() -> Any:
            return self._client.table("users").update(payload).eq("id", uid).execute()

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
        if not payload:
            return user

        def upd() -> Any:
            return self._client.table("users").update(payload).eq("id", uid).execute()

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
                .select("id, name, dosage, schedule, instructions_zh, raw_metadata")
                .eq("user_id", uid)
                .order("id")
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return [_med_row_to_record(r) for r in rows]

    async def add_medication(self, line_user_id: str, draft: MedicationDraft) -> MedicationRecord:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        ins = (draft.instructions_zh or "").strip()
        payload: dict[str, Any] = {
            "user_id": uid,
            "name": draft.name.strip(),
            "dosage": draft.dosage.strip(),
            "schedule": draft.schedule.strip(),
            "instructions_zh": ins or None,
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
                .eq("user_id", uid)
                .eq("id", medication_id)
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return len(rows) > 0

    async def sync_upcoming_dose_events(self, line_user_id: str) -> list[tuple[str, datetime]]:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        tz_name = str(user.get("timezone") or "Asia/Taipei")
        meds = await self.list_medications(line_user_id)
        now = datetime.now(UTC)
        cutoff = now.isoformat()

        def delete_future() -> Any:
            return (
                self._client.table("dose_events")
                .delete()
                .eq("user_id", uid)
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
                        "user_id": uid,
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
                .select("id, user_id, medication_id, scheduled_at, reminder_sent_at, taken_at")
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
        uid = str(dr["user_id"])
        mid = str(dr["medication_id"])
        scheduled_at = _parse_ts(dr["scheduled_at"])

        def q_user() -> Any:
            return (
                self._client.table("users")
                .select("external_user_id, timezone")
                .eq("id", uid)
                .limit(1)
                .execute()
            )

        uresp = await _run_q(q_user)
        urows = uresp.data or []
        if not urows:
            return None
        line_uid = str(urows[0]["external_user_id"])
        tz_name = str(urows[0].get("timezone") or "Asia/Taipei")

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
                .eq("user_id", uid)
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
            "user_id": uid,
            "role": turn.role,
            "content": turn.content,
            "created_at": at.isoformat(),
        }

        def q() -> Any:
            return self._client.table("conversation_turns").insert(payload).execute()

        await _run_q(q)
