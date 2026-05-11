"""LINE Messaging API client — ``line-bot-sdk`` v3 (production integrations)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    AsyncMessagingApiBlob,
    AudioMessage,
    Configuration,
    Message,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)

from medbuddy.protocols import LineMessagingPort

log = logging.getLogger(__name__)


def _coerce_reply_messages(messages: list[dict[str, Any]]) -> list[Message]:
    out: list[Message] = []
    for m in messages:
        mtype = m.get("type")
        if mtype == "text":
            out.append(TextMessage(text=m.get("text") or ""))
        elif mtype == "audio":
            out.append(
                AudioMessage(
                    original_content_url=m["originalContentUrl"],
                    duration=int(m["duration"]),
                )
            )
        else:
            msg = f"Unsupported LINE message payload type for reply: {mtype!r}"
            raise ValueError(msg)
    return out


class LineHttpClient(LineMessagingPort):
    def __init__(self, *, channel_access_token: str) -> None:
        self._channel_access_token = channel_access_token
        configuration = Configuration(access_token=channel_access_token)
        api_client = AsyncApiClient(configuration)
        self._messaging = AsyncMessagingApi(api_client)
        self._blob = AsyncMessagingApiBlob(api_client)

    async def reply_message_batch(self, reply_token: str, messages: list[dict[str, Any]]) -> None:
        log.info(
            "LINE outbound: reply attempt message_count=%d reply_token_prefix=%s",
            len(messages),
            (reply_token or "")[:8],
        )
        req = ReplyMessageRequest(
            reply_token=reply_token,
            messages=_coerce_reply_messages(messages),
        )
        try:
            await self._messaging.reply_message(req)
        except Exception:
            log.error(
                "LINE outbound: reply failed message_count=%d reply_token_prefix=%s",
                len(messages),
                (reply_token or "")[:8],
                exc_info=True,
            )
            raise
        log.info(
            "LINE outbound: reply accepted message_count=%d reply_token_prefix=%s",
            len(messages),
            (reply_token or "")[:8],
        )

    async def push_message_batch(self, to_user_id: str, messages: list[dict[str, Any]]) -> None:
        log.info(
            "LINE outbound: push attempt message_count=%d to_user_prefix=%s",
            len(messages),
            (to_user_id or "")[:8],
        )
        req = PushMessageRequest(
            to=to_user_id,
            messages=_coerce_reply_messages(messages),
        )
        try:
            await self._messaging.push_message(req)
        except Exception:
            log.error(
                "LINE outbound: push failed message_count=%d to_user_prefix=%s",
                len(messages),
                (to_user_id or "")[:8],
                exc_info=True,
            )
            raise
        log.info(
            "LINE outbound: push accepted message_count=%d to_user_prefix=%s",
            len(messages),
            (to_user_id or "")[:8],
        )

    async def reply_text(self, reply_token: str, text: str) -> None:
        await self.reply_message_batch(reply_token, [{"type": "text", "text": text}])

    async def reply_audio_url(self, reply_token: str, audio_url: str, duration_ms: int) -> None:
        await self.reply_message_batch(
            reply_token,
            [
                {
                    "type": "audio",
                    "originalContentUrl": audio_url,
                    "duration": duration_ms,
                }
            ],
        )

    async def get_message_content(self, message_id: str) -> bytes:
        data = await self._blob.get_message_content(message_id)
        return bytes(data)

    async def get_user_profile(self, user_id: str) -> dict[str, Any] | None:
        url = f"https://api.line.me/v2/bot/profile/{user_id}"
        headers = {"Authorization": f"Bearer {self._channel_access_token}"}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(url, headers=headers, timeout=10.0)
        except Exception:
            log.warning(
                "LINE profile: request failed user_id_prefix=%s",
                (user_id or "")[:8],
                exc_info=True,
            )
            return None
        if r.status_code != 200:
            log.warning(
                "LINE profile: status=%s user_id_prefix=%s",
                r.status_code,
                (user_id or "")[:8],
            )
            return None
        try:
            data = r.json()
        except Exception:
            log.warning("LINE profile: invalid JSON user_id_prefix=%s", (user_id or "")[:8])
            return None
        return data if isinstance(data, dict) else None

    async def send_chat_loading_indicator(self, user_id: str, *, seconds: int = 20) -> None:
        url = "https://api.line.me/v2/bot/chat/loading/start"
        headers = {
            "Authorization": f"Bearer {self._channel_access_token}",
            "Content-Type": "application/json",
        }
        payload = {"chatId": user_id, "loadingSeconds": max(5, min(60, seconds))}
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(url, json=payload, headers=headers, timeout=5.0)
            if r.status_code not in (200, 202):
                log.warning(
                    "LINE loading indicator: unexpected status=%s user_id_prefix=%s",
                    r.status_code,
                    (user_id or "")[:8],
                )
        except Exception:
            log.warning(
                "LINE loading indicator: request failed user_id_prefix=%s",
                (user_id or "")[:8],
                exc_info=True,
            )
