"""Wrap ``DrugDataPort`` with Supabase ``drug_reference_cache`` read-through caching."""

from __future__ import annotations

from medbuddy.drug_cache_keys import normalize_query_key
from medbuddy.integrations.supabase_drug_caches import SupabaseDrugCaches
from medbuddy.models.domain import DrugGrounding
from medbuddy.protocols.ports import DrugDataPort

SOURCE_TFDA = "tfda"
SOURCE_OPENFDA = "openfda"


class CachingDrugData(DrugDataPort):
    def __init__(self, inner: DrugDataPort, caches: SupabaseDrugCaches) -> None:
        self._inner = inner
        self._caches = caches

    async def fetch_tfda_snippet(self, query: str) -> DrugGrounding | None:
        key = normalize_query_key(query)
        hit = await self._caches.get_valid_reference(source=SOURCE_TFDA, query_key=key)
        if hit:
            return self._caches.grounding_from_row(hit)
        g = await self._inner.fetch_tfda_snippet(query)
        if g:
            await self._caches.upsert_reference(
                source=SOURCE_TFDA,
                query_key=key,
                title=g.title,
                usage_text=g.body_zh,
            )
        return g

    async def fetch_openfda_label_snippet(self, query: str) -> DrugGrounding | None:
        key = normalize_query_key(query)
        hit = await self._caches.get_valid_reference(source=SOURCE_OPENFDA, query_key=key)
        if hit:
            return self._caches.grounding_from_row(hit)
        g = await self._inner.fetch_openfda_label_snippet(query)
        if g:
            await self._caches.upsert_reference(
                source=SOURCE_OPENFDA,
                query_key=key,
                title=g.title,
                usage_text=g.body_zh,
            )
        return g
