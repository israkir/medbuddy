"""Map structured LLM extraction to :class:`~medbuddy.models.domain.MedicationDraft`."""

from __future__ import annotations

from medbuddy.llm.schemas import MedicationExtraction
from medbuddy.models.domain import MedicationDraft
from medbuddy.reminders.dose_schedule import parse_hhmm


def _validated_hhmm_list(
    *,
    multi: list[str] | None,
    single: str | None,
) -> list[str]:
    out: list[str] = []
    if multi:
        for raw in multi:
            if not raw or not str(raw).strip():
                continue
            s = str(raw).strip()
            try:
                parse_hhmm(s)
            except ValueError:
                continue
            if s not in out:
                out.append(s)
    if not out and single and single.strip():
        try:
            s = single.strip()
            parse_hhmm(s)
            out.append(s)
        except ValueError:
            pass
    if not out:
        return []
    return sorted(out, key=lambda t: (parse_hhmm(t)[0], parse_hhmm(t)[1]))


def medication_draft_from_extraction(
    extracted: MedicationExtraction, *, unspecified: str
) -> MedicationDraft | None:
    name = extracted.name.strip()
    if not name:
        return None
    hd = extracted.reminder_horizon_days
    if hd is not None:
        hd = max(1, min(90, int(hd)))
    times = _validated_hhmm_list(
        multi=extracted.daily_reminder_local_hhmm_list,
        single=extracted.daily_reminder_local_hhmm,
    )
    daily_single: str | None = None
    daily_list: list[str] | None = None
    if len(times) == 1:
        daily_single = times[0]
    elif len(times) > 1:
        daily_list = times
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
        daily_reminder_local_hhmm=daily_single,
        daily_reminder_local_hhmm_list=daily_list,
    )
