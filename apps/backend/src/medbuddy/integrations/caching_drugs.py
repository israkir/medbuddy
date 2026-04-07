"""Wrap ``DrugDataPort`` with Supabase ``drug_reference_cache`` read-through caching."""

from __future__ import annotations

from medbuddy.drug_cache_keys import (
    DRUG_REFERENCE_SOURCE_OPENFDA,
    DRUG_REFERENCE_SOURCE_TFDA,
    normalize_query_key,
)
from medbuddy.integrations.persistence.supabase_drug_caches import SupabaseDrugCaches
from medbuddy.models.domain import DrugGrounding
from medbuddy.protocols.ports import DrugDataPort


class CachingDrugData(DrugDataPort):
    def __init__(self, inner: DrugDataPort, caches: SupabaseDrugCaches) -> None:
        self._inner = inner
        self._caches = caches

    async def fetch_tfda_snippet(self, query: str) -> DrugGrounding | None:
        key = normalize_query_key(query)
        hit = await self._caches.get_valid_reference(
            source=DRUG_REFERENCE_SOURCE_TFDA, query_key=key
        )
        if hit:
            return self._caches.grounding_from_row(hit)
        g = await self._inner.fetch_tfda_snippet(query)
        if g:
            await self._caches.upsert_reference(
                source=DRUG_REFERENCE_SOURCE_TFDA,
                query_key=key,
                title=g.title,
                usage_text=g.body_zh,
                indications_and_usage=g.indications_and_usage,
                dosage_and_administration=g.dosage_and_administration,
                warnings=g.warnings,
                raw_payload=g.raw_payload,
            )
        return g

    async def fetch_openfda_label_snippet(self, query: str) -> DrugGrounding | None:
        key = normalize_query_key(query)
        hit = await self._caches.get_valid_reference(
            source=DRUG_REFERENCE_SOURCE_OPENFDA, query_key=key
        )
        if hit:
            return self._caches.grounding_from_row(hit)
        g = await self._inner.fetch_openfda_label_snippet(query)
        if g:
            await self._caches.upsert_reference(
                source=DRUG_REFERENCE_SOURCE_OPENFDA,
                query_key=key,
                title=g.title,
                usage_text=g.body_zh,
                indications_and_usage=g.indications_and_usage,
                dosage_and_administration=g.dosage_and_administration,
                warnings=g.warnings,
                raw_payload=g.raw_payload,
            )
        return g
