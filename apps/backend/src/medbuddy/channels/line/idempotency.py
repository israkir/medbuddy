"""LINE webhook event deduplication via Redis SETNX.

Each incoming webhook carries a ``webhookEventId``.  We record the first
occurrence with a 5-minute TTL.  If the same ID arrives again (LINE retry or
duplicate delivery), we skip it and return an early 200 so LINE stops retrying.

Falls back gracefully (always-process) when no Redis URL is configured, so
mock-mode and tests are unaffected.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_TTL_SECONDS = 300  # 5 minutes — matches LINE's retry window


async def mark_and_check_line_event_seen(redis_url: str, webhook_event_id: str) -> bool:
    """Attempt to claim *webhook_event_id* in Redis.

    Returns ``True`` if the event was **already** seen (caller should skip it).
    Returns ``False`` if this is the first occurrence (caller should process it).
    Always returns ``False`` when Redis is unavailable or *redis_url* is empty.
    """
    if not redis_url or not webhook_event_id:
        return False
    try:
        from redis.asyncio import from_url as _redis_from_url  # type: ignore[import-untyped]

        r = _redis_from_url(redis_url, decode_responses=True)
        try:
            key = f"webhook:seen:{webhook_event_id}"
            # SET NX EX: set only if absent; returns True on success, None if already set
            result = await r.set(key, "1", nx=True, ex=_TTL_SECONDS)
            return result is None  # None → key existed → already seen
        finally:
            await r.aclose()
    except Exception:
        log.debug(
            "webhook idempotency: Redis check failed for event_id=%r; processing anyway",
            webhook_event_id,
        )
        return False
