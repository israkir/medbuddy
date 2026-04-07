from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from medbuddy.llm.schemas import (
    HealthSummaryResult,
    InteractionCheckResult,
    MedicationSummaryItem,
)

__all__ = [
    "ConversationTurn",
    "DoseClarificationPending",
    "MedicationAddConfirmationPending",
    "DoseEventReminderPayload",
    "DoseEventPendingCandidate",
    "DrugGrounding",
    "HealthSummary",
    "Intent",
    "InteractionResult",
    "LineUserContext",
    "MedicationDraft",
    "MedicationRecord",
    "MessageKind",
    "TurnInterpretation",
    "VitalLogRecord",
]


class Intent(str, Enum):
    ADD_MEDICATION = "add_medication"
    UPDATE_MEDICATION = "update_medication"
    LIST_MEDICATIONS = "list_medications"
    REMOVE_MEDICATION = "remove_medication"
    CONFIRM_DOSE = "confirm_dose"
    REPORT_MISSED_DOSE = "report_missed_dose"
    EXPLAIN_MEDICATION = "explain_medication"
    INTERACTION_CHECK = "interaction_check"
    LOG_VITAL = "log_vital"
    REQUEST_SUMMARY = "request_summary"
    UPDATE_PROFILE = "update_profile"
    OFF_TOPIC = "off_topic"
    GENERAL_QUESTION = "general_question"


@dataclass(frozen=True)
class TurnInterpretation:
    """Single structured read of a user line: intent plus adherence slots for mechanical dispatch."""

    intent: Intent
    reasoning: str
    record_pending_dose_as_taken: bool
    dose_adherence_note: str | None


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
    instructions: str | None = None
    # Reminder materialization (see medications.raw_metadata["reminder"] when saved)
    first_reminder_in_minutes: int | None = None
    materialize_daily_reminders: bool = True
    reminder_horizon_days: int | None = None
    needs_horizon_confirmation: bool = False
    daily_reminder_local_hhmm: str | None = None
    daily_reminder_local_hhmm_list: list[str] | None = None


@dataclass
class MedicationRecord:
    id: str
    name: str
    dosage: str
    schedule: str
    instructions: str | None = None
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VitalLogRecord:
    """One saved vital-sign row for a patient."""

    id: str
    kind: str
    display_summary: str
    payload: dict[str, Any]
    notes: str | None
    recorded_at: datetime


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
    is_nudge: bool = False


@dataclass(frozen=True)
class DoseEventPendingCandidate:
    """Minimal pending-dose row for adherence disambiguation prompts."""

    dose_event_id: str
    medication_name: str
    dosage: str
    schedule: str
    scheduled_at: datetime


DoseClarificationKind = Literal["pending_taken", "note_on_taken"]


@dataclass(frozen=True)
class DoseClarificationPending:
    """Server-side state for deterministic follow-up after a dose disambiguation prompt."""

    kind: DoseClarificationKind
    option_ids: tuple[str, ...]
    pending_note: str | None
    expires_at: datetime

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "option_ids": list(self.option_ids),
            "pending_note": self.pending_note,
            "expires_at": self.expires_at.replace(tzinfo=UTC).isoformat(),
        }

    @classmethod
    def from_json(cls, data: Any) -> DoseClarificationPending | None:
        if not isinstance(data, dict):
            return None
        kind = data.get("kind")
        if kind not in ("pending_taken", "note_on_taken"):
            return None
        raw_ids = data.get("option_ids")
        if not isinstance(raw_ids, list) or not raw_ids:
            return None
        option_ids = tuple(str(x).strip() for x in raw_ids if str(x).strip())
        if len(option_ids) != len(raw_ids):
            return None
        exp_raw = data.get("expires_at")
        if not isinstance(exp_raw, str):
            return None
        try:
            exp = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        pn = data.get("pending_note")
        pending_note: str | None
        if pn is None:
            pending_note = None
        elif isinstance(pn, str):
            pending_note = pn.strip() or None
        else:
            return None
        return cls(
            kind=kind,
            option_ids=option_ids,
            pending_note=pending_note,
            expires_at=exp,
        )


MEDICATION_ADD_CONFIRM_KIND = "medication_add_confirm"


