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

    async def get_reference_cache_id(self, *, source: str, query_key: str) -> str | None:
        """Return id of a non-expired ``drug_reference_cache`` row, if any."""
        ...

    async def save_personalized_reply(
        self,
        *,
        user_uuid: str,
        query_fingerprint: str,
        intent: str,
        personalized_text: str,
        locale: str,
        llm_meta: dict[str, Any],
        medication_id: str | None = None,
        reference_cache_id: str | None = None,
    ) -> None: ...
