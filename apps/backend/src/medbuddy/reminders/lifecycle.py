"""Hook medication changes to dose_event sync + Redis job enqueue."""

from __future__ import annotations

import logging

from medbuddy.services import AppServices
from medbuddy.reminders.enqueue import enqueue_reminder_jobs

log = logging.getLogger(__name__)


async def sync_and_enqueue_reminders(svc: AppServices, user_key: str) -> None:
    jobs = await svc.users.sync_upcoming_dose_events(user_key)
    if not svc.settings.redis_url:
        log.debug(
            "reminder: synced %d dose row(s) for user_key=%s; REDIS_URL unset, skip enqueue",
            len(jobs),
            user_key,
        )
        return
    await enqueue_reminder_jobs(svc.settings.redis_url, jobs)
    log.info(
        "reminder: synced %d dose row(s) and enqueued jobs for user_key=%s",
        len(jobs),
        user_key,
    )
