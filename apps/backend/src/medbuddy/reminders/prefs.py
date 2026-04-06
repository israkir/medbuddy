"""Per-medication reminder preferences (stored in medications.raw_metadata['reminder'])."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from medbuddy.i18n import t
from medbuddy.models.domain import MedicationDraft, MedicationRecord
from medbuddy.reminders.dose_schedule import iter_scheduled_dose_times_utc, parse_hhmm


@dataclass(frozen=True)
class ReminderPrefs:
    """Scheduling hints for dose_events materialization (from LLM + stored metadata)."""

    first_reminder_in_minutes: int | None = None
    materialize_daily: bool = True
    horizon_days: int | None = None
    needs_horizon_confirmation: bool = False
    daily_local_hhmm: str | None = None


def reminder_prefs_from_metadata(raw_metadata: dict[str, Any] | None) -> ReminderPrefs:
    if not raw_metadata:
        return ReminderPrefs()
    rem = raw_metadata.get("reminder")
    if not isinstance(rem, dict):
        return ReminderPrefs()
    fm = rem.get("first_reminder_in_minutes")
    first_min: int | None = None
    if isinstance(fm, (int, float)):
        first_min = int(fm)
    horizon = rem.get("horizon_days")
    horizon_days: int | None = None
    if isinstance(horizon, (int, float)):
        horizon_days = int(horizon)
    hh = rem.get("daily_local_hhmm")
    daily_hhmm: str | None = None
    if isinstance(hh, str) and hh.strip():
        try:
            parse_hhmm(hh.strip())
            daily_hhmm = hh.strip()
        except ValueError:
            daily_hhmm = None
    return ReminderPrefs(
        first_reminder_in_minutes=first_min,
        materialize_daily=bool(rem.get("materialize_daily", True)),
        horizon_days=horizon_days,
        needs_horizon_confirmation=bool(rem.get("needs_horizon_confirmation", False)),
        daily_local_hhmm=daily_hhmm,
    )


def reminder_blob_from_draft(draft: MedicationDraft) -> dict[str, Any]:
    """Subset of draft fields persisted under raw_metadata['reminder']."""
    return {
        "first_reminder_in_minutes": draft.first_reminder_in_minutes,
        "materialize_daily": draft.materialize_daily_reminders,
        "horizon_days": draft.reminder_horizon_days,
        "needs_horizon_confirmation": draft.needs_horizon_confirmation,
        "daily_local_hhmm": draft.daily_reminder_local_hhmm,
    }


def iter_dose_instants_for_medication(
    prefs: ReminderPrefs,
    *,
    tz_name: str,
    default_local_hhmm: str,
    default_horizon_days: int,
    now_utc: datetime,
) -> list[datetime]:
    """UTC instants for one medication: optional first relative reminder + optional daily grid."""
    now = now_utc if now_utc.tzinfo else now_utc.replace(tzinfo=UTC)
    out: list[datetime] = []

    fm = prefs.first_reminder_in_minutes
    if isinstance(fm, int) and fm > 0:
        first_at = now + timedelta(minutes=fm)
        if first_at > now:
            out.append(first_at)

    if prefs.needs_horizon_confirmation and prefs.first_reminder_in_minutes is None:
        return _dedupe_sorted(out)

    daily_ok = prefs.materialize_daily and not prefs.needs_horizon_confirmation
    if daily_ok:
        raw_h = prefs.horizon_days if prefs.horizon_days is not None else default_horizon_days
        horizon = max(1, min(90, int(raw_h)))
        hhmm = (prefs.daily_local_hhmm or default_local_hhmm).strip()
        daily_times = iter_scheduled_dose_times_utc(
            tz_name=tz_name,
            local_hhmm=hhmm,
            horizon_days=horizon,
            now_utc=now,
        )
        out.extend(daily_times)

    return _dedupe_sorted(out)


def _dedupe_sorted(instants: list[datetime]) -> list[datetime]:
    seen: set[datetime] = set()
    unique: list[datetime] = []
    for dt in instants:
        if dt not in seen:
            seen.add(dt)
            unique.append(dt)
    unique.sort()
    return unique


def reminder_compose_appendix(saved: MedicationRecord, locale: str) -> str:
    """Extra instructions for compose_medication_added_reply from stored reminder prefs."""
    raw = saved.raw_metadata or {}
    rem = raw.get("reminder") if isinstance(raw, dict) else None
    if not isinstance(rem, dict):
        return ""
    lines: list[str] = []
    if rem.get("needs_horizon_confirmation"):
        lines.append(t("gemini.added_ask_reminder_horizon", locale=locale))
    fm = rem.get("first_reminder_in_minutes")
    md = bool(rem.get("materialize_daily", True))
    if isinstance(fm, (int, float)) and int(fm) > 0:
        if md:
            lines.append(
                t(
                    "gemini.added_first_reminder_plus_daily",
                    locale=locale,
                    minutes=int(fm),
                )
            )
        else:
            lines.append(t("gemini.added_first_reminder_only", locale=locale, minutes=int(fm)))
    elif md and not rem.get("needs_horizon_confirmation"):
        hd = rem.get("horizon_days")
        if isinstance(hd, (int, float)):
            lines.append(t("gemini.added_daily_horizon_days", locale=locale, days=int(hd)))
    if not lines:
        return ""
    return "\n\n" + "\n".join(lines)
