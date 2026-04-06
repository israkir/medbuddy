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
        raise HTTPException(status_code=401, detail="invalid signature") from e
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="invalid json") from e

    if _skip_line_signature_verification(settings):
        log.debug("LINE signature verification skipped (mock without channel secret)")

    for event in events:
        await handle_line_event(event.to_dict(), svc)

    return {"status": "ok"}
