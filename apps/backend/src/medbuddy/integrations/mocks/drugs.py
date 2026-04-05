import asyncio

from medbuddy.i18n import t
from medbuddy.models.domain import DrugGrounding
from medbuddy.protocols.ports import DrugDataPort


class MockDrugData(DrugDataPort):
    def __init__(self, *, locale: str = "zh-TW") -> None:
        self._locale = locale
        self.queries: list[str] = []

    async def fetch_tfda_snippet(self, query: str) -> DrugGrounding | None:
        await asyncio.sleep(0)
        self.queries.append(query)
        loc = self._locale
        return DrugGrounding(
            source="TFDA(mock)",
            title=t("mocks.drugs.tfda_title", locale=loc, query=query),
            body_zh=t("mocks.drugs.tfda_body", locale=loc),
        )

    async def fetch_openfda_label_snippet(self, query: str) -> DrugGrounding | None:
        await asyncio.sleep(0)
        self.queries.append(f"openfda:{query}")
        loc = self._locale
        return DrugGrounding(
            source="OpenFDA(mock)",
            title=f"Label {query}",
            body_zh=t("mocks.drugs.openfda_body", locale=loc),
        )
