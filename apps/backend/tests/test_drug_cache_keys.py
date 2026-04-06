"""Stable keys for drug reference and personalization caches."""

from medbuddy.drug_cache_keys import (
    normalize_query_key,
    personalization_fingerprint,
    resolve_medication_id_for_personalization,
)
from medbuddy.models.domain import Intent, MedicationRecord


def test_normalize_query_key_collapses_case_and_spaces() -> None:
    assert normalize_query_key("  Aspirin\t 500 ") == "aspirin 500"


def test_personalization_fingerprint_depends_on_patient_list() -> None:
    fp1 = personalization_fingerprint(
        intent=Intent.EXPLAIN_MEDICATION,
        user_text="解釋 metformin",
        patient_context="list a",
    )
    fp2 = personalization_fingerprint(
        intent=Intent.EXPLAIN_MEDICATION,
        user_text="解釋 metformin",
        patient_context="list b",
    )
    assert fp1 != fp2


def test_personalization_fingerprint_differs_by_intent() -> None:
    ctx = "- med: 1"
    fp_e = personalization_fingerprint(
        intent=Intent.EXPLAIN_MEDICATION, user_text="aspirin", patient_context=ctx
    )
    fp_i = personalization_fingerprint(
        intent=Intent.INTERACTION_CHECK, user_text="aspirin", patient_context=ctx
    )
    assert fp_e != fp_i


def test_resolve_medication_id_single_match() -> None:
    meds = [
        MedicationRecord(
            id="m1", name="阿斯匹靈", dosage="100mg", schedule="QD", instructions_zh=None
        ),
        MedicationRecord(
            id="m2", name="metformin", dosage="500", schedule="BID", instructions_zh=None
        ),
    ]
    assert resolve_medication_id_for_personalization(meds, "解釋阿斯匹靈怎麼吃") == "m1"


def test_resolve_medication_id_ambiguous_returns_none() -> None:
    meds = [
        MedicationRecord(id="a", name="aspirin", dosage="1", schedule="QD", instructions_zh=None),
        MedicationRecord(
            id="b", name="aspirin xr", dosage="2", schedule="QD", instructions_zh=None
        ),
    ]
    assert resolve_medication_id_for_personalization(meds, "aspirin and aspirin xr") is None
