from __future__ import annotations

import logging
from typing import Any

from medbuddy.core.i18n import t
from medbuddy.llm.medication_draft_build import dose_or_schedule_display
from medbuddy.application.profile.emergency_contacts import (
    emergency_contact_hint,
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
    """Plain-language facts from light onboarding (name, age, notes). Empty if unset."""
    name = user_row.get("preferred_name")
    age = user_row.get("age_years")
    gender_key = normalized_profile_gender(user_row.get("gender"))
    notes = user_row.get("health_notes")
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
    if isinstance(notes, str) and notes.strip():
        parts.append(t("prompts.demographics_notes", locale=locale, notes=notes.strip()))
    if isinstance(contact, str) and contact.strip():
        parts.append(t("prompts.demographics_contact", locale=locale, contact=contact.strip()))
    if not parts:
        return ""
    header = t("prompts.demographics_header", locale=locale)
    return f"{header}\n" + "\n".join(parts)


def format_patient_profile_signals_for_llm(
    user_row: dict[str, Any],
    *,
    locale: str,
    include_health_notes: bool = False,
) -> str:
    """Coarse cues for the model: preferred form of address when set; age band (not exact age);
    gender label; health-notes / emergency-contact signals (raw strings omitted unless
    ``include_health_notes=True``).

    When ``include_health_notes=True`` the actual health notes text is included
    so the model can cross-check drug contraindications or allergy conflicts.
    """
    name = user_row.get("preferred_name")
    age = user_row.get("age_years")
    gender_key = normalized_profile_gender(user_row.get("gender"))
    notes = user_row.get("health_notes")
    contact = _profile_contact_hint(user_row)
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
    if isinstance(notes, str) and notes.strip():
        if include_health_notes:
            parts.append(
                t("prompts.llm_signal_health_notes_full", locale=locale, notes=notes.strip())
            )
        else:
            parts.append(t("prompts.llm_signal_has_health_notes", locale=locale))
    if isinstance(contact, str) and contact.strip():
        parts.append(t("prompts.llm_signal_has_emergency_contact", locale=locale))
    if not parts:
        return ""
    header = t("prompts.llm_profile_signals_header", locale=locale)
    return f"{header}\n" + "\n".join(f"- {p}" for p in parts)


def format_profile_gaps(user_row: dict[str, Any], *, locale: str) -> str:
    """List profile dimensions not stored yet (so the model can ask when helpful)."""
    name = user_row.get("preferred_name")
    age = user_row.get("age_years")
    gender_key = normalized_profile_gender(user_row.get("gender"))
    notes = user_row.get("health_notes")
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
    if not (isinstance(notes, str) and notes.strip()):
        gaps.append(t("prompts.gap_health_notes", locale=locale))
    if not gaps:
        return ""
    intro = t("prompts.profile_gaps_intro", locale=locale)
    return f"{intro}\n" + "\n".join(gaps)


def build_patient_context_for_chat_display(
    user_row: dict[str, Any], meds: list, *, locale: str
) -> str:
    """User-facing summary including stored profile text (not for third-party LLMs)."""
    demo = format_patient_demographics(user_row, locale=locale)
    gaps = format_profile_gaps(user_row, locale=locale)
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
) -> str:
    """De-identified profile cues plus medications — safe for external model APIs.

    Pass ``include_health_notes=True`` for safety-critical calls (add_medication,
    interaction_check, explain_medication) so the model can detect contraindications
    or allergy conflicts from the patient's stored health notes.
    """
    signals = format_patient_profile_signals_for_llm(
        user_row, locale=locale, include_health_notes=include_health_notes
    )
    gaps = format_profile_gaps(user_row, locale=locale)
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
    log.info(
        "build_patient_context_for_llm complete locale=%s chars=%d:\n%s",
        locale,
        len(result),
        result,
    )
    return result
