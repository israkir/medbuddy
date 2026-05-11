from __future__ import annotations

import logging
from typing import Any

from medbuddy.core.i18n import t
from medbuddy.models.domain import HealthConditionRecord
from medbuddy.llm.medication_draft_build import dose_or_schedule_display
from medbuddy.application.profile.emergency_contacts import (
    emergency_contact_hint,
    emergency_contacts_redacted_hint,
    normalize_emergency_contacts,
)

log = logging.getLogger(__name__)

_PROFILE_GENDER_I18N: dict[str, str] = {
    "female": "prompts.gender_option_female",
    "male": "prompts.gender_option_male",
    "non_binary": "prompts.gender_option_non_binary",
    "prefer_not_say": "prompts.gender_option_prefer_not_say",
    "other": "prompts.gender_option_other",
}


def normalized_profile_gender(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    g = value.strip().lower()
    return g if g in _PROFILE_GENDER_I18N else None


def gender_option_label(gender_key: str, *, locale: str) -> str:
    return t(_PROFILE_GENDER_I18N[gender_key], locale=locale)


def _age_band_label(age: int, *, locale: str) -> str:
    if age >= 90:
        return t("prompts.llm_signal_age_band_90_plus", locale=locale)
    low = (age // 10) * 10
    high = min(low + 9, 89)
    return t("prompts.llm_signal_age_band_range", locale=locale, low=low, high=high)


def _profile_contact_hint(user_row: dict[str, Any]) -> str:
    """Return structured contact hint, falling back to legacy single-string field."""
    contacts = normalize_emergency_contacts(user_row.get("emergency_contacts"))
    hint = emergency_contact_hint(contacts)
    if hint.strip():
        return hint
    legacy = user_row.get("emergency_contact")
    if isinstance(legacy, str):
        return legacy.strip()
    return ""


def get_system_persona(*, locale: str) -> str:
    return t("prompts.system_persona", locale=locale)


def format_patient_medication_context(meds: list, *, locale: str) -> str:
    if not meds:
        return t("prompts.no_medications", locale=locale)
    un = t("medication.unspecified", locale=locale)
    lines: list[str] = []
    any_incomplete = False
    for m in meds:
        dosage = dose_or_schedule_display(m.dosage, unspecified_label=un)
        schedule = dose_or_schedule_display(m.schedule, unspecified_label=un)
        if dosage == un or schedule == un:
            any_incomplete = True
        lines.append(
            t(
                "prompts.medication_line",
                locale=locale,
                name=m.name,
                dosage=dosage,
                schedule=schedule,
            )
        )
    body = "\n".join(lines)
    if any_incomplete:
        body += "\n" + t("medication.list_hint_fill_dose_schedule", locale=locale)
    return body


def format_patient_demographics(user_row: dict[str, Any], *, locale: str) -> str:
    """Plain-language facts from light onboarding (name, age, gender, contact). Empty if unset."""
    name = user_row.get("preferred_name")
    age = user_row.get("age_years")
    gender_key = normalized_profile_gender(user_row.get("gender"))
    contact = _profile_contact_hint(user_row)
    parts: list[str] = []
    if isinstance(name, str) and name.strip():
        parts.append(t("prompts.demographics_name", locale=locale, name=name.strip()))
    if isinstance(age, int):
        parts.append(t("prompts.demographics_age", locale=locale, age=age))
    if gender_key:
        parts.append(
            t(
                "prompts.demographics_gender",
                locale=locale,
                label=gender_option_label(gender_key, locale=locale),
            )
        )
    if isinstance(contact, str) and contact.strip():
        parts.append(t("prompts.demographics_contact", locale=locale, contact=contact.strip()))
    if not parts:
        return ""
    header = t("prompts.demographics_header", locale=locale)
    return f"{header}\n" + "\n".join(parts)


def _health_condition_display_line(c: HealthConditionRecord) -> str:
    parts = [c.name]
    if c.severity:
        parts.append(f"({c.severity})")
    if c.notes:
        parts.append(f"— {c.notes}")
    return " ".join(parts)


def format_health_conditions_block_for_llm(
    conditions: list[HealthConditionRecord],
    *,
    locale: str,
) -> str:
    """Grouped allergies / conditions / history for external LLM context."""
    if not conditions:
        return ""
    by_cat: dict[str, list[HealthConditionRecord]] = {
        "allergy": [],
        "condition": [],
        "history": [],
    }
    for c in conditions:
        key = c.category if c.category in by_cat else "condition"
        by_cat[key].append(c)
    lines: list[str] = []
    if by_cat["allergy"]:
        items = "; ".join(_health_condition_display_line(c) for c in by_cat["allergy"])
        lines.append(t("prompts.llm_health_allergies", locale=locale, items=items))
    if by_cat["condition"]:
        items = "; ".join(_health_condition_display_line(c) for c in by_cat["condition"])
        lines.append(t("prompts.llm_health_conditions", locale=locale, items=items))
    if by_cat["history"]:
        items = "; ".join(_health_condition_display_line(c) for c in by_cat["history"])
        lines.append(t("prompts.llm_health_history", locale=locale, items=items))
    if not lines:
        return ""
    intro = t("prompts.llm_health_structured_intro", locale=locale)
    return intro + "\n" + "\n".join(lines)


def format_patient_profile_signals_for_llm(
    user_row: dict[str, Any],
    *,
    locale: str,
    include_health_notes: bool = False,
    health_conditions: list[HealthConditionRecord] | None = None,
) -> tuple[str, dict[str, str]]:
    """Coarse cues for the model: preferred form of address when set; age band (not exact age);
    gender label; structured health conditions and emergency-contact signals.

    When ``include_health_notes=True`` (legacy name: **structured health detail**), include the
    full grouped allergies/conditions/history block for drug-safety checks.

    Returns:
        (signals_block, pii_token_substitutions)
        signals_block           — multi-line string for the system prompt.
        pii_token_substitutions — map of ``[EMERGENCY_CONTACT_N]`` → real contact string;
                                  empty dict when no contacts are on file.
    """
    name = user_row.get("preferred_name")
    age = user_row.get("age_years")
    gender_key = normalized_profile_gender(user_row.get("gender"))
    parts: list[str] = []
    if isinstance(name, str) and name.strip():
        parts.append(t("prompts.llm_preferred_address_form", locale=locale, name=name.strip()))
    if isinstance(age, int):
        parts.append(
            t(
                "prompts.llm_signal_age_band",
                locale=locale,
                band=_age_band_label(age, locale=locale),
            )
        )
    if gender_key:
        parts.append(
            t(
                "prompts.llm_signal_gender",
                locale=locale,
                label=gender_option_label(gender_key, locale=locale),
            )
        )
    contacts_raw = user_row.get("emergency_contacts")
    redacted_hint, pii_token_substitutions = emergency_contacts_redacted_hint(
        contacts_raw, locale=locale
    )
    if redacted_hint.strip():
        parts.append(redacted_hint)
    elif _profile_contact_hint(user_row):
        # Legacy single-string contact: fall back to boolean hint (no token rehydration needed).
        parts.append(t("prompts.llm_signal_has_emergency_contact", locale=locale))
    hc_list = health_conditions or []
    hc_block = format_health_conditions_block_for_llm(hc_list, locale=locale)
    if hc_block.strip():
        if include_health_notes:
            parts.append(
                t("prompts.llm_signal_health_conditions_detail", locale=locale, body=hc_block)
            )
        else:
            parts.append(t("prompts.llm_signal_has_health_conditions", locale=locale))
    if not parts:
        return "", pii_token_substitutions
    header = t("prompts.llm_profile_signals_header", locale=locale)
    return f"{header}\n" + "\n".join(f"- {p}" for p in parts), pii_token_substitutions


def format_profile_gaps(
    user_row: dict[str, Any],
    *,
    locale: str,
    active_health_condition_count: int = 0,
) -> str:
    """List profile dimensions not stored yet (so the model can ask when helpful)."""
    name = user_row.get("preferred_name")
    age = user_row.get("age_years")
    gender_key = normalized_profile_gender(user_row.get("gender"))
    contact = _profile_contact_hint(user_row)
    gaps: list[str] = []
    if not (isinstance(name, str) and name.strip()):
        gaps.append(t("prompts.gap_preferred_name", locale=locale))
    if not isinstance(age, int):
        gaps.append(t("prompts.gap_age", locale=locale))
    if not gender_key:
        gaps.append(t("prompts.gap_gender", locale=locale))
    if not (isinstance(contact, str) and contact.strip()):
        gaps.append(t("prompts.gap_contact", locale=locale))
    if active_health_condition_count <= 0:
        gaps.append(t("prompts.gap_health_conditions", locale=locale))
    if not gaps:
        return ""
    intro = t("prompts.profile_gaps_intro", locale=locale)
    return f"{intro}\n" + "\n".join(gaps)


def build_patient_context_for_chat_display(
    user_row: dict[str, Any], meds: list, *, locale: str, active_health_condition_count: int = 0
) -> str:
    """User-facing summary including stored profile text (not for third-party LLMs)."""
    demo = format_patient_demographics(user_row, locale=locale)
    gaps = format_profile_gaps(
        user_row, locale=locale, active_health_condition_count=active_health_condition_count
    )
    med_part = format_patient_medication_context(meds, locale=locale)
    blocks: list[str] = []
    if demo:
        blocks.append(demo)
    if gaps:
        blocks.append(gaps)
    if blocks:
        return "\n\n".join(blocks) + f"\n\n{med_part}"
    return med_part


def build_patient_context_for_llm(
    user_row: dict[str, Any],
    meds: list,
    *,
    locale: str,
    upcoming_doses_context: str | None = None,
    include_health_notes: bool = False,
    health_conditions: list[HealthConditionRecord] | None = None,
) -> str:
    """De-identified profile cues plus medications — safe for external model APIs.

    Pass ``include_health_notes=True`` for safety-critical calls (add_medication,
    interaction_check, explain_medication) so the model receives the full structured
    allergies/conditions/history block when available.
    """
    hc_list = health_conditions or []
    signals, _token_map = format_patient_profile_signals_for_llm(
        user_row,
        locale=locale,
        include_health_notes=include_health_notes,
        health_conditions=hc_list,
    )
    gaps = format_profile_gaps(user_row, locale=locale, active_health_condition_count=len(hc_list))
    med_part = format_patient_medication_context(meds, locale=locale)
    blocks: list[str] = []
    if signals:
        blocks.append(signals)
    if gaps:
        blocks.append(gaps)
    if blocks:
        base = "\n\n".join(blocks) + f"\n\n{med_part}"
    else:
        base = med_part
    if upcoming_doses_context and upcoming_doses_context.strip():
        result = f"{base}\n\n{upcoming_doses_context.strip()}"
    else:
        result = base
    log.info("build_patient_context_for_llm complete locale=%s chars=%d", locale, len(result))
    log.debug("build_patient_context_for_llm body:\n%s", result)
    return result
