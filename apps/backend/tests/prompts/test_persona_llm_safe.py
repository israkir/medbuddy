"""Patient context for LLM must not echo raw profile strings."""

from medbuddy.llm.prompts.persona import build_patient_context_for_llm


def test_llm_context_includes_preferred_name_for_addressing_omits_other_raw_profile() -> None:
    user_row = {
        "preferred_name": "Secret User",
        "age_years": 71,
        "emergency_contact": None,
        "health_notes": "diabetes",
    }
    ctx = build_patient_context_for_llm(user_row, [], locale="en")
    assert "Secret User" in ctx
    assert "diabetes" not in ctx
    assert "71" not in ctx
    assert "70" in ctx


def test_llm_context_includes_gender_category_label() -> None:
    user_row = {
        "preferred_name": None,
        "age_years": 60,
        "gender": "female",
        "emergency_contact": None,
        "health_notes": None,
    }
    ctx = build_patient_context_for_llm(user_row, [], locale="en")
    assert "Female" in ctx
