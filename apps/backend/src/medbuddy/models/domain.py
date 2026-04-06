from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class Intent(str, Enum):
    ADD_MEDICATION = "add_medication"
    LIST_MEDICATIONS = "list_medications"
    REMOVE_MEDICATION = "remove_medication"
    CONFIRM_DOSE = "confirm_dose"
    EXPLAIN_MEDICATION = "explain_medication"
    INTERACTION_CHECK = "interaction_check"
    LOG_VITAL = "log_vital"
    REQUEST_SUMMARY = "request_summary"
    UPDATE_PROFILE = "update_profile"
    GENERAL_QUESTION = "general_question"


class MessageKind(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    POSTBACK = "postback"
    FOLLOW = "follow"
    UNKNOWN = "unknown"


@dataclass
class LineUserContext:
    line_user_id: str
    display_name: str | None = None


@dataclass
class MedicationDraft:
    """Structured fields extracted from a user message before persisting."""

    name: str
    dosage: str
    schedule: str
    instructions_zh: str | None = None


@dataclass
class MedicationRecord:
    id: str
    name: str
    dosage: str
    schedule: str
    instructions_zh: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DoseEventReminderPayload:
    """Fields needed to send a LINE push for one scheduled dose."""

    dose_event_id: str
    line_user_id: str
    medication_name: str
    dosage: str
    schedule: str
    scheduled_at: datetime
    user_timezone: str


@dataclass
class ConversationTurn:
    role: str  # "user" | "assistant"
    content: str
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class DrugGrounding:
    source: str
    title: str
    body_zh: str
    indications_and_usage: str | None = None
    dosage_and_administration: str | None = None
    warnings: str | None = None
    raw_payload: dict[str, Any] | None = None
