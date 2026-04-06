"""Stable keys for drug reference and personalization caches."""

from medbuddy.drug_cache_keys import normalize_query_key, personalization_fingerprint
from medbuddy.models.domain import Intent


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
