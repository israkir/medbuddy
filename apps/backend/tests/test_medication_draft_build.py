"""MedicationExtraction → MedicationDraft mapping."""

from medbuddy.llm.medication_draft_build import medication_draft_from_extraction
from medbuddy.llm.schemas import MedicationExtraction


def test_extraction_multi_daily_times_sets_list() -> None:
    ext = MedicationExtraction(
        name="Aspirin",
        dosage="50mg",
        schedule="TID",
        reminder_horizon_days=3,
        daily_reminder_local_hhmm_list=["12:30", "08:00", "18:30"],
    )
    d = medication_draft_from_extraction(ext, unspecified="unspecified")
    assert d is not None
    assert d.daily_reminder_local_hhmm_list == ["08:00", "12:30", "18:30"]
    assert d.daily_reminder_local_hhmm is None
    assert d.reminder_horizon_days == 3
