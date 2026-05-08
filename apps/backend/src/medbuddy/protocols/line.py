"""LINE Messaging and audio blob store interfaces."""

from __future__ import annotations

from typing import Any, Protocol


class LineMessagingPort(Protocol):
    """LINE allows multiple messages in a single reply — use batch for text + audio."""

    async def reply_message_batch(
        self, reply_token: str, messages: list[dict[str, Any]]
    ) -> None: ...

    async def reply_text(self, reply_token: str, text: str) -> None: ...

    async def reply_audio_url(self, reply_token: str, audio_url: str, duration_ms: int) -> None: ...

    async def push_message_batch(self, to_user_id: str, messages: list[dict[str, Any]]) -> None: ...

    async def get_message_content(self, message_id: str) -> bytes: ...

    async def get_user_profile(self, user_id: str) -> dict[str, Any] | None: ...


class LineAudioBlobStorePort(Protocol):
    """Short-lived publicly URL-addressable audio payloads for LINE ``originalContentUrl``."""

    def put(self, data: bytes) -> str: ...

    def get(self, audio_id: str) -> bytes | None: ...

    def public_url(self, audio_id: str) -> str: ...
