"""LINE channel: event → classify → optional drug grounding → LLM → reply (text/audio)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import parse_qs

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.engine.types import AppServices
from medbuddy.models.domain import MessageKind
from medbuddy.i18n import t

log = logging.getLogger(__name__)


def _message_kind(message: dict[str, Any]) -> MessageKind:
    mtype = message.get("type")
    if mtype == "text":
        return MessageKind.TEXT
    if mtype == "audio":
        return MessageKind.AUDIO
    return MessageKind.UNKNOWN


async def _ensure_consent(svc: AppServices, line_user_id: str, reply_token: str) -> bool:
    user = await svc.users.get_or_create_user(line_user_id)
    if user.get("consent_accepted"):
        return True
    await svc.line.reply_quick_reply_consent(reply_token)
    return False


async def _handle_user_message(
    svc: AppServices,
    *,
    line_user_id: str,
    reply_token: str,
    user_text: str,
    prefer_audio_reply: bool,
) -> None:
    if not await _ensure_consent(svc, line_user_id, reply_token):
        return

    reply_text = await run_assistant_text_turn(
        svc,
        user_key=line_user_id,
        user_text=user_text,
    )

    if prefer_audio_reply:
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

    await svc.line.reply_text(reply_token, reply_text)


async def handle_line_event(event: dict[str, Any], svc: AppServices) -> None:
    etype = event.get("type")
    reply_token = event.get("replyToken") or ""
    source = event.get("source") or {}
    line_user_id = source.get("userId") or ""

    if not line_user_id:
        log.warning("LINE event without userId: %s", event)
        return

    if etype == "follow":
        await svc.users.get_or_create_user(line_user_id)
        await svc.line.reply_quick_reply_consent(reply_token)
        return

    if etype == "postback":
        data = event.get("postback", {}).get("data") or ""
        qs = parse_qs(data)
        action = (qs.get("action") or [""])[0]
        value = (qs.get("value") or [""])[0]
        if action == "consent":
            accepted = value == "yes"
            await svc.users.set_consent(line_user_id, accepted)
            loc = svc.settings.locale
            if accepted:
                await svc.line.reply_text(
                    reply_token,
                    t("orchestrator.consent_accepted", locale=loc),
                )
            else:
                await svc.line.reply_text(
                    reply_token,
                    t("orchestrator.consent_declined", locale=loc),
                )
        return

    if etype != "message":
        return

    message = event.get("message") or {}
    kind = _message_kind(message)

    if kind == MessageKind.TEXT:
        text = message.get("text") or ""
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
            return
        raw = await svc.line.get_message_content(str(mid))
        user_text = await svc.stt.transcribe_m4a(raw)
        await _handle_user_message(
            svc,
            line_user_id=line_user_id,
            reply_token=reply_token,
            user_text=user_text,
            prefer_audio_reply=True,
        )
        return
