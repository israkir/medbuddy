"""MedicationExtraction → MedicationDraft mapping."""

from medbuddy.llm.medication_draft_build import (
    apply_one_off_reminder_dose_default,
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
    assert not medication_draft_needs_add_confirmation(
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


def test_one_off_reminder_a_pill_counts_as_dose_cue() -> None:
    un = "Unspecified"
    d = MedicationDraft(
        name="Aspirin",
        dosage=un,
        schedule=un,
        first_reminder_in_minutes=1,
        materialize_daily_reminders=False,
    )
    d = apply_one_off_reminder_dose_default(d, unspecified_label=un, locale="en")
    assert not medication_draft_needs_add_confirmation(
        d,
        unspecified_label=un,
        user_text="remind me take a pill of aspirin after 1 minute",
    )


def test_one_off_reminder_minute_phrase_without_pill_word() -> None:
    un = "未註明"
    d = MedicationDraft(
        name="阿斯匹靈",
        dosage=un,
        schedule=un,
        first_reminder_in_minutes=1,
        materialize_daily_reminders=False,
    )
    d = apply_one_off_reminder_dose_default(d, unspecified_label=un, locale="zh-TW")
    assert not medication_draft_needs_add_confirmation(
        d,
        unspecified_label=un,
        user_text="一分鐘後提醒我吃阿斯匹靈",
    )


def test_apply_one_off_reminder_dose_default_fills_placeholder() -> None:
    un = "Unspecified"
    d = MedicationDraft(
        name="Aspirin",
        dosage=un,
        schedule=un,
        first_reminder_in_minutes=5,
        materialize_daily_reminders=False,
    )
    out = apply_one_off_reminder_dose_default(d, unspecified_label=un, locale="en")
    assert out.dosage != un
    assert "pill" in out.dosage.lower()


def test_extraction_indefinite_en_suppresses_horizon_ask() -> None:
    """Chronic English phrasing → is_indefinite=True forces needs_horizon_confirmation=False."""
    ext = MedicationExtraction(
        name="Losartan",
        dosage="50mg",
        schedule="once daily",
        is_indefinite=True,
        # Even if the extraction (wrongly) flagged horizon-confirmation, the builder must suppress it.
        needs_horizon_confirmation=True,
        reminder_horizon_days=30,
        daily_reminder_local_hhmm="08:00",
    )
    d = medication_draft_from_extraction(ext, unspecified="unspecified")
    assert d is not None
    assert d.is_indefinite is True
    assert d.needs_horizon_confirmation is False
    assert d.materialize_daily_reminders is True
    # Horizon days are dropped so the server default applies on every refill.
    assert d.reminder_horizon_days is None


def test_extraction_indefinite_zh_round_trips() -> None:
    """Chronic Chinese phrasing snapshot — is_indefinite=True is honored."""
    ext = MedicationExtraction(
        name="降血壓藥",
        dosage="50mg",
        schedule="每日一次",
        is_indefinite=True,
        daily_reminder_local_hhmm="08:00",
    )
    d = medication_draft_from_extraction(ext, unspecified="未註明")
    assert d is not None
    assert d.is_indefinite is True
    assert d.needs_horizon_confirmation is False


def test_extraction_finite_preserves_existing_horizon_behavior() -> None:
    """Default extraction (no chronic signal) keeps existing horizon-confirmation behaviour."""
    ext = MedicationExtraction(
        name="Aspirin",
        dosage="100mg",
        schedule="once daily",
        needs_horizon_confirmation=True,
        materialize_daily_reminders=False,
    )
    d = medication_draft_from_extraction(ext, unspecified="unspecified")
    assert d is not None
    assert d.is_indefinite is False
    assert d.needs_horizon_confirmation is True
    assert d.materialize_daily_reminders is False
