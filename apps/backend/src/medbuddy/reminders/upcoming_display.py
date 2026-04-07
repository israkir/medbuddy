"""Format pending dose_events for user replies and LLM patient context (local timezone)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from medbuddy.i18n import t
from medbuddy.models.domain import DoseEventPendingCandidate


def upcoming_schedule_window_utc(
    tz_name: str, now_utc: datetime, *, horizon_days: int = 7
) -> tuple[datetime, datetime]:
    """Return ``[start, end)`` in UTC: local midnight through ``horizon_days`` full calendar days."""
    tz = ZoneInfo(tz_name)
    local = now_utc.astimezone(tz)
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local_exclusive = start_local + timedelta(days=horizon_days)
    return start_local.astimezone(UTC), end_local_exclusive.astimezone(UTC)


def _format_local_time_label(
    scheduled_at: datetime, tz_name: str, now_utc: datetime, *, locale: str
) -> str:
    tz = ZoneInfo(tz_name)
    local = scheduled_at.astimezone(tz)
    now_local = now_utc.astimezone(tz)
    hm = local.strftime("%H:%M")
    if local.date() != now_local.date():
        return t(
            "medication.upcoming_time_other_day",
            locale=locale,
            date=local.strftime("%Y-%m-%d"),
            time=hm,
        )
    return hm


def format_upcoming_doses_lines(
    rows: list[DoseEventPendingCandidate],
    *,
    tz_name: str,
    now_utc: datetime,
    locale: str,
    for_llm: bool,
) -> list[str]:
    """One line per dose: local time, name, dose; optional due marker."""
    lines: list[str] = []
    for r in rows:
        time_lbl = _format_local_time_label(r.scheduled_at, tz_name, now_utc, locale=locale)
        due = (
            (r.scheduled_at <= now_utc)
            if r.scheduled_at.tzinfo
            else (r.scheduled_at.replace(tzinfo=UTC) <= now_utc)
        )
        due_suffix = t("medication.upcoming_due_suffix", locale=locale) if due else ""
        if for_llm:
            lines.append(
                t(
                    "prompts.upcoming_dose_line",
                    locale=locale,
                    time_local=time_lbl,
                    name=r.medication_name,
                    dosage=r.dosage,
                    schedule=r.schedule,
                    due_suffix=due_suffix,
                )
            )
        else:
            lines.append(
                t(
                    "medication.upcoming_line",
                    locale=locale,
                    time_local=time_lbl,
                    name=r.medication_name,
                    dosage=r.dosage,
                    schedule=r.schedule,
                    due_suffix=due_suffix,
                )
            )
    return lines


def format_upcoming_doses_for_llm(
    rows: list[DoseEventPendingCandidate],
    *,
    tz_name: str,
    now_utc: datetime,
    locale: str,
) -> str:
    if not rows:
        return t("prompts.upcoming_doses_none", locale=locale)
    intro = t("prompts.upcoming_doses_intro", locale=locale)
    body = "\n".join(
        format_upcoming_doses_lines(
            rows, tz_name=tz_name, now_utc=now_utc, locale=locale, for_llm=True
        )
    )
    return f"{intro}\n{body}"


def format_upcoming_doses_user_reply(
    rows: list[DoseEventPendingCandidate],
    *,
    tz_name: str,
    now_utc: datetime,
    locale: str,
) -> str:
    if not rows:
        return t("medication.upcoming_empty", locale=locale)
    intro = t("medication.upcoming_intro", locale=locale)
    body = "\n".join(
        format_upcoming_doses_lines(
            rows, tz_name=tz_name, now_utc=now_utc, locale=locale, for_llm=False
        )
    )
    return f"{intro}\n{body}"
