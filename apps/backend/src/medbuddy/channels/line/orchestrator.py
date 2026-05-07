"""LINE channel: event → classify → optional drug grounding → LLM → reply."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.services import AppServices
from medbuddy.core.i18n import t
from medbuddy.models.domain import MessageKind
from medbuddy.core.locale import effective_user_locale
from medbuddy.privacy.redact import redact_pii_text

log = logging.getLogger(__name__)


def _preview_redacted(text: str, *, limit: int = 80) -> str:
    redacted = redact_pii_text(text)
    if len(redacted) <= limit:
        return redacted
    return redacted[:limit] + "..."


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
    locale: str,
    inbound_was_audio: bool,
) -> None:
    turn = await run_assistant_text_turn(
        svc,
        user_key=line_user_id,
        user_text=user_text,
    )
    reply_text = turn.reply

    mode = svc.settings.line_voice_replies
    want_voice = mode == "always" or (mode == "audio_inbound" and inbound_was_audio)
    if want_voice and svc.tts is None:
        log.warning(
            "LINE flow: user_id=%s voice reply skipped (TTS not configured)",
            line_user_id,
        )
        want_voice = False
    if want_voice and not reply_text.strip():
        want_voice = False

    if not want_voice:
        log.info(
            "LINE flow: user_id=%s assistant reply len=%d chars — text only",
            line_user_id,
            len(reply_text),
        )
        await svc.line.reply_text(reply_token, reply_text)
        return

    pub = (svc.settings.public_base_url or "").strip()
    if not pub.lower().startswith("https:"):
        log.warning(
            "LINE flow: user_id=%s voice reply may fail — public_base_url is not HTTPS",
            line_user_id,
        )

    tts = svc.tts
    assert tts is not None

    try:
        m4a, duration_ms = await tts.synthesize_m4a(reply_text, language_code=locale)
        audio_id = svc.line_audio_blobs.put(m4a)
        audio_url = svc.line_audio_blobs.public_url(audio_id)
    except Exception:
        log.error(
            "LINE flow: user_id=%s TTS/blob failed; falling back to text",
            line_user_id,
            exc_info=True,
        )
        await svc.line.reply_text(reply_token, reply_text)
        return

    await svc.line.reply_message_batch(
        reply_token,
        [
            {"type": "text", "text": reply_text},
            {
                "type": "audio",
                "originalContentUrl": audio_url,
                "duration": duration_ms,
            },
        ],
    )
    log.info(
        "LINE flow: user_id=%s assistant reply len=%d chars — text+audio duration_ms=%s",
        line_user_id,
        len(reply_text),
        duration_ms,
    )


async def handle_line_event(event: dict[str, Any], svc: AppServices) -> None:
    etype = event.get("type")
    reply_token = event.get("replyToken") or ""
    source = event.get("source") or {}
    line_user_id = source.get("userId") or ""

    if not line_user_id:
        raw_msg = event.get("message")
        msg_type = raw_msg.get("type") if isinstance(raw_msg, dict) else None
        log.warning(
            "LINE event without userId: type=%s webhook_event_id=%s message.type=%s",
            etype,
            event.get("webhookEventId"),
            msg_type,
        )
        return

    log.info(
        "LINE event: user_id=%s type=%s webhook_event_id=%r",
        line_user_id,
        etype,
        event.get("webhookEventId"),
    )

    if etype == "follow":
        row = await svc.users.get_or_create_user(line_user_id)
        loc = effective_user_locale(row.get("locale"))
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
        log.info(
            "LINE flow: user_id=%s unhandled postback action_len=%d",
            line_user_id,
            len(action),
        )
        return

    if etype != "message":
        log.debug("LINE event: user_id=%s ignored non-message type=%s", line_user_id, etype)
        return

    message = event.get("message") or {}
    kind = _message_kind(message)

    if kind == MessageKind.TEXT:
        text = message.get("text") or ""
        log.info(
            "LINE flow: user_id=%s inbound text chars=%d preview=%r",
            line_user_id,
            len(text),
            _preview_redacted(text),
        )
        row = await svc.users.get_or_create_user(line_user_id)
        loc = effective_user_locale(row.get("locale"))
        await _handle_user_message(
            svc,
            line_user_id=line_user_id,
            reply_token=reply_token,
            user_text=text,
            locale=loc,
            inbound_was_audio=False,
        )
        return

    if kind == MessageKind.AUDIO:
        mid = message.get("id")
        if not mid:
            log.warning("LINE flow: user_id=%s audio message without id", line_user_id)
            return
        log.info("LINE flow: user_id=%s inbound audio message_id=%s", line_user_id, mid)
        row = await svc.users.get_or_create_user(line_user_id)
        loc = effective_user_locale(row.get("locale"))
        raw = await svc.line.get_message_content(str(mid))
        try:
            user_text = await svc.stt.transcribe_m4a(raw, language_code=loc)
        except Exception:
            log.error(
                "LINE flow: user_id=%s STT failed; sending fallback reply",
                line_user_id,
                exc_info=True,
            )
            await svc.line.reply_text(reply_token, t("agent.generic_error", locale=loc))
            return
        log.info(
            "LINE flow: user_id=%s STT done transcribed_chars=%d preview=%r",
            line_user_id,
            len(user_text),
            _preview_redacted(user_text),
        )
        await _handle_user_message(
            svc,
            line_user_id=line_user_id,
            reply_token=reply_token,
            user_text=user_text,
            locale=loc,
            inbound_was_audio=True,
        )
        return

    log.info(
        "LINE flow: user_id=%s unsupported message kind=%s",
        line_user_id,
        kind,
    )
