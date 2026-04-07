"""Pydantic schemas for structured LLM outputs.

These are passed to ``generate_structured()`` so the model returns
type-safe objects instead of raw text that needs JSON fence stripping.
All fields use ``description`` so Gemini's response_schema renders
clear field hints in the JSON schema it sends to the model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MedicationExtraction(BaseModel):
    """Structured medication extracted from a user message."""

    name: str = Field(description="Generic or brand name of the medication")
    dosage: str = Field(description="Dosage amount and unit, e.g. '10mg' or '未指定'")
    schedule: str = Field(description="Frequency/timing, e.g. '每日一次' or '未指定'")
    instructions: str | None = Field(
        default=None,
        description="Additional instructions from the user in their own words, or null",
    )
    first_reminder_in_minutes: int | None = Field(
        default=None,
        description=(
            "If the user asked for a first/one-off reminder soon (e.g. in N minutes), set N; else null"
        ),
    )
    materialize_daily_reminders: bool = Field(
        default=True,
        description=(
            "False if the user only wants a one-off / first reminder; True if recurring daily reminders apply"
        ),
    )
    reminder_horizon_days: int | None = Field(
        default=None,
        description="Explicit number of days to schedule daily reminders (1-90), or null for server default",
    )
    needs_horizon_confirmation: bool = Field(
        default=False,
        description=(
            "True if the user did not say how long daily reminders should run and you should ask them"
        ),
    )
    daily_reminder_local_hhmm: str | None = Field(
        default=None,
        description="If the user gave a daily clock time (HH:MM local), set it; else null",
    )


class RemovalResolution(BaseModel):
    """Which medication the user wants to stop taking."""

    medication_id: str | None = Field(
        default=None,
        description="UUID of the medication to remove, or null if unclear",
    )


class IntentClassification(BaseModel):
    """Classified intent for a user message."""

    intent: str = Field(
        description=(
            "Exactly one of: add_medication, list_medications, remove_medication, confirm_dose, "
            "explain_medication, interaction_check, log_vital, request_summary, "
            "update_profile, update_locale, off_topic, general_question. "
            "Follow the system routing rules: each value maps to one assistant tool or fallback. "
            "add_medication = save/track drug or dose reminders; explain_medication = ask what/why "
            "about a drug without adding to list; interaction_check = combine substances; "
            "general_question = only when no more specific intent fits."
        )
    )
    reasoning: str = Field(
        description=(
            "One sentence: user goal + which tool/path this intent maps to (e.g. add_medication → "
            "persist medication and reminders)."
        )
    )


class ProfilePatchExtraction(BaseModel):
    """Profile fields extracted from a user message (all optional)."""

    preferred_name: str | None = Field(
        default=None,
        max_length=80,
        description="Preferred name or how to address the user; null if not stated or unclear",
    )
    age_years: int | None = Field(
        default=None,
        ge=0,
        le=120,
        description="Age in years if clearly stated; null otherwise",
    )
    gender: str | None = Field(
        default=None,
        description=(
            "One of: female, male, non_binary, other, prefer_not_say — null if not stated"
        ),
    )
    emergency_contact: str | None = Field(
        default=None,
        max_length=200,
        description="Family or emergency contact if clearly given; null otherwise",
    )
    health_notes: str | None = Field(
        default=None,
        max_length=1000,
        description=(
            "Allergies or important persistent health notes if the user is updating their "
            "profile; null for one-off symptoms or dose-related comments"
        ),
    )


class DoseConfirmationNoteExtraction(BaseModel):
    """Note to attach when the user confirms taking a dose."""

    note: str | None = Field(
        default=None,
        max_length=500,
        description=(
            "If the user mentions a side effect, reaction, symptom, or anything to remember "
            "for this dose (e.g. headache after taking it), capture it briefly; else null"
        ),
    )


class LocaleIntentExtraction(BaseModel):
    """Which reply language the user wants when switching UI/conversation language."""

    target_locale: Literal["en", "zh-TW"] | None = Field(
        default=None,
        description=(
            "en if they want English replies, zh-TW for Traditional Chinese (Taiwan); "
            "null if the message is not asking to change reply language"
        ),
    )


class InteractionPair(BaseModel):
    """A single potential drug-drug or drug-condition interaction."""

    drug_a: str = Field(description="First drug or substance name")
    drug_b: str = Field(description="Second drug, substance, or condition")
    severity: str = Field(description="One of: none, mild, moderate, severe, unknown")
    description: str = Field(description="Plain-language explanation of the interaction risk")
    recommendation: str = Field(
        description="What the user should do (e.g. take with food, consult doctor)"
    )


class InteractionCheckResult(BaseModel):
    """Structured result of a drug interaction analysis."""

    medications_checked: list[str] = Field(
        description="Names of medications checked in this analysis"
    )
    interactions: list[InteractionPair] = Field(
        description="All detected interactions; empty list if none found"
    )
    overall_severity: str = Field(
        description="Worst severity across all interactions: none, mild, moderate, severe"
    )
    summary: str = Field(description="One-paragraph plain-language summary for the patient")
    disclaimer: str = Field(
        description="Standard disclaimer reminding patient to consult their doctor"
    )


class MedicationSummaryItem(BaseModel):
    """One medication entry in the doctor-ready health summary."""

    name: str
    dosage: str
    schedule: str
    purpose: str = Field(description="Likely therapeutic purpose in plain language")
    notes: str | None = Field(default=None, description="Patient-provided notes, if any")


class HealthSummaryResult(BaseModel):
    """Structured doctor-ready health summary."""

    summary_for_doctor: str = Field(
        description=(
            "Concise clinical summary paragraph suitable for a doctor to read in 30 seconds. "
            "Include patient demographics (anonymized), current medications, and any "
            "reported symptoms or concerns from recent conversations."
        )
    )
    key_concerns: list[str] = Field(
        description="Up to 5 bullet points the doctor should pay attention to"
    )
    reported_symptoms: list[str] = Field(
        description="Symptoms or side effects the patient has mentioned recently"
    )
    medication_adherence_notes: str = Field(
        description="Any adherence issues or skipped-dose mentions from recent conversations"
    )
    recommended_questions: list[str] = Field(
        description="Suggested questions the patient might want to ask the doctor"
    )
