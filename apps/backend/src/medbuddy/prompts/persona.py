from __future__ import annotations

from typing import Any

from medbuddy.i18n import t


def get_system_persona(*, locale: str) -> str:
    return t("prompts.system_persona", locale=locale)


def format_patient_medication_context(meds: list, *, locale: str) -> str:
    if not meds:
        return t("prompts.no_medications", locale=locale)
    lines = []
    for m in meds:
        lines.append(
            t(
                "prompts.medication_line",
                locale=locale,
                name=m.name,
                dosage=m.dosage,
                schedule=m.schedule,
            )
        )
    return "\n".join(lines)


def format_patient_demographics(user_row: dict[str, Any], *, locale: str) -> str:
    """Plain-language facts from light onboarding (name, age, notes). Empty if unset."""
    name = user_row.get("preferred_name")
    age = user_row.get("age_years")
    notes = user_row.get("health_notes")
    contact = user_row.get("emergency_contact")
    parts: list[str] = []
    if isinstance(name, str) and name.strip():
        parts.append(t("prompts.demographics_name", locale=locale, name=name.strip()))
    if isinstance(age, int):
        parts.append(t("prompts.demographics_age", locale=locale, age=age))
    if isinstance(notes, str) and notes.strip():
        parts.append(t("prompts.demographics_notes", locale=locale, notes=notes.strip()))
    if isinstance(contact, str) and contact.strip():
        parts.append(t("prompts.demographics_contact", locale=locale, contact=contact.strip()))
    if not parts:
        return ""
    header = t("prompts.demographics_header", locale=locale)
    return f"{header}\n" + "\n".join(parts)


def build_patient_context_for_llm(user_row: dict[str, Any], meds: list, *, locale: str) -> str:
    demo = format_patient_demographics(user_row, locale=locale)
    med_part = format_patient_medication_context(meds, locale=locale)
    if demo:
        return f"{demo}\n\n{med_part}"
    return med_part
