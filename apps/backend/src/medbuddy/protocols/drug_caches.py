"""Optional Supabase-backed caches (reference + per-user LLM personalization)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DrugCachesPort(Protocol):
    async def get_personalized_reply(
        self,
        *,
        user_uuid: str,
        query_fingerprint: str,
    ) -> str | None: ...

    async def save_personalized_reply(
        self,
        *,
        user_uuid: str,
        query_fingerprint: str,
        intent: str,
        personalized_text: str,
        locale: str,
        llm_meta: dict[str, Any],
    ) -> None: ...
