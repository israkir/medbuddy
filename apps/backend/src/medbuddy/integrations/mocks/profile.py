"""Mock mixin: profile and pending-state methods for MockUserData."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from medbuddy.models.domain import (
    DoseClarificationPending,
    MedicationAddConfirmationPending,
    ReminderHorizonPending,
    VitalLogRecord,
    parse_pending_agent_clarification,
)
from medbuddy.core.locale import effective_user_locale, normalize_locale_patch
from medbuddy.core.timezone import effective_user_timezone, normalize_timezone_patch


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


class MockProfileMixin:
    """Profile, vital-log and pending-state methods for MockUserData."""

    # Provided by MockUserData.__init__
    _users: dict[str, dict[str, Any]]
    _meds: dict[str, list[Any]]
    _vitals: dict[str, list[VitalLogRecord]]
    _dose_clarification: dict[str, dict[str, Any] | None]

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

    async def add_vital_log(
        self,
        line_user_id: str,
        *,
        kind: str,
        display_summary: str,
        payload: dict[str, Any],
        notes: str | None = None,
    ) -> VitalLogRecord:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        n = (notes or "").strip() or None
        rec = VitalLogRecord(
            id=str(uuid.uuid4()),
            kind=kind.strip(),
            display_summary=display_summary.strip(),
            payload=dict(payload),
            notes=n,
            recorded_at=datetime.now(UTC),
        )
        self._vitals.setdefault(line_user_id, []).append(rec)
        return rec

    async def list_recent_vital_logs(
        self, line_user_id: str, *, limit: int = 20
    ) -> list[VitalLogRecord]:
        await asyncio.sleep(0)
        await self.get_or_create_user(line_user_id)
        items = list(self._vitals.get(line_user_id, []))
        items.sort(key=lambda r: r.recorded_at, reverse=True)
        return items[: max(1, min(limit, 100))]

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
