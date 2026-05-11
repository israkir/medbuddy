"""Supabase mixin: profile and pending-state methods for SupabaseUserData."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Sequence

from medbuddy.models.domain import (
    HEALTH_ROUTING_INTENT_VITAL,
    DoseClarificationPending,
    HealthConditionInput,
    HealthConditionRecord,
    HealthIssueEventRecord,
    MedicationAddConfirmationPending,
    ReminderHorizonPending,
    parse_pending_agent_clarification,
)
from medbuddy.core.locale import effective_user_locale, normalize_locale_patch
from medbuddy.core.timezone import effective_user_timezone, normalize_timezone_patch
from medbuddy.application.profile.emergency_contacts import (
    normalize_emergency_contacts,
)

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


_ALLOWED_HEALTH_CONDITION_CATEGORIES = frozenset({"allergy", "condition", "history"})


def _health_condition_db_row_to_record(row: dict[str, Any]) -> HealthConditionRecord:
    ts_raw = row.get("created_at")
    created = _parse_ts(ts_raw) if ts_raw is not None else datetime.now(UTC)
    sev_raw = row.get("severity")
    severity = sev_raw.strip() if isinstance(sev_raw, str) and sev_raw.strip() else None
    notes_raw = row.get("notes")
    notes = notes_raw.strip() if isinstance(notes_raw, str) and notes_raw.strip() else None
    return HealthConditionRecord(
        id=str(row["id"]),
        category=str(row.get("category") or "condition"),
        name=str(row.get("name") or "").strip(),
        severity=severity,
        notes=notes,
        is_active=bool(row.get("is_active", True)),
        created_at=created,
    )


def _user_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    contacts = normalize_emergency_contacts(row.get("emergency_contacts"))
    return {
        "id": str(row["id"]),
        "line_user_id": row["external_user_id"],
        "preferred_name": row.get("preferred_name"),
        "age_years": row.get("age_years"),
        "gender": row.get("gender"),
        "emergency_contacts": contacts,
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
                    "onboarding_completed_at, timezone, locale"
                )
                .eq("external_user_id", external_user_id)
                .limit(1)
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        if not rows:
            return None
        row = dict(rows[0])
        row["emergency_contacts"] = await self._list_emergency_contacts(str(row["id"]))
        return row

    async def _list_emergency_contacts(self, patient_id: str) -> list[dict[str, Any]]:
        def q() -> Any:
            return (
                self._client.table("emergency_contacts")
                .select(
                    "id, contact_name, relationship, channel_type, channel_value, "
                    "is_primary, notes, source, created_at, updated_at"
                )
                .eq("patient_id", patient_id)
                .order("is_primary", desc=True)
                .order("created_at", desc=False)
                .execute()
            )

        rows = (await _run_q(q)).data or []
        return normalize_emergency_contacts(rows)

    async def _merge_emergency_contacts(
        self, patient_id: str, contacts: list[dict[str, str | bool]]
    ) -> None:
        """Append/update emergency contacts; only the most recently written row stays primary.

        Multiple emergency contacts are kept on file. New entries that match an
        existing ``(channel_type, channel_value)`` are updated in place; new
        unique entries are inserted. After all writes, ``is_primary`` is forced
        to ``True`` on the row with the latest ``updated_at`` only — older
        contacts are demoted automatically so the most recent contact is always
        the single primary.
        """
        normalized = normalize_emergency_contacts(contacts)
        if not normalized:
            return
        existing_rows = await self._list_emergency_contacts(patient_id)
        existing_keys = {
            (str(r.get("channel_type") or ""), str(r.get("channel_value") or ""))
            for r in existing_rows
        }
        now = datetime.now(UTC)
        for i, c in enumerate(normalized):
            ch_type = str(c.get("channel_type") or "")
            ch_val = str(c.get("channel_value") or "")
            ts = (now + timedelta(microseconds=i)).isoformat()
            payload_base: dict[str, Any] = {
                "contact_name": c.get("contact_name"),
                "relationship": c.get("relationship"),
                "notes": c.get("notes"),
                "is_primary": False,
                "updated_at": ts,
            }
            if (ch_type, ch_val) in existing_keys:

                def upd(
                    payload: dict[str, Any] = payload_base,
                    ch_type: str = ch_type,
                    ch_val: str = ch_val,
                ) -> Any:
                    return (
                        self._client.table("emergency_contacts")
                        .update(payload)
                        .eq("patient_id", patient_id)
                        .eq("channel_type", ch_type)
                        .eq("channel_value", ch_val)
                        .execute()
                    )

                await _run_q(upd)
            else:
                insert_payload = {
                    "patient_id": patient_id,
                    "channel_type": ch_type,
                    "channel_value": ch_val,
                    "source": "user",
                    "created_at": ts,
                    **payload_base,
                }

                def ins(payload: dict[str, Any] = insert_payload) -> Any:
                    return self._client.table("emergency_contacts").insert(payload).execute()

                await _run_q(ins)

        def fetch_latest() -> Any:
            return (
                self._client.table("emergency_contacts")
                .select("id")
                .eq("patient_id", patient_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )

        rows = (await _run_q(fetch_latest)).data or []
        if not rows:
            return
        latest_id = rows[0]["id"]

        # Single atomic UPDATE: is_primary = (id = latest_id) for all rows of this patient.
        # This replaces two sequential UPDATEs that had a race window between them.
        def set_primary() -> Any:
            return self._client.rpc(
                "medbuddy_set_emergency_primary",
                {"p_patient_id": patient_id, "p_contact_id": latest_id},
            ).execute()

        await _run_q(set_primary)

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
        emergency_contacts: list[dict[str, Any]] | None,
        health_conditions: Sequence[HealthConditionInput] | None = None,
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
            "onboarding_completed_at": now.isoformat(),
            "timezone": effective_user_timezone(timezone),
            "locale": effective_user_locale(locale),
        }
        contacts = normalize_emergency_contacts(emergency_contacts or [])

        def upd() -> Any:
            return self._client.table("patients").update(payload).eq("id", uid).execute()

        await _run_q(upd)
        if contacts:
            await self._merge_emergency_contacts(uid, contacts)
        if health_conditions:
            await self.upsert_health_conditions(line_user_id, list(health_conditions))
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
        if "emergency_contacts" in fields:
            contacts = normalize_emergency_contacts(fields["emergency_contacts"])
            await self._merge_emergency_contacts(uid, contacts)
        if not payload:
            row = await self._select_user_row(line_user_id)
            return _user_row_to_dict(row) if row else user

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

    async def upsert_health_conditions(
        self, line_user_id: str, items: Sequence[HealthConditionInput]
    ) -> list[HealthConditionRecord]:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        out: list[HealthConditionRecord] = []
        now_iso = datetime.now(UTC).isoformat()
        for item in items:
            name = (item.name or "").strip()
            if not name:
                continue
            cat = (
                item.category
                if item.category in _ALLOWED_HEALTH_CONDITION_CATEGORIES
                else "condition"
            )

            def select_match() -> Any:
                return (
                    self._client.table("patient_health_conditions")
                    .select("id, category, name, severity, notes, is_active, created_at")
                    .eq("patient_id", uid)
                    .eq("category", cat)
                    .execute()
                )

            if item.action == "remove":
                resp_rm = await _run_q(select_match)
                rows_rm = resp_rm.data or []
                match_rm = next(
                    (
                        r
                        for r in rows_rm
                        if str(r.get("name") or "").strip().lower() == name.lower()
                    ),
                    None,
                )
                if match_rm:

                    def deactivate() -> Any:
                        return (
                            self._client.table("patient_health_conditions")
                            .update({"is_active": False, "updated_at": now_iso})
                            .eq("id", str(match_rm["id"]))
                            .execute()
                        )

                    await _run_q(deactivate)
                continue

            resp = await _run_q(select_match)
            rows = resp.data or []
            match = next(
                (r for r in rows if str(r.get("name") or "").strip().lower() == name.lower()),
                None,
            )
            sev = (item.severity or "").strip() or None
            nts = (item.notes or "").strip() or None
            if match:
                pid = str(match["id"])

                def upd_existing() -> Any:
                    return (
                        self._client.table("patient_health_conditions")
                        .update(
                            {
                                "severity": sev,
                                "notes": nts,
                                "is_active": True,
                                "updated_at": now_iso,
                            }
                        )
                        .eq("id", pid)
                        .execute()
                    )

                ur = await _run_q(upd_existing)
                urows = ur.data or []
                if urows:
                    out.append(_health_condition_db_row_to_record(dict(urows[0])))
            else:
                insert_payload: dict[str, Any] = {
                    "patient_id": uid,
                    "category": cat,
                    "name": name,
                    "severity": sev,
                    "notes": nts,
                    "is_active": True,
                    "source": "user",
                    "created_at": now_iso,
                    "updated_at": now_iso,
                }

                def ins() -> Any:
                    return (
                        self._client.table("patient_health_conditions")
                        .insert(insert_payload)
                        .execute()
                    )

                try:
                    ir = await _run_q(ins)
                except Exception as e:  # noqa: BLE001
                    err = str(e).lower()
                    if "unique" not in err and "23505" not in err:
                        raise
                    resp_race = await _run_q(select_match)
                    rows_race = resp_race.data or []
                    match_race = next(
                        (
                            r
                            for r in rows_race
                            if str(r.get("name") or "").strip().lower() == name.lower()
                        ),
                        None,
                    )
                    if not match_race:
                        raise
                    pid_race = str(match_race["id"])

                    def upd_race() -> Any:
                        return (
                            self._client.table("patient_health_conditions")
                            .update(
                                {
                                    "severity": sev,
                                    "notes": nts,
                                    "is_active": True,
                                    "updated_at": now_iso,
                                }
                            )
                            .eq("id", pid_race)
                            .execute()
                        )

                    ur = await _run_q(upd_race)
                    urows = ur.data or []
                    if urows:
                        out.append(_health_condition_db_row_to_record(dict(urows[0])))
                    continue
                irows = ir.data or []
                if irows:
                    out.append(_health_condition_db_row_to_record(dict(irows[0])))
        return out

    async def deactivate_health_condition(self, line_user_id: str, condition_id: str) -> bool:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])
        now_iso = datetime.now(UTC).isoformat()

        def q() -> Any:
            return (
                self._client.table("patient_health_conditions")
                .update({"is_active": False, "updated_at": now_iso})
                .eq("id", condition_id)
                .eq("patient_id", uid)
                .execute()
            )

        resp = await _run_q(q)
        rows = resp.data or []
        return bool(rows)

    async def list_health_conditions(
        self, line_user_id: str, *, active_only: bool = True
    ) -> list[HealthConditionRecord]:
        user = await self.get_or_create_user(line_user_id)
        uid = str(user["id"])

        def q() -> Any:
            query = (
                self._client.table("patient_health_conditions")
                .select("id, category, name, severity, notes, is_active, created_at")
                .eq("patient_id", uid)
                .order("created_at", desc=True)
            )
            if active_only:
                query = query.eq("is_active", True)
            return query.execute()

        resp = await _run_q(q)
        rows = resp.data or []
        return [_health_condition_db_row_to_record(dict(r)) for r in rows]

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
