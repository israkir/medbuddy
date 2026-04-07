"""HttpDrugData parses OpenFDA label JSON into structured grounding + raw payload."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from medbuddy.integrations.drugs_http import HttpDrugData


@pytest.mark.asyncio
async def test_tfda_snippet_is_none_until_integrated() -> None:
    g = await HttpDrugData(locale="en").fetch_tfda_snippet("anything")
    assert g is None


@pytest.mark.asyncio
async def test_openfda_grounding_fills_sections_and_raw() -> None:
    payload = {
        "results": [
            {
                "indications_and_usage": ["Diabetes type 2."],
                "dosage_and_administration": ["500 mg BID."],
                "warnings": ["Lactic acidosis."],
                "openfda": {"brand_name": ["METFORMIN HCL"]},
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json = MagicMock(return_value=payload)

    http_client = MagicMock()
    http_client.get = AsyncMock(return_value=mock_resp)

    g = await HttpDrugData(locale="en", http_client=http_client).fetch_openfda_label_snippet(
        "metformin"
    )

    http_client.get.assert_awaited_once()
    assert g is not None
    assert g.indications_and_usage == "Diabetes type 2."
    assert g.dosage_and_administration == "500 mg BID."
    assert g.warnings == "Lactic acidosis."
    assert g.title == "METFORMIN HCL"
    assert g.raw_payload is not None
    assert g.raw_payload["label"]["openfda"]["brand_name"] == ["METFORMIN HCL"]
