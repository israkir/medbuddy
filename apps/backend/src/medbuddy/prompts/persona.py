from __future__ import annotations

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
