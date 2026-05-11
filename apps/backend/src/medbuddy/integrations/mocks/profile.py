"""Mock mixin: profile and pending-state methods for MockUserData."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, Sequence

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
from medbuddy.application.profile.emergency_contacts import (
    merge_emergency_contacts,
)
from medbuddy.core.locale import effective_user_locale, normalize_locale_patch
from medbuddy.core.timezone import effective_user_timezone, normalize_timezone_patch


def _default_profile_fields() -> dict[str, Any]:
    return {
        "preferred_name": None,
        "age_years": None,
        "gender": None,
        "emergency_contacts": [],
        "onboarding_completed_at": None,
        "locale": "zh-TW",
    }


class MockProfileMixin:
    """Profile, health-issue events, and pending-state methods for MockUserData."""

    # Provided by MockUserData.__init__
    _users: dict[str, dict[str, Any]]
    _meds: dict[str, list[Any]]
    _vitals: dict[str, list[HealthIssueEventRecord]]
    _dose_clarification: dict[str, dict[str, Any] | None]
    _health_conditions: dict[str, list[dict[str, Any]]]

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
        emergency_contacts: list[dict[str, Any]] | None,
        health_conditions: Sequence[HealthConditionInput] | None = None,
        timezone: str | None = None,
        locale: str = "zh-TW",
    ) -> dict[str, Any]:
        await asyncio.sleep(0)
        row = await self.get_or_create_user(line_user_id)
        row["preferred_name"] = preferred_name.strip()
        row["age_years"] = age_years
        row["gender"] = gender
        row["emergency_contacts"] = merge_emergency_contacts(
            row.get("emergency_contacts"), emergency_contacts or []
        )
        row["onboarding_completed_at"] = datetime.now(UTC)
        row["timezone"] = effective_user_timezone(timezone)
        row["locale"] = effective_user_locale(locale)
        if health_conditions:
            await self.upsert_health_conditions(line_user_id, list(health_conditions))
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
        if "emergency_contacts" in fields:
            row["emergency_contacts"] = merge_emergency_contacts(
                row.get("emergency_contacts"), fields["emergency_contacts"]
            )
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

    def _mock_hc_row_to_record(self, d: dict[str, Any]) -> HealthConditionRecord:
        created = d.get("created_at")
        if isinstance(created, datetime):
            ts = created if created.tzinfo else created.replace(tzinfo=UTC)
        else:
            ts = datetime.now(UTC)
        sev_raw = d.get("severity")
        severity = sev_raw.strip() if isinstance(sev_raw, str) and sev_raw.strip() else None
        notes_raw = d.get("notes")
        notes = notes_raw.strip() if isinstance(notes_raw, str) and notes_raw.strip() else None
        return HealthConditionRecord(
            id=str(d["id"]),
            category=str(d.get("category") or "condition"),
            name=str(d.get("name") or "").strip(),
            severity=severity,
            notes=notes,
            is_active=bool(d.get("is_active", True)),
            created_at=ts,
        )

    async def upsert_health_conditions(
        self, line_user_id: str, items: Sequence[HealthConditionInput]
    ) -> list[HealthConditionRecord]:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        bucket = self._health_conditions.setdefault(line_user_id, [])
        out: list[HealthConditionRecord] = []
        allowed = frozenset({"allergy", "condition", "history"})
        for item in items:
            name = (item.name or "").strip()
            if not name:
                continue
            cat = item.category if item.category in allowed else "condition"
            if item.action == "remove":
                for d in bucket:
                    if (
                        str(d.get("category")) == cat
                        and str(d.get("name") or "").strip().lower() == name.lower()
                    ):
                        d["is_active"] = False
                continue
            match = next(
                (
                    d
                    for d in bucket
                    if str(d.get("category")) == cat
                    and str(d.get("name") or "").strip().lower() == name.lower()
                ),
                None,
            )
            sev = (item.severity or "").strip() or None
            nts = (item.notes or "").strip() or None
            if match:
                match["severity"] = sev
                match["notes"] = nts
                match["is_active"] = True
                match["updated_at"] = datetime.now(UTC)
                out.append(self._mock_hc_row_to_record(match))
            else:
                rec = {
                    "id": str(uuid.uuid4()),
                    "category": cat,
                    "name": name,
                    "severity": sev,
                    "notes": nts,
                    "is_active": True,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
                bucket.append(rec)
                out.append(self._mock_hc_row_to_record(rec))
        return out

    async def deactivate_health_condition(self, line_user_id: str, condition_id: str) -> bool:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        bucket = self._health_conditions.setdefault(line_user_id, [])
        for d in bucket:
            if str(d.get("id")) == condition_id:
                d["is_active"] = False
                d["updated_at"] = datetime.now(UTC)
                return True
        return False

    async def list_health_conditions(
        self, line_user_id: str, *, active_only: bool = True
    ) -> list[HealthConditionRecord]:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        bucket = list(self._health_conditions.get(line_user_id, []))
        if active_only:
            bucket = [d for d in bucket if d.get("is_active", True)]
        bucket.sort(
            key=lambda d: d.get("created_at") or datetime.min.replace(tzinfo=UTC), reverse=True
        )
        return [self._mock_hc_row_to_record(d) for d in bucket]

    async def record_health_issue_event(
        self,
        line_user_id: str,
        *,
        routing_intent: str,
        user_message: str,
        locale: str,
    ) -> HealthIssueEventRecord:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        rec = HealthIssueEventRecord(
            id=str(uuid.uuid4()),
            routing_intent=routing_intent.strip(),
            user_message=user_message.strip(),
            locale=locale.strip(),
            kind=None,
            display_summary=None,
            payload={},
            notes=None,
            created_at=datetime.now(UTC),
        )
        self._vitals.setdefault(line_user_id, []).append(rec)
        return rec

    async def list_recent_health_issue_events(
        self,
        line_user_id: str,
        *,
        limit: int = 20,
        routing_intents: Sequence[str] | None = None,
    ) -> list[HealthIssueEventRecord]:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        items = list(self._vitals.get(line_user_id, []))
        if routing_intents:
            allowed = frozenset(routing_intents)
            items = [r for r in items if r.routing_intent in allowed]
        items.sort(key=lambda r: r.created_at, reverse=True)
        return items[: max(1, min(limit, 200))]

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
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        n = (notes or "").strip() or None
        um = (user_message or "").strip() or None
        loc = (locale or "").strip() or None
        rec = HealthIssueEventRecord(
            id=str(uuid.uuid4()),
            routing_intent=HEALTH_ROUTING_INTENT_VITAL,
            user_message=um,
            locale=loc,
            kind=kind.strip(),
            display_summary=display_summary.strip(),
            payload=dict(payload),
            notes=n,
            created_at=datetime.now(UTC),
        )
        self._vitals.setdefault(line_user_id, []).append(rec)
        return rec

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

    async def get_medication_add_confirmation_pending(
        self, line_user_id: str
    ) -> MedicationAddConfirmationPending | None:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        raw = self._dose_clarification.get(line_user_id)
        parsed = parse_pending_agent_clarification(raw) if raw else None
        return parsed if isinstance(parsed, MedicationAddConfirmationPending) else None

    async def set_medication_add_confirmation_pending(
        self, line_user_id: str, pending: MedicationAddConfirmationPending | None
    ) -> None:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        self._dose_clarification[line_user_id] = pending.to_json() if pending else None

    async def get_reminder_horizon_pending(
        self, line_user_id: str
    ) -> ReminderHorizonPending | None:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        raw = self._dose_clarification.get(line_user_id)
        parsed = parse_pending_agent_clarification(raw) if raw else None
        return parsed if isinstance(parsed, ReminderHorizonPending) else None

    async def set_reminder_horizon_pending(
        self, line_user_id: str, pending: ReminderHorizonPending | None
    ) -> None:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        self._dose_clarification[line_user_id] = pending.to_json() if pending else None
