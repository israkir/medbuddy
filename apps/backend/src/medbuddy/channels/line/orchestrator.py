"""LINE channel: event → classify → optional drug grounding → LLM → reply."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import parse_qs

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.models.domain import MessageKind

log = logging.getLogger(__name__)


def _message_kind(message: dict[str, Any]) -> MessageKind:
    mtype = message.get("type")
    if mtype == "text":
        return MessageKind.TEXT
    if mtype == "audio":
        return MessageKind.AUDIO
    return MessageKind.UNKNOWN


async def _handle_user_message(
    svc: AppServices,
    *,
    line_user_id: str,
    reply_token: str,
    user_text: str,
    prefer_audio_reply: bool,
) -> None:
    reply_text = await run_assistant_text_turn(
        svc,
        user_key=line_user_id,
        user_text=user_text,
    )

    if prefer_audio_reply:
        log.info(
            "LINE flow: user_id=%s assistant reply len=%d chars — TTS + text batch",
            line_user_id,
            len(reply_text),
        )
        audio_url, duration_ms = await svc.tts.synthesize_to_m4a_url(
            reply_text,
            svc.settings.public_base_url,
        )

        async def _cleanup() -> None:
            await asyncio.sleep(svc.settings.audio_temp_ttl_seconds)
            await svc.storage.delete_object(audio_url)

        asyncio.create_task(_cleanup())

        await svc.line.reply_message_batch(
            reply_token,
            [
                {
                    "type": "audio",
                    "originalContentUrl": audio_url,
                    "duration": duration_ms,
                },
                {"type": "text", "text": reply_text},
            ],
        )
        return

    log.info(
        "LINE flow: user_id=%s assistant reply len=%d chars — text reply",
        line_user_id,
        len(reply_text),
    )
    await svc.line.reply_text(reply_token, reply_text)


async def handle_line_event(event: dict[str, Any], svc: AppServices) -> None:
    etype = event.get("type")
    reply_token = event.get("replyToken") or ""
    source = event.get("source") or {}
    line_user_id = source.get("userId") or ""

    if not line_user_id:
        log.warning("LINE event without userId: %s", event)
        return

    log.info(
        "LINE event: user_id=%s type=%s webhook_event_id=%r",
        line_user_id,
        etype,
        event.get("webhookEventId"),
    )

    if etype == "follow":
        await svc.users.get_or_create_user(line_user_id)
        loc = svc.settings.locale
        await svc.line.reply_text(
            reply_token,
            t("line.follow_welcome", locale=loc),
        )
        log.info("LINE flow: user_id=%s new follow — welcome", line_user_id)
        return

    if etype == "postback":
        data = event.get("postback", {}).get("data") or ""
        qs = parse_qs(data)
        action = (qs.get("action") or [""])[0]
        log.info("LINE flow: user_id=%s unhandled postback action=%r", line_user_id, action)
        return

    if etype != "message":
        log.debug("LINE event: user_id=%s ignored non-message type=%s", line_user_id, etype)
        return

    message = event.get("message") or {}
    kind = _message_kind(message)

    if kind == MessageKind.TEXT:
        text = message.get("text") or ""
        log.info(
            "LINE flow: user_id=%s inbound text chars=%d",
            line_user_id,
            len(text),
        )
        await _handle_user_message(
            svc,
            line_user_id=line_user_id,
            reply_token=reply_token,
            user_text=text,
            prefer_audio_reply=False,
        )
        return

    if kind == MessageKind.AUDIO:
        mid = message.get("id")
        if not mid:
            log.warning("LINE flow: user_id=%s audio message without id", line_user_id)
            return
        log.info("LINE flow: user_id=%s inbound audio message_id=%s", line_user_id, mid)
        raw = await svc.line.get_message_content(str(mid))
        user_text = await svc.stt.transcribe_m4a(raw)
        log.info(
            "LINE flow: user_id=%s STT done transcribed_chars=%d",
            line_user_id,
            len(user_text),
        )
        await _handle_user_message(
            svc,
            line_user_id=line_user_id,
            reply_token=reply_token,
            user_text=user_text,
            prefer_audio_reply=True,
        )
        return

    log.info(
        "LINE flow: user_id=%s unsupported message kind=%s",
        line_user_id,
        kind,
    )
