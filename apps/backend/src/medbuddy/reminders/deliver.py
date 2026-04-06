"""Send one LINE push for a dose_event and mark reminder_sent_at."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t

log = logging.getLogger(__name__)


async def deliver_dose_reminder(svc: AppServices, dose_event_id: str) -> bool:
    """Load the row, push LINE text, then mark sent. Returns True if a push was attempted."""
    payload = await svc.users.get_dose_event_for_reminder(dose_event_id)
    if payload is None:
        log.debug("reminder skip: no pending row for dose_event_id=%s", dose_event_id)
        return False

    locale = svc.settings.locale
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
    return True
