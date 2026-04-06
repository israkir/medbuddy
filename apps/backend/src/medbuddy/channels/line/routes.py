"""LINE Messaging API webhook."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from linebot.v3 import WebhookParser
from linebot.v3.exceptions import InvalidSignatureError

from medbuddy.channels.line.orchestrator import handle_line_event
from medbuddy.config import Settings, get_settings
from medbuddy.deps import get_services
from medbuddy.engine.types import AppServices

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/line", tags=["line"])


def _skip_line_signature_verification(settings: Settings) -> bool:
    """Allow local mock runs without a channel secret (matches previous behavior)."""
    return bool(settings.mock_external_services and not settings.line_channel_secret)


@router.post("/webhook")
async def line_webhook(
    request: Request,
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

    for event in events:
        await handle_line_event(event.to_dict(), svc)

    log.info("LINE webhook: batch completed OK")
    return {"status": "ok"}
