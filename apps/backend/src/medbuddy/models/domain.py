from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class Intent(str, Enum):
    ADD_MEDICATION = "add_medication"
    CONFIRM_DOSE = "confirm_dose"
    EXPLAIN_MEDICATION = "explain_medication"
    INTERACTION_CHECK = "interaction_check"
    LOG_VITAL = "log_vital"
    REQUEST_SUMMARY = "request_summary"
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
class MedicationRecord:
    id: str
    name: str
    dosage: str
    schedule: str
    instructions_zh: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


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