def _medication_draft_to_json(draft: MedicationDraft) -> dict[str, Any]:
    dl = draft.daily_reminder_local_hhmm_list
    return {
        "name": draft.name,
        "dosage": draft.dosage,
        "schedule": draft.schedule,
        "instructions": draft.instructions,
        "first_reminder_in_minutes": draft.first_reminder_in_minutes,
        "materialize_daily_reminders": draft.materialize_daily_reminders,
        "reminder_horizon_days": draft.reminder_horizon_days,
        "needs_horizon_confirmation": draft.needs_horizon_confirmation,
        "daily_reminder_local_hhmm": draft.daily_reminder_local_hhmm,
        "daily_reminder_local_hhmm_list": list(dl) if dl else None,
    }


def _medication_draft_from_dict(data: Any) -> MedicationDraft | None:
    if not isinstance(data, dict):
        return None
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    dosage = str(data.get("dosage") or "").strip()
    schedule = str(data.get("schedule") or "").strip()
    if not dosage or not schedule:
        return None
    ins = data.get("instructions")
    instructions: str | None
    if ins is None:
        instructions = None
    elif isinstance(ins, str):
        instructions = ins.strip() or None
    else:
        return None
    fm = data.get("first_reminder_in_minutes")
    first_reminder_in_minutes: int | None
    if fm is None:
        first_reminder_in_minutes = None
    elif isinstance(fm, int):
        first_reminder_in_minutes = fm if fm > 0 else None
    elif isinstance(fm, float) and fm.is_integer():
        iv = int(fm)
        first_reminder_in_minutes = iv if iv > 0 else None
    else:
        return None
    mat = data.get("materialize_daily_reminders")
    if not isinstance(mat, bool):
        mat = True
    rh = data.get("reminder_horizon_days")
    reminder_horizon_days: int | None
    if rh is None:
        reminder_horizon_days = None
    elif isinstance(rh, int):
        reminder_horizon_days = max(1, min(90, rh))
    else:
        return None
    nhc = data.get("needs_horizon_confirmation")
    needs_horizon_confirmation = bool(nhc) if isinstance(nhc, bool) else False
    d1 = data.get("daily_reminder_local_hhmm")
    daily_reminder_local_hhmm: str | None
    if d1 is None:
        daily_reminder_local_hhmm = None
    elif isinstance(d1, str):
        daily_reminder_local_hhmm = d1.strip() or None
    else:
        return None
    raw_list = data.get("daily_reminder_local_hhmm_list")
    daily_reminder_local_hhmm_list: list[str] | None = None
    if raw_list is not None:
        if not isinstance(raw_list, list):
            return None
        daily_reminder_local_hhmm_list = [
            str(x).strip() for x in raw_list if str(x).strip()
        ] or None
    return MedicationDraft(
        name=name,
        dosage=dosage,
        schedule=schedule,
        instructions=instructions,
        first_reminder_in_minutes=first_reminder_in_minutes,
        materialize_daily_reminders=mat,
        reminder_horizon_days=reminder_horizon_days,
        needs_horizon_confirmation=needs_horizon_confirmation,
        daily_reminder_local_hhmm=daily_reminder_local_hhmm,
        daily_reminder_local_hhmm_list=daily_reminder_local_hhmm_list,
    )


@dataclass(frozen=True)
class MedicationAddConfirmationPending:
    """Pending user OK before saving a medication with missing dose, schedule, or notes."""

    draft: MedicationDraft
    expires_at: datetime

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": MEDICATION_ADD_CONFIRM_KIND,
            "draft": _medication_draft_to_json(self.draft),
            "expires_at": self.expires_at.replace(tzinfo=UTC).isoformat(),
        }

    @classmethod
    def from_json(cls, data: Any) -> MedicationAddConfirmationPending | None:
        if not isinstance(data, dict):
            return None
        if data.get("kind") != MEDICATION_ADD_CONFIRM_KIND:
            return None
        exp_raw = data.get("expires_at")
        if not isinstance(exp_raw, str):
            return None
        try:
            exp = datetime.fromisoformat(exp_raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        draft = _medication_draft_from_dict(data.get("draft"))
        if draft is None:
            return None
        return cls(draft=draft, expires_at=exp)


def parse_pending_agent_clarification(
    raw: Any,
) -> DoseClarificationPending | MedicationAddConfirmationPending | None:
    """Decode ``patients.pending_agent_clarification`` JSON (dose choice or med-add confirm)."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get("kind")
    if kind == MEDICATION_ADD_CONFIRM_KIND:
        return MedicationAddConfirmationPending.from_json(raw)
    return DoseClarificationPending.from_json(raw)


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
