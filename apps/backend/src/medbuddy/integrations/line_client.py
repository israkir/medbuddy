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
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)

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
    def __init__(self, *, channel_access_token: str) -> None:
        configuration = Configuration(access_token=channel_access_token)
        api_client = AsyncApiClient(configuration)
        self._messaging = AsyncMessagingApi(api_client)
        self._blob = AsyncMessagingApiBlob(api_client)

    async def reply_message_batch(self, reply_token: str, messages: list[dict[str, Any]]) -> None:
        req = ReplyMessageRequest(
            reply_token=reply_token,
            messages=_coerce_reply_messages(messages),
        )
        await self._messaging.reply_message(req)

    async def push_message_batch(self, to_user_id: str, messages: list[dict[str, Any]]) -> None:
        req = PushMessageRequest(
            to=to_user_id,
            messages=_coerce_reply_messages(messages),
        )
        await self._messaging.push_message(req)

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
