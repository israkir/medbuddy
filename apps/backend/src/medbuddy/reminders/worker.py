"""arq worker: set ``REDIS_URL`` and run ``arq medbuddy.reminders.worker.WorkerSettings``."""

from __future__ import annotations

import os
from typing import Any

import httpx
from arq.connections import RedisSettings

from medbuddy.config import get_settings
from medbuddy.container import build_app_services
from medbuddy.core.request_id import set_request_id
from medbuddy.reminders.deliver import deliver_dose_reminder, deliver_dose_reminder_nudge


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    ctx["settings"] = settings
    outbound_http: httpx.AsyncClient | None = None
    if not settings.is_mock:
        # Same defaults as ``main.py`` lifespan — HttpDrugData shares this client.
        outbound_http = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
    ctx["outbound_http"] = outbound_http
    ctx["services"] = build_app_services(settings, outbound_http=outbound_http)


async def shutdown(ctx: dict[str, Any]) -> None:
    client = ctx.get("outbound_http")
    if isinstance(client, httpx.AsyncClient):
        await client.aclose()


async def send_reminder_for_dose(
    ctx: dict[str, Any],
    dose_event_id: str,
    scheduled_at_iso: str | None = None,
    origin_request_id: str | None = None,
) -> None:
    if origin_request_id:
        set_request_id(origin_request_id)
    svc = ctx["services"]
    await deliver_dose_reminder(svc, dose_event_id, scheduled_at_iso=scheduled_at_iso)


async def send_reminder_nudge(
    ctx: dict[str, Any], dose_event_id: str, expected_nudge_count: int
) -> None:
    svc = ctx["services"]
    await deliver_dose_reminder_nudge(svc, dose_event_id, expected_nudge_count)


def _redis_settings() -> RedisSettings:
    # Prefer process env so the worker does not depend on Settings redis_url at import time.
    url = (os.environ.get("REDIS_URL") or get_settings().redis_url or "").strip()
    if not url:
        msg = "REDIS_URL must be set for the reminder worker (see backend README)."
        raise RuntimeError(msg)
    return RedisSettings.from_dsn(url)


class WorkerSettings:
    redis_settings = _redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    functions = [send_reminder_for_dose, send_reminder_nudge]
