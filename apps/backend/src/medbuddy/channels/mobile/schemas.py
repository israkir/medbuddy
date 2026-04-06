"""Pydantic models for the standalone app JSON API."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ProfileGender(str, Enum):
    """Coarse sex/gender for profile and clinical context (user-chosen categories)."""

    FEMALE = "female"
    MALE = "male"
    NON_BINARY = "non_binary"
    PREFER_NOT_SAY = "prefer_not_say"
    OTHER = "other"


class OnboardingSubmit(BaseModel):
    """First-run profile for the standalone app (large-type friendly fields)."""

    preferred_name: str = Field(..., min_length=1, max_length=80)
    age_years: int | None = Field(None, ge=0, le=120)
    gender: ProfileGender | None = None
    emergency_contact: str | None = Field(None, max_length=200)
    health_notes: str | None = Field(None, max_length=1000)


class MessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)


class MessageReply(BaseModel):
    reply: str


class MeResponse(BaseModel):
    app_user_id: str
    preferred_name: str | None = None
    age_years: int | None = None
    gender: str | None = None
    emergency_contact: str | None = None
    health_notes: str | None = None
    onboarding_completed_at: str | None = None
