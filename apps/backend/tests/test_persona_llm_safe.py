"""Patient context for LLM must not echo raw profile strings."""

from medbuddy.prompts.persona import build_patient_context_for_llm


def test_llm_context_omits_raw_preferred_name() -> None:
    user_row = {
        "preferred_name": "Secret User",
        "age_years": 71,
        "emergency_contact": None,
        "health_notes": "diabetes",
    }
    ctx = build_patient_context_for_llm(user_row, [], locale="en")
    assert "Secret" not in ctx
    assert "User" not in ctx
    assert "diabetes" not in ctx
    assert "71" not in ctx
    assert "70" in ctx
