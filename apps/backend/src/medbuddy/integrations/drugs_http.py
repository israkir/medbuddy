"""HTTP-backed drug data (OpenFDA + optional TFDA HTML fetch)."""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

from medbuddy.models.domain import DrugGrounding
from medbuddy.protocols.ports import DrugDataPort

_LABEL_SECTION_MAX = 2000


def _stringify_label_section(block: object, *, max_len: int = _LABEL_SECTION_MAX) -> str | None:
    if block is None:
        return None
    if isinstance(block, list):
        text = "\n".join(str(x) for x in block)
    else:
        text = str(block)
    text = text.strip()
    if not text:
        return None
    return text[:max_len]


def _openfda_display_title(first: dict[str, Any], fallback: str) -> str:
    openfda = first.get("openfda") if isinstance(first.get("openfda"), dict) else {}
    for key in ("brand_name", "generic_name"):
        names = openfda.get(key)
        if isinstance(names, list) and names:
            pick = str(names[0]).strip()
            if pick:
                return pick
    return fallback


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
        if not isinstance(first, dict):
            return None
        indications = _stringify_label_section(first.get("indications_and_usage"))
        dosage = _stringify_label_section(first.get("dosage_and_administration"))
        warnings = _stringify_label_section(first.get("warnings"))
        text_bits = [x for x in (indications, dosage, warnings) if x]
        body = "\n".join(text_bits) if text_bits else str(first)[:_LABEL_SECTION_MAX]
        title = _openfda_display_title(first, query)
        return DrugGrounding(
            source="OpenFDA",
            title=title,
            body_zh=body,
            indications_and_usage=indications,
            dosage_and_administration=dosage,
            warnings=warnings,
            raw_payload={"label": first},
        )

    async def fetch_tfda_snippet(self, query: str) -> DrugGrounding | None:
        """No live TFDA fetch yet — do not impersonate ``source=tfda`` or cache placeholder rows.

        Use :meth:`fetch_openfda_label_snippet` for US label text. Return ``None`` here until a real
        TFDA client exists, so ``drug_reference_cache.source`` stays accurate.
        """
        _ = query
        return None
