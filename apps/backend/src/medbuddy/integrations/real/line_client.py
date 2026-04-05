"""LINE Messaging API client — use when MOCK_EXTERNAL_SERVICES=false."""

from __future__ import annotations

import json
from typing import Any

import httpx

from medbuddy.i18n import t
from medbuddy.protocols.ports import LineMessagingPort


class LineHttpClient(LineMessagingPort):
    def __init__(self, *, channel_access_token: str, locale: str = "zh-TW") -> None:
        self._token = channel_access_token
        self._locale = locale
        self._headers = {
            "Authorization": f"Bearer {channel_access_token}",
            "Content-Type": "application/json",
        }

    async def reply_message_batch(self, reply_token: str, messages: list[dict[str, Any]]) -> None:
        body = {"replyToken": reply_token, "messages": messages}
        await self._post_json("https://api.line.me/v2/bot/message/reply", body)

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
        body = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": t("line.consent_body", locale=loc),
                    "quickReply": {
                        "items": [
                            {
                                "type": "action",
                                "action": {
                                    "type": "postback",
                                    "label": agree,
                                    "data": "action=consent&value=yes",
                                    "displayText": agree,
                                },
                            },
                            {
                                "type": "action",
                                "action": {
                                    "type": "postback",
                                    "label": disagree,
                                    "data": "action=consent&value=no",
                                    "displayText": disagree,
                                },
                            },
                        ]
                    },
                }
            ],
        }
        await self._post_json("https://api.line.me/v2/bot/message/reply", body)

    async def get_message_content(self, message_id: str) -> bytes:
        url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(
                url,
                headers={"Authorization": f"Bearer {self._token}"},
            )
            r.raise_for_status()
            return r.content

    async def _post_json(self, url: str, body: dict) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, content=json.dumps(body), headers=self._headers)
            r.raise_for_status()
