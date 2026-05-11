"""LINE Messaging API webhook."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError

from medbuddy.channels.line.idempotency import mark_and_check_line_event_seen
from medbuddy.channels.line.orchestrator import handle_line_event
from medbuddy.config import Settings, get_settings
from medbuddy.deps import get_services
from medbuddy.services import AppServices

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/line", tags=["line"])


async def _run_event(payload: dict[str, Any], svc: AppServices) -> None:
    try:
        await handle_line_event(payload, svc)
    except Exception:
        log.error("LINE webhook: background event handler failed", exc_info=True)


@router.get("/media/audio/{audio_id}")
async def line_tts_audio_asset(
    audio_id: str,
    svc: AppServices = Depends(get_services),
) -> Response:
    """Public HTTPS URL for LINE ``audio`` messages (ephemeral; see ``LineAudioBlobStore``)."""
    data = svc.line_audio_blobs.get(audio_id)
    if data is None:
        raise HTTPException(status_code=404, detail="not found")
    return Response(
        content=data,
        media_type="audio/mp4",
        headers={"Cache-Control": "public, max-age=60"},
    )


def _skip_line_signature_verification(settings: Settings) -> bool:
    """Allow local mock runs without a channel secret (matches previous behavior)."""
    return bool(settings.is_mock and not settings.line_channel_secret)


@router.post("/webhook")
async def line_webhook(
    request: Request,
    background: BackgroundTasks,
    svc: AppServices = Depends(get_services),
) -> dict[str, str]:
    settings = get_settings()
    raw = await request.body()
    body_text = raw.decode("utf-8")
    sig = request.headers.get("X-Line-Signature") or ""

    parser = WebhookParser(
        settings.line_channel_secret or "",
        skip_signature_verification=lambda: _skip_line_signature_verification(settings),
    )
    try:
        events = parser.parse(body_text, sig)
    except InvalidSignatureError as e:
        log.warning("LINE webhook: invalid signature (check LINE_CHANNEL_SECRET vs console)")
        raise HTTPException(status_code=401, detail="invalid signature") from e
    except json.JSONDecodeError as e:
        log.warning("LINE webhook: JSON parse failed: %s", e)
        raise HTTPException(status_code=400, detail="invalid json") from e

    skip_sig = _skip_line_signature_verification(settings)
    if skip_sig:
        log.warning(
            "LINE webhook: signature verification skipped (mock mode without channel secret)"
        )

    log.info("LINE webhook: accepted batch, event_count=%d", len(events))
    for i, event in enumerate(events):
        payload = event.to_dict()
        et = payload.get("type")
        detail = ""
        if et == "message":
            m = payload.get("message") or {}
            detail = f" message_type={m.get('type')!r}"
        log.info(
            "LINE webhook: event[%d] type=%s webhook_event_id=%r%s",
            i,
            et,
            payload.get("webhookEventId"),
            detail,
        )

    redis_url = svc.settings.redis_url
    for event in events:
        payload = event.to_dict()
        event_id = payload.get("webhookEventId") or ""
        if redis_url and event_id:
            already_seen = await mark_and_check_line_event_seen(redis_url, event_id)
            if already_seen:
                log.info("LINE webhook: duplicate event skipped webhook_event_id=%r", event_id)
                continue
        background.add_task(_run_event, payload, svc)

    log.info("LINE webhook: batch accepted OK, processing in background")
    return {"status": "ok"}
