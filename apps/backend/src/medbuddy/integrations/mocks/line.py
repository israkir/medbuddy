from __future__ import annotations

import asyncio
from typing import Any

from medbuddy.protocols import LineMessagingPort


class MockLineClient(LineMessagingPort):
    """Records outbound calls for assertions; simulates content fetch."""

    def __init__(self) -> None:
        self.replies: list[dict[str, Any]] = []
        self.pushes: list[dict[str, Any]] = []
        self._content_by_message_id: dict[str, bytes] = {}

    def seed_voice_message(self, message_id: str, m4a_bytes: bytes) -> None:
        self._content_by_message_id[message_id] = m4a_bytes

    async def reply_message_batch(self, reply_token: str, messages: list[dict[str, Any]]) -> None:
        await asyncio.sleep(0)
        self.replies.append(
            {"type": "batch", "reply_token": reply_token, "messages": messages},
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

    async def push_message_batch(self, to_user_id: str, messages: list[dict[str, Any]]) -> None:
        await asyncio.sleep(0)
        self.pushes.append({"to_user_id": to_user_id, "messages": messages})

    async def get_message_content(self, message_id: str) -> bytes:
        await asyncio.sleep(0)
        return self._content_by_message_id.get(message_id, b"mock-m4a-placeholder")
