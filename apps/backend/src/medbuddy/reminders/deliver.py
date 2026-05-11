"""Send LINE push for dose_events: primary reminder and optional follow-up nudges."""

from __future__ import annotations

import hashlib
import logging
import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

_NUDGE_JITTER_SECONDS = 30  # ±30 s applied at enqueue time to spread fan-out

from medbuddy.services import AppServices  # noqa: E402
from medbuddy.core.i18n import t  # noqa: E402
from medbuddy.llm.medication_draft_build import dose_or_schedule_display  # noqa: E402
from medbuddy.reminders.enqueue import enqueue_reminder_nudge_job  # noqa: E402

log = logging.getLogger(__name__)


def _should_append_education_cta(
    *,
    user_key: str,
    medication_name: str,
    local_dt: datetime,
    every_n_days: int,
) -> bool:
    if every_n_days <= 0:
        return False
    day_bucket = local_dt.date().toordinal() // every_n_days
    stable = hashlib.sha256(f"{user_key}:{medication_name}".encode("utf-8")).hexdigest()
    slot = int(stable[-2:], 16) % every_n_days
    return (local_dt.date().toordinal() % every_n_days) == slot and day_bucket >= 0


async def deliver_dose_reminder(
    svc: AppServices,
    dose_event_id: str,
    scheduled_at_iso: str | None = None,
) -> bool:
    """Load the row, push LINE text, then mark sent. Returns True if a push was attempted.

    ``scheduled_at_iso`` is the ISO-8601 timestamp baked into the arq job at enqueue time.
    If it no longer matches the live row (e.g. the event was rescheduled or deleted and
    recreated), the job is dropped to avoid double-firing on a stale id.
    """
    payload = await svc.users.get_dose_event_for_reminder(dose_event_id)
    if payload is None:
        log.info(
            "reminder skip: no pending row for dose_event_id=%s (stale id or already handled)",
            dose_event_id,
        )
        return False

    if scheduled_at_iso is not None:
        live_iso = payload.scheduled_at.isoformat()
        if live_iso != scheduled_at_iso:
            log.info(
                "reminder skip: scheduled_at mismatch dose_event_id=%s "
                "expected=%s actual=%s (row rescheduled or recreated)",
                dose_event_id,
                scheduled_at_iso,
                live_iso,
            )
            return False

    locale = payload.user_locale
    un = t("medication.unspecified", locale=locale)
    tz = ZoneInfo(payload.user_timezone)
    local = payload.scheduled_at.astimezone(tz)
    time_str = local.strftime("%H:%M")
    text = t(
        "reminder.line_push",
        locale=locale,
        name=payload.medication_name,
        dosage=dose_or_schedule_display(payload.dosage, unspecified_label=un),
        schedule=dose_or_schedule_display(payload.schedule, unspecified_label=un),
        time_local=time_str,
    )
    if _should_append_education_cta(
        user_key=payload.line_user_id,
        medication_name=payload.medication_name,
        local_dt=local,
        every_n_days=svc.settings.reminder_education_cta_every_n_days,
    ):
        text = f"{text}\n{t('reminder.education_cta', locale=locale)}"
        log.info(
            "reminder education_cta_shown user=%s med=%s dose_event_id=%s",
            payload.line_user_id,
            payload.medication_name,
            dose_event_id,
        )
    else:
        log.info(
            "reminder education_cadence_suppressed user=%s med=%s dose_event_id=%s",
            payload.line_user_id,
            payload.medication_name,
            dose_event_id,
        )
    await svc.line.push_message_batch(payload.line_user_id, [{"type": "text", "text": text}])
    marked = await svc.users.try_mark_reminder_sent(dose_event_id)
    if not marked:
        log.warning(
            "reminder: push sent but try_mark_reminder_sent false for dose_event_id=%s",
            dose_event_id,
        )
    elif marked and svc.settings.reminder_nudge_intervals_minutes and svc.settings.redis_url:
        await _enqueue_first_nudge(svc, dose_event_id)
    return True


async def deliver_dose_reminder_nudge(
    svc: AppServices, dose_event_id: str, expected_nudge_count: int
) -> bool:
    """Send a follow-up nudge if the dose is still not marked taken. Returns True if a push ran."""
    intervals = svc.settings.reminder_nudge_intervals_minutes
    if not intervals:
        return False
    max_n = len(intervals)
    payload = await svc.users.get_dose_event_for_nudge(
        dose_event_id,
        expected_nudge_count=expected_nudge_count,
        max_nudges=max_n,
    )
    if payload is None:
        log.debug(
            "reminder nudge skip: dose_event_id=%s expected_nudge_count=%s",
            dose_event_id,
            expected_nudge_count,
        )
        return False

    locale = payload.user_locale
    un = t("medication.unspecified", locale=locale)
    tz = ZoneInfo(payload.user_timezone)
    local = payload.scheduled_at.astimezone(tz)
    time_str = local.strftime("%H:%M")
    text = t(
        "reminder.line_push_nudge",
        locale=locale,
        name=payload.medication_name,
        dosage=dose_or_schedule_display(payload.dosage, unspecified_label=un),
        schedule=dose_or_schedule_display(payload.schedule, unspecified_label=un),
        time_local=time_str,
    )
    await svc.line.push_message_batch(payload.line_user_id, [{"type": "text", "text": text}])
    ok = await svc.users.try_increment_reminder_nudge(
        dose_event_id, expected_nudge_count=expected_nudge_count
    )
    if not ok:
        log.warning(
            "reminder: nudge push sent but try_increment_reminder_nudge false "
            "for dose_event_id=%s expected_nudge_count=%s",
            dose_event_id,
            expected_nudge_count,
        )
    elif ok and expected_nudge_count + 1 < max_n:
        nxt = expected_nudge_count + 1
        delay_min = intervals[nxt]
        jitter = random.uniform(-_NUDGE_JITTER_SECONDS, _NUDGE_JITTER_SECONDS)
        defer_until = datetime.now(UTC) + timedelta(minutes=delay_min, seconds=jitter)
        await enqueue_reminder_nudge_job(svc.settings.redis_url, dose_event_id, nxt, defer_until)
    return True


async def _enqueue_first_nudge(svc: AppServices, dose_event_id: str) -> None:
    intervals = svc.settings.reminder_nudge_intervals_minutes
    redis_url = svc.settings.redis_url
    if not intervals or not redis_url:
        return
    delay_min = intervals[0]
    jitter = random.uniform(-_NUDGE_JITTER_SECONDS, _NUDGE_JITTER_SECONDS)
    defer_until = datetime.now(UTC) + timedelta(minutes=delay_min, seconds=jitter)
    await enqueue_reminder_nudge_job(redis_url, dose_event_id, 0, defer_until)
