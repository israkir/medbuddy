"""HTTP-backed drug data (OpenFDA + optional TFDA HTML fetch)."""

from __future__ import annotations

import urllib.parse

import httpx

from medbuddy.i18n import t
from medbuddy.models.domain import DrugGrounding
from medbuddy.protocols.ports import DrugDataPort


class HttpDrugData(DrugDataPort):
    def __init__(self, *, timeout: float = 20.0, locale: str = "zh-TW") -> None:
        self._timeout = timeout
        self._locale = locale

    async def fetch_openfda_label_snippet(self, query: str) -> DrugGrounding | None:
        q = urllib.parse.quote(query)
        url = (
            "https://api.fda.gov/drug/label.json?"
            f"search=openfda.brand_name:{q}+OR+openfda.generic_name:{q}&limit=1"
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
        results = data.get("results") or []
        if not results:
            return None
        first = results[0]
        text_bits: list[str] = []
        for key in ("indications_and_usage", "dosage_and_administration", "warnings"):
            block = first.get(key)
            if isinstance(block, list):
                text_bits.append("\n".join(block)[:2000])
        body = "\n".join(text_bits) or str(first)[:2000]
        return DrugGrounding(source="OpenFDA", title=query, body_zh=body)

    async def fetch_tfda_snippet(self, query: str) -> DrugGrounding | None:
        """TFDA has no stable public JSON API in prototype — extend with scraper/cache."""
        _ = query
        loc = self._locale
        return DrugGrounding(
            source="TFDA",
            title=t("tfda.pending_title", locale=loc),
            body_zh=t("tfda.pending_body", locale=loc),
        )
