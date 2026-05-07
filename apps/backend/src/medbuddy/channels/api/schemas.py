"""Pydantic models for the standalone app JSON API."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ProfileGender(str, Enum):
    """Coarse sex/gender for profile and clinical context (user-chosen categories)."""

    FEMALE = "female"
    MALE = "male"
    NON_BINARY = "non_binary"
    PREFER_NOT_SAY = "prefer_not_say"
    OTHER = "other"


class AppLocale(str, Enum):
    """Standalone app UI language (matches Expo i18n resources)."""

    EN = "en"
    ZH_TW = "zh-TW"


class OnboardingSubmit(BaseModel):
    """First-run profile for the standalone app (large-type friendly fields)."""

    preferred_name: str = Field(..., min_length=1, max_length=80)
    age_years: int | None = Field(None, ge=0, le=120)
    gender: ProfileGender | None = None
    emergency_contact: str | None = Field(None, max_length=200)
    health_notes: str | None = Field(None, max_length=1000)
    locale: AppLocale = Field(
        default=AppLocale.ZH_TW,
        description="App UI language (en or zh-TW)",
    )
    timezone: str | None = Field(
        None,
        max_length=64,
        description="IANA timezone (e.g. Asia/Taipei); omit for default Asia/Taipei",
    )

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            return None
        try:
            ZoneInfo(s)
        except (ZoneInfoNotFoundError, OSError) as e:
            raise ValueError("timezone must be a valid IANA timezone name") from e
        return s


class MessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)


class MessageReply(BaseModel):
    reply: str
    metadata: dict[str, object] = Field(
        default_factory=dict,
        description="Structured flags for the client UI (e.g. simulated emergency notification).",
    )


class MessageVoiceReply(BaseModel):
    """Assistant reply after transcribing a voice upload (same text pipeline as ``MessageCreate``)."""

    reply: str
    transcript: str
    metadata: dict[str, object] = Field(default_factory=dict)


class MeResponse(BaseModel):
    app_user_id: str
    preferred_name: str | None = None
    age_years: int | None = None
    gender: str | None = None
    emergency_contact: str | None = None
    health_notes: str | None = None
    timezone: str = Field(
        default="Asia/Taipei",
        description="IANA timezone used for medication reminders (default Asia/Taipei)",
    )
    locale: str = Field(
        default="zh-TW",
        description="App UI language (en or zh-TW)",
    )
    onboarding_completed_at: str | None = None


class MedicationSummaryItemResponse(BaseModel):
    name: str
    dosage: str
    schedule: str
    purpose: str
    notes: str | None = None


class HealthSummaryResponse(BaseModel):
    """Doctor-ready health summary returned by ``GET /v1/app/summary``."""

    generated_at: datetime
    summary_for_doctor: str = Field(description="Concise clinical paragraph suitable for a doctor.")
    medications: list[MedicationSummaryItemResponse]
    key_concerns: list[str]
    reported_symptoms: list[str]
    medication_adherence_notes: str
    recommended_questions: list[str]
    plain_text: str = Field(description="Full summary as a single formatted text block.")
