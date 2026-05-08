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


def test_llm_context_stored_preferred_name_in_signals_not_in_gaps() -> None:
    """Regression: patients.preferred_name must appear in the LLM block and must not list name gap."""
    user_row = {
        "preferred_name": "Mei",
        "age_years": None,
        "gender": None,
        "emergency_contact": None,
        "health_notes": None,
    }
    ctx = build_patient_context_for_llm(user_row, [], locale="en")
    assert "Mei" in ctx
    assert "Preferred form of address" in ctx
    assert "Preferred name / how to address them: not stored yet" not in ctx


def test_llm_context_whitespace_preferred_name_is_absent_and_gap_lists_name() -> None:
    user_row = {
        "preferred_name": "   ",
        "age_years": None,
        "gender": None,
        "emergency_contact": None,
        "health_notes": None,
    }
    ctx = build_patient_context_for_llm(user_row, [], locale="en")
    assert "Preferred name / how to address them: not stored yet" in ctx
    assert "Preferred form of address" not in ctx


def test_llm_context_zh_tw_includes_preferred_name_literal() -> None:
    user_row = {
        "preferred_name": "阿春",
        "age_years": None,
        "gender": None,
        "emergency_contact": None,
        "health_notes": None,
    }
    ctx = build_patient_context_for_llm(user_row, [], locale="zh-TW")
    assert "阿春" in ctx
    assert "慣用稱呼" in ctx
