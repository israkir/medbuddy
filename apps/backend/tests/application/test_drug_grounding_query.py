"""Registry lookup query resolution (short follow-ups, weak tokens)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from medbuddy.application.drug_grounding_query import resolve_registry_lookup_query
from medbuddy.integrations.caching_drugs import CachingDrugData, is_weak_grounding_query
from medbuddy.models.domain import ConversationTurn, MedicationRecord
from medbuddy.models.domain import DrugGrounding


def test_is_weak_grounding_query_sure_and_metformin() -> None:
    assert is_weak_grounding_query("sure") is True
    assert is_weak_grounding_query("好") is True
    assert is_weak_grounding_query("metformin") is False
    assert is_weak_grounding_query("b12") is False


def test_resolve_sure_from_catalog_in_assistant_turn() -> None:
    meds = [
        MedicationRecord(
            id="m1",
            name="Vitamin C",
            dosage="500mg",
            schedule="daily",
        )
    ]
    hist = [
        ConversationTurn(
            role="assistant",
            content="I can tell you about side effects for Vitamin C. Want that?",
        ),
    ]
    q = resolve_registry_lookup_query(
        user_text="sure",
        history=hist,
        medications=meds,
    )
    assert q == "Vitamin C"


def test_resolve_sure_vitamin_c_fallback_when_not_on_list() -> None:
    hist = [
        ConversationTurn(
            role="assistant",
            content="If you want, I can share interaction notes for vitamin C.",
        ),
    ]
    q = resolve_registry_lookup_query(
        user_text="sure",
        history=hist,
        medications=[],
    )
    assert q == "vitamin c"


def test_resolve_medication_id_overrides_weak_user_text() -> None:
    meds = [
        MedicationRecord(id="mid-9", name="Aspirin", dosage="81mg", schedule="daily"),
    ]
    q = resolve_registry_lookup_query(
        user_text="ok",
        history=[],
        medications=meds,
        medication_id="mid-9",
    )
    assert q == "Aspirin"


def test_resolve_drug_query_from_tool_args() -> None:
    q = resolve_registry_lookup_query(
        user_text="yes please",
        history=[],
        medications=[],
        drug_query="Ibuprofen",
    )
    assert q == "Ibuprofen"


def test_resolve_strong_user_text_unchanged() -> None:
    q = resolve_registry_lookup_query(
        user_text="  What is metformin? ",
        history=[],
        medications=[],
    )
    assert q == "What is metformin?"


def test_resolve_sure_no_context_returns_none() -> None:
    assert (
        resolve_registry_lookup_query(
            user_text="sure",
            history=[],
            medications=[],
        )
        is None
    )


@pytest.mark.asyncio
async def test_caching_drug_data_skips_weak_query_without_calling_inner() -> None:
    inner = MagicMock()
    inner.fetch_openfda_label_snippet = AsyncMock(
        return_value=DrugGrounding(
            source="OpenFDA",
            title="X",
            body_zh="y",
        )
    )
    caches = MagicMock()
    caches.get_valid_reference = AsyncMock(return_value=None)
    caches.upsert_reference = AsyncMock()
    caching = CachingDrugData(inner, caches)
    out = await caching.fetch_openfda_label_snippet("sure")
    assert out is None
    inner.fetch_openfda_label_snippet.assert_not_awaited()
    caches.upsert_reference.assert_not_awaited()
