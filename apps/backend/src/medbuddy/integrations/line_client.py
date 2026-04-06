"""LINE Messaging API client — ``line-bot-sdk`` v3 when MOCK_EXTERNAL_SERVICES=false."""

from __future__ import annotations

from typing import Any

from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    AsyncMessagingApiBlob,
    AudioMessage,
    Configuration,
    Message,
    PostbackAction,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)

from medbuddy.i18n import t
from medbuddy.protocols.ports import LineMessagingPort


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
    def __init__(self, *, channel_access_token: str, locale: str = "zh-TW") -> None:
        configuration = Configuration(access_token=channel_access_token)
        api_client = AsyncApiClient(configuration)
        self._messaging = AsyncMessagingApi(api_client)
        self._blob = AsyncMessagingApiBlob(api_client)
        self._locale = locale

    async def reply_message_batch(self, reply_token: str, messages: list[dict[str, Any]]) -> None:
        req = ReplyMessageRequest(
            reply_token=reply_token,
            messages=_coerce_reply_messages(messages),
        )
        await self._messaging.reply_message(req)

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

    async def reply_quick_reply_consent(self, reply_token: str) -> None:
        loc = self._locale
        agree = t("line.consent_agree", locale=loc)
        disagree = t("line.consent_disagree", locale=loc)
        body = t("line.consent_body", locale=loc)
        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    action=PostbackAction(
                        label=agree,
                        data="action=consent&value=yes",
                        display_text=agree,
                    )
                ),
                QuickReplyItem(
                    action=PostbackAction(
                        label=disagree,
                        data="action=consent&value=no",
                        display_text=disagree,
                    )
                ),
            ]
        )
        req = ReplyMessageRequest(
            reply_token=reply_token,
            messages=[TextMessage(text=body, quick_reply=quick_reply)],
        )
        await self._messaging.reply_message(req)

    async def get_message_content(self, message_id: str) -> bytes:
        data = await self._blob.get_message_content(message_id)
        return bytes(data)
