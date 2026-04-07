"""Shared operational routes (health, cron hooks)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import PlainTextResponse

from medbuddy.config import get_settings
from medbuddy.engine.types import AppServices
from medbuddy.reminders.enqueue import enqueue_reminder_jobs_now

router = APIRouter(tags=["infrastructure"])


@router.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@router.post("/internal/reminders/reconcile")
async def reminders_reconcile(
    request: Request,
    x_cron_secret: str | None = Header(None, alias="X-Cron-Secret"),
) -> dict[str, int | str]:
    """Re-enqueue due doses that never received a push (secret header; optional safety net)."""
    settings = get_settings()
    if not settings.cron_secret or (x_cron_secret or "") != settings.cron_secret:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not settings.redis_url.strip():
        raise HTTPException(status_code=503, detail="redis not configured")

    svc: AppServices = request.app.state.services
    ids = await svc.users.list_dose_event_ids_for_reconcile(before_utc=datetime.now(UTC))
    await enqueue_reminder_jobs_now(settings.redis_url, ids)
    return {"enqueued": len(ids), "status": "ok"}
