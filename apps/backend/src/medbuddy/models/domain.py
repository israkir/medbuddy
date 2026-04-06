from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from medbuddy.llm.schemas import (
    HealthSummaryResult,
    InteractionCheckResult,
    MedicationSummaryItem,
)

__all__ = [
    "ConversationTurn",
    "DoseEventReminderPayload",
    "DrugGrounding",
    "HealthSummary",
    "Intent",
    "InteractionResult",
    "LineUserContext",
    "MedicationDraft",
    "MedicationRecord",
    "MessageKind",
]


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
    UPDATE_LOCALE = "update_locale"
    OFF_TOPIC = "off_topic"
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
    # Reminder materialization (see medications.raw_metadata["reminder"] when saved)
    first_reminder_in_minutes: int | None = None
    materialize_daily_reminders: bool = True
    reminder_horizon_days: int | None = None
    needs_horizon_confirmation: bool = False
    daily_reminder_local_hhmm: str | None = None


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
    user_locale: str


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


@dataclass
class InteractionResult:
    """Structured drug-interaction analysis returned by the agent."""

    query: str
    result: InteractionCheckResult
    grounding_sources: list[str] = field(default_factory=list)

    @property
    def has_serious_interactions(self) -> bool:
        return self.result.overall_severity in ("moderate", "severe")


@dataclass
class HealthSummary:
    """Doctor-ready patient health summary."""

    generated_at: datetime
    user_key: str
    locale: str
    medications: list[MedicationSummaryItem]
    result: HealthSummaryResult

    def as_text(self) -> str:
        """Plain-text representation for LINE/mobile chat display."""
        lines = [self.result.summary_for_doctor]
        if self.result.key_concerns:
            concerns = "\n".join(f"• {c}" for c in self.result.key_concerns)
            lines.append(f"\n重點關注:\n{concerns}")
        if self.result.reported_symptoms:
            symptoms = "、".join(self.result.reported_symptoms)
            lines.append(f"\n近期症狀: {symptoms}")
        if self.result.recommended_questions:
            qs = "\n".join(f"• {q}" for q in self.result.recommended_questions)
            lines.append(f"\n建議詢問醫師:\n{qs}")
        return "\n".join(lines)
