"""MedicationExtraction → MedicationDraft mapping."""

from medbuddy.llm.medication_draft_build import (
    dose_or_schedule_display,
    medication_draft_from_extraction,
    medication_draft_needs_add_confirmation,
)
from medbuddy.llm.schemas import MedicationExtraction
from medbuddy.models.domain import MedicationDraft


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


def test_needs_add_confirmation_when_dose_or_schedule_unspecified() -> None:
    un = "Unspecified"
    full = MedicationDraft(
        name="X",
        dosage="10mg",
        schedule="QD",
        instructions="with food",
    )
    assert not medication_draft_needs_add_confirmation(
        full, unspecified_label=un, user_text="Aspirin 10mg once daily with food"
    )

    sparse = MedicationDraft(name="X", dosage=un, schedule="QD", instructions=None)
    assert medication_draft_needs_add_confirmation(
        sparse, unspecified_label=un, user_text="add aspirin"
    )

    no_notes = MedicationDraft(name="X", dosage="10mg", schedule="QD", instructions=None)
    assert medication_draft_needs_add_confirmation(
        no_notes, unspecified_label=un, user_text="aspirin 10mg daily"
    )


def test_dose_or_schedule_display_maps_english_unspecified_to_locale_label() -> None:
    zh = "未註明"
    assert dose_or_schedule_display("unspecified", unspecified_label=zh) == zh
    assert dose_or_schedule_display("Unspecified", unspecified_label=zh) == zh
    assert dose_or_schedule_display("", unspecified_label=zh) == zh
    assert dose_or_schedule_display("100mg", unspecified_label=zh) == "100mg"


def test_needs_add_confirmation_when_model_infers_from_name_only() -> None:
    d = MedicationDraft(
        name="Aspirin",
        dosage="100mg",
        schedule="daily",
        instructions="after meal",
    )
    assert medication_draft_needs_add_confirmation(
        d, unspecified_label="Unspecified", user_text="add aspirin"
    )
