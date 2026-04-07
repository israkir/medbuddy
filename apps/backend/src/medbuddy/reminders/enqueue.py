"""Enqueue arq jobs for dose reminders (requires redis_url and arq)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

log = logging.getLogger(__name__)


async def enqueue_reminder_jobs(redis_url: str, jobs: list[tuple[str, datetime]]) -> None:
    """Schedule ``send_reminder_for_dose`` for each ``(dose_event_id, scheduled_at_utc)``."""
    if not redis_url or not jobs:
        return
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
    except ImportError:
        log.warning(
            "arq is not installed; cannot enqueue reminders. "
            "Install with: pip install 'medbuddy-api[reminders]'"
        )
        return

    redis = await create_pool(RedisSettings.from_dsn(redis_url))
    try:
        for dose_id, defer_until in jobs:
            dt = defer_until if defer_until.tzinfo else defer_until.replace(tzinfo=UTC)
            if dt <= datetime.now(UTC):
                await redis.enqueue_job("send_reminder_for_dose", dose_id)
            else:
                await redis.enqueue_job("send_reminder_for_dose", dose_id, _defer_until=dt)
    finally:
        await redis.close()


async def enqueue_reminder_jobs_now(redis_url: str, dose_event_ids: list[str]) -> None:
    """Enqueue immediate jobs (reconciliation path)."""
    if not redis_url or not dose_event_ids:
        return
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
    except ImportError:
        log.warning("arq is not installed; skipping reminder reconciliation enqueue")
        return

    redis = await create_pool(RedisSettings.from_dsn(redis_url))
    try:
        for dose_id in dose_event_ids:
            await redis.enqueue_job("send_reminder_for_dose", dose_id)
    finally:
        await redis.close()


async def enqueue_reminder_nudge_job(
    redis_url: str,
    dose_event_id: str,
    expected_nudge_count: int,
    defer_until: datetime,
) -> None:
    """Schedule ``send_reminder_nudge`` for a follow-up push after the primary reminder."""
    if not redis_url:
        return
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
    except ImportError:
        log.warning(
            "arq is not installed; cannot enqueue reminder nudges. "
            "Install with: pip install 'medbuddy-api[reminders]'"
        )
        return

    redis = await create_pool(RedisSettings.from_dsn(redis_url))
    try:
        dt = defer_until if defer_until.tzinfo else defer_until.replace(tzinfo=UTC)
        if dt <= datetime.now(UTC):
            await redis.enqueue_job(
                "send_reminder_nudge",
                dose_event_id,
                expected_nudge_count,
            )
        else:
            await redis.enqueue_job(
                "send_reminder_nudge",
                dose_event_id,
                expected_nudge_count,
                _defer_until=dt,
            )
    finally:
        await redis.close()
