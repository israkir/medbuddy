"""Supabase mixin: profile and pending-state methods for SupabaseUserData."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Sequence

from medbuddy.models.domain import (
    HEALTH_ROUTING_INTENT_VITAL,
    DoseClarificationPending,
    HealthIssueEventRecord,
    MedicationAddConfirmationPending,
    ReminderHorizonPending,
    parse_pending_agent_clarification,
)
from medbuddy.core.locale import effective_user_locale, normalize_locale_patch
from medbuddy.core.timezone import effective_user_timezone, normalize_timezone_patch

if TYPE_CHECKING:
    pass

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
        "locale": effective_user_locale(row.get("locale")),
    }


def _health_issue_row_to_record(row: dict[str, Any]) -> HealthIssueEventRecord:
    raw = row.get("payload")
    if not isinstance(raw, dict):
        raw = {}
    notes = row.get("notes")
    nout: str | None
    if notes is None:
        nout = None
    elif isinstance(notes, str):
        nout = notes.strip() or None
    else:
        nout = str(notes)
    ts_raw = row.get("created_at") or row.get("recorded_at")
    created = _parse_ts(ts_raw) if ts_raw is not None else datetime.now(UTC)
    ri = row.get("routing_intent") or row.get("event_type") or HEALTH_ROUTING_INTENT_VITAL
    ri_s = str(ri).strip()
    if ri_s == "vital":
        ri_s = HEALTH_ROUTING_INTENT_VITAL
    k = row.get("kind")
    ds = row.get("display_summary")
    um = row.get("user_message")
    loc = row.get("locale")
    return HealthIssueEventRecord(
        id=str(row["id"]),
        routing_intent=ri_s,
        user_message=(str(um).strip() if isinstance(um, str) and um.strip() else None),
        locale=(str(loc).strip() if isinstance(loc, str) and loc.strip() else None),
        kind=(str(k).strip() if isinstance(k, str) and k.strip() else None),
        display_summary=(str(ds).strip() if isinstance(ds, str) and ds.strip() else None),
        payload=raw,
        notes=nout,
        created_at=created,
    )


def _run_q(fn: Any) -> Any:
    return asyncio.to_thread(fn)


class SupabaseProfileMixin:
    """Profile, health-issue events, and pending-state methods for SupabaseUserData."""

    # Provided by SupabaseUserData.__init__
    _client: Any
    _settings: Any

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
                    log.info("DB users.get_or_create: duplicate insert race recovered")
                    return _user_row_to_dict(row)
            log.warning("Supabase user insert failed: %s", e)
            raise

        rows = resp.data or []
        if not rows:
            row = await self._select_user_row(line_user_id)
            if not row:
                msg = "Supabase insert returned no row"
                raise RuntimeError(msg)
            log.info("DB users.get_or_create: created user via fallback select")
            return _user_row_to_dict(row)
        log.info("DB users.get_or_create: inserted new user")
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
        log.info("DB users.save_onboarding_profile: patient_id=%s updated", uid)
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
        log.info(
            "DB users.patch_profile: patient_id=%s updated_fields=%s",
            uid,
            ",".join(sorted(payload.keys())),
        )
        row = await self._select_user_row(line_user_id)
        if not row:
            msg = "Supabase user row missing after profile patch"
            raise RuntimeError(msg)
        return _user_row_to_dict(row)

    async def record_health_issue_event(
        self,
        line_user_id: str,
        *,
        routing_intent: str,
        user_message: str,
        locale: str,
    ) -> HealthIssueEventRecord:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        body: dict[str, Any] = {
            "patient_id": uid,
            "routing_intent": routing_intent.strip(),
            "user_message": user_message.strip(),
            "locale": locale.strip(),
            "payload": {},
        }

        def insert() -> Any:
            return self._client.table("health_issue_events").insert(body).execute()

        resp = await _run_q(insert)
        rows = resp.data or []
        if not rows:
            msg = "Supabase health_issue_events insert returned no row"
            raise RuntimeError(msg)
        log.info(
            "DB health_issue_events.record: patient_id=%s routing_intent=%s",
            uid,
            routing_intent.strip(),
        )
        return _health_issue_row_to_record(rows[0])

    async def list_recent_health_issue_events(
        self,
        line_user_id: str,
        *,
        limit: int = 20,
        routing_intents: Sequence[str] | None = None,
    ) -> list[HealthIssueEventRecord]:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        lim = max(1, min(limit, 200))

        def q() -> Any:
            query = (
                self._client.table("health_issue_events")
                .select(
                    "id, routing_intent, user_message, locale, kind, "
                    "display_summary, payload, notes, created_at"
                )
                .eq("patient_id", uid)
                .order("created_at", desc=True)
                .limit(lim)
            )
            if routing_intents:
                query = query.in_("routing_intent", list(routing_intents))
            return query.execute()

        resp = await _run_q(q)
        rows = resp.data or []
        return [_health_issue_row_to_record(r) for r in rows]

    async def add_vital_log(
        self,
        line_user_id: str,
        *,
        kind: str,
        display_summary: str,
        payload: dict[str, Any],
        notes: str | None = None,
        user_message: str | None = None,
        locale: str | None = None,
    ) -> HealthIssueEventRecord:
        user = await self.get_or_create_user(line_user_id)
        uid = user["id"]
        n = (notes or "").strip() or None
        um = (user_message or "").strip() or None
        loc = (locale or "").strip() or None
        body: dict[str, Any] = {
            "patient_id": uid,
            "routing_intent": HEALTH_ROUTING_INTENT_VITAL,
            "user_message": um,
            "locale": loc,
            "kind": kind.strip(),
            "display_summary": display_summary.strip(),
            "payload": dict(payload),
            "notes": n,
        }

        def insert() -> Any:
            return self._client.table("health_issue_events").insert(body).execute()

        resp = await _run_q(insert)
        rows = resp.data or []
        if not rows:
            msg = "Supabase health_issue_events insert returned no row"
            raise RuntimeError(msg)
        log.info(
            "DB health_issue_events.vital: patient_id=%s kind=%s",
            uid,
            kind.strip(),
        )
        return _health_issue_row_to_record(rows[0])

    async def list_recent_vital_logs(
        self, line_user_id: str, *, limit: int = 20
    ) -> list[HealthIssueEventRecord]:
        return await self.list_recent_health_issue_events(
            line_user_id,
            limit=limit,
            routing_intents=(HEALTH_ROUTING_INTENT_VITAL,),
        )

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

    async def get_medication_add_confirmation_pending(
        self, line_user_id: str
    ) -> MedicationAddConfirmationPending | None:
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
        parsed = parse_pending_agent_clarification(raw)
        return parsed if isinstance(parsed, MedicationAddConfirmationPending) else None

    async def set_medication_add_confirmation_pending(
        self, line_user_id: str, pending: MedicationAddConfirmationPending | None
    ) -> None:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        payload = {"pending_agent_clarification": pending.to_json() if pending else None}

        def u() -> Any:
            return self._client.table("patients").update(payload).eq("id", uid).execute()

        await _run_q(u)

    async def get_reminder_horizon_pending(
        self, line_user_id: str
    ) -> ReminderHorizonPending | None:
        def q() -> Any:
            return (
                self._client.table("patients")
                .select("pending_agent_clarification")
                .eq("external_user_id", line_user_id)
                .limit(1)
                .execute()
            )

        rows = (await _run_q(q)).data or []
        if not rows:
            return None
        raw = rows[0].get("pending_agent_clarification")
        parsed = parse_pending_agent_clarification(raw)
        return parsed if isinstance(parsed, ReminderHorizonPending) else None

    async def set_reminder_horizon_pending(
        self, line_user_id: str, pending: ReminderHorizonPending | None
    ) -> None:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        payload = {"pending_agent_clarification": pending.to_json() if pending else None}

        def u() -> Any:
            return self._client.table("patients").update(payload).eq("id", uid).execute()

        await _run_q(u)
