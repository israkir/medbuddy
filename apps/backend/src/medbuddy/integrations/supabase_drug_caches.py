"""Supabase tables ``drug_reference_cache`` (via ``CachingDrugData``) and ``drug_personalization_cache``."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from medbuddy.config import Settings
from medbuddy.drug_cache_keys import normalize_query_key
from medbuddy.models.domain import DrugGrounding
from medbuddy.protocols.drug_caches import DrugCachesPort

log = logging.getLogger(__name__)


def _run_q(fn: Any) -> Any:
    return asyncio.to_thread(fn)


def _parse_ts(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        s = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(s)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


class SupabaseDrugCaches(DrugCachesPort):
    """Read/write drug reference rows (used by ``CachingDrugData``) and personalization rows."""

    def __init__(self, client: Any, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    async def get_valid_reference(self, *, source: str, query_key: str) -> dict[str, Any] | None:
        key = normalize_query_key(query_key)

        def q() -> Any:
            return (
                self._client.table("drug_reference_cache")
                .select("*")
                .eq("source", source)
                .eq("query_key", key)
                .limit(1)
                .execute()
            )

        try:
            resp = await _run_q(q)
        except Exception as e:  # noqa: BLE001
            log.warning("drug_reference_cache select failed: %s", e)
            return None
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        exp = _parse_ts(row.get("expires_at"))
        if exp is not None and exp < datetime.now(UTC):
            return None
        return row

    async def upsert_reference(
        self,
        *,
        source: str,
        query_key: str,
        title: str,
        usage_text: str,
        indications_and_usage: str | None = None,
        dosage_and_administration: str | None = None,
        warnings: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        key = normalize_query_key(query_key)
        ttl_h = self._settings.drug_reference_cache_ttl_hours
        now = datetime.now(UTC)
        expires_at: str | None = None
        if ttl_h > 0:
            expires_at = (now + timedelta(hours=ttl_h)).isoformat()
        row: dict[str, Any] = {
            "source": source,
            "query_key": key,
            "title": title,
            "usage_text": usage_text,
            "indications_and_usage": indications_and_usage,
            "dosage_and_administration": dosage_and_administration,
            "warnings": warnings,
            "raw_payload": raw_payload or {},
            "fetched_at": now.isoformat(),
            "expires_at": expires_at,
        }

        def q() -> Any:
            return (
                self._client.table("drug_reference_cache")
                .upsert(row, on_conflict="source,query_key")
                .execute()
            )

        try:
            await _run_q(q)
        except Exception as e:  # noqa: BLE001
            log.warning("drug_reference_cache upsert failed: %s", e)

    def grounding_from_row(self, row: dict[str, Any]) -> DrugGrounding:
        return DrugGrounding(
            source=str(row.get("source") or "reference"),
            title=str(row.get("title") or ""),
            body_zh=str(row.get("usage_text") or ""),
        )

    async def get_personalized_reply(
        self,
        *,
        user_uuid: str,
        query_fingerprint: str,
    ) -> str | None:
        def q() -> Any:
            return (
                self._client.table("drug_personalization_cache")
                .select("personalized_text, expires_at")
                .eq("user_id", user_uuid)
                .eq("query_fingerprint", query_fingerprint)
                .limit(1)
                .execute()
            )

        try:
            resp = await _run_q(q)
        except Exception as e:  # noqa: BLE001
            log.warning("drug_personalization_cache select failed: %s", e)
            return None
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        exp = _parse_ts(row.get("expires_at"))
        if exp is not None and exp < datetime.now(UTC):
            return None
        text = row.get("personalized_text")
        return str(text).strip() if text else None

    async def save_personalized_reply(
        self,
        *,
        user_uuid: str,
        query_fingerprint: str,
        intent: str,
        personalized_text: str,
        locale: str,
        llm_meta: dict[str, Any],
    ) -> None:
        ttl_h = self._settings.drug_personalization_cache_ttl_hours
        now = datetime.now(UTC)
        expires_at: str | None = None
        if ttl_h > 0:
            expires_at = (now + timedelta(hours=ttl_h)).isoformat()
        row: dict[str, Any] = {
            "user_id": user_uuid,
            "query_fingerprint": query_fingerprint,
            "intent": intent,
            "personalized_text": personalized_text,
            "locale": locale,
            "llm_meta": llm_meta,
            "medication_id": None,
            "reference_cache_id": None,
            "updated_at": now.isoformat(),
            "expires_at": expires_at,
        }

        def q() -> Any:
            return (
                self._client.table("drug_personalization_cache")
                .upsert(row, on_conflict="user_id,query_fingerprint")
                .execute()
            )

        try:
            await _run_q(q)
        except Exception as e:  # noqa: BLE001
            log.warning("drug_personalization_cache upsert failed: %s", e)
