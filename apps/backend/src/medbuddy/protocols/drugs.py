"""Drug data and drug-cache interfaces."""

from __future__ import annotations

from typing import Protocol

from medbuddy.models.domain import DrugGrounding


class DrugDataPort(Protocol):
    async def fetch_tfda_snippet(self, query: str) -> DrugGrounding | None: ...

    async def fetch_openfda_label_snippet(self, query: str) -> DrugGrounding | None: ...
