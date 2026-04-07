"""Map structured LLM extraction to :class:`~medbuddy.models.domain.MedicationDraft`."""

from __future__ import annotations

from medbuddy.llm.schemas import MedicationExtraction
from medbuddy.models.domain import MedicationDraft
from medbuddy.reminders.dose_schedule import parse_hhmm


def medication_draft_from_extraction(
    extracted: MedicationExtraction, *, unspecified: str
) -> MedicationDraft | None:
    name = extracted.name.strip()
    if not name:
        return None
    hd = extracted.reminder_horizon_days
    if hd is not None:
        hd = max(1, min(90, int(hd)))
    raw_daily = extracted.daily_reminder_local_hhmm
    daily: str | None = None
    if raw_daily and raw_daily.strip():
        try:
            parse_hhmm(raw_daily.strip())
            daily = raw_daily.strip()
        except ValueError:
            daily = None
    fm = extracted.first_reminder_in_minutes
    if fm is not None:
        fm = int(fm)
        if fm <= 0:
            fm = None
    return MedicationDraft(
        name=name,
        dosage=extracted.dosage.strip() or unspecified,
        schedule=extracted.schedule.strip() or unspecified,
        instructions=extracted.instructions,
        first_reminder_in_minutes=fm,
        materialize_daily_reminders=extracted.materialize_daily_reminders,
        reminder_horizon_days=hd,
        needs_horizon_confirmation=extracted.needs_horizon_confirmation,
        daily_reminder_local_hhmm=daily,
    )
