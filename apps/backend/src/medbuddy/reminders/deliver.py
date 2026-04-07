"""Send LINE push for dose_events: primary reminder and optional follow-up nudges."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.reminders.enqueue import enqueue_reminder_nudge_job

log = logging.getLogger(__name__)


async def deliver_dose_reminder(svc: AppServices, dose_event_id: str) -> bool:
    """Load the row, push LINE text, then mark sent. Returns True if a push was attempted."""
    payload = await svc.users.get_dose_event_for_reminder(dose_event_id)
    if payload is None:
        log.debug("reminder skip: no pending row for dose_event_id=%s", dose_event_id)
        return False

    locale = payload.user_locale
    tz = ZoneInfo(payload.user_timezone)
    local = payload.scheduled_at.astimezone(tz)
    time_str = local.strftime("%H:%M")
    text = t(
        "reminder.line_push",
        locale=locale,
        name=payload.medication_name,
        dosage=payload.dosage,
        schedule=payload.schedule,
        time_local=time_str,
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
    tz = ZoneInfo(payload.user_timezone)
    local = payload.scheduled_at.astimezone(tz)
    time_str = local.strftime("%H:%M")
    text = t(
        "reminder.line_push_nudge",
        locale=locale,
        name=payload.medication_name,
        dosage=payload.dosage,
        schedule=payload.schedule,
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
        defer_until = datetime.now(UTC) + timedelta(minutes=delay_min)
        await enqueue_reminder_nudge_job(svc.settings.redis_url, dose_event_id, nxt, defer_until)
    return True


async def _enqueue_first_nudge(svc: AppServices, dose_event_id: str) -> None:
    intervals = svc.settings.reminder_nudge_intervals_minutes
    redis_url = svc.settings.redis_url
    if not intervals or not redis_url:
        return
    delay_min = intervals[0]
    defer_until = datetime.now(UTC) + timedelta(minutes=delay_min)
    await enqueue_reminder_nudge_job(redis_url, dose_event_id, 0, defer_until)
