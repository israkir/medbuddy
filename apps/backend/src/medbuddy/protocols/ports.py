"""Integration boundaries — implement with mocks, HTTP clients, or future adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from medbuddy.models.domain import (
    ConversationTurn,
    DoseClarificationPending,
    DoseEventReminderPayload,
    DoseEventPendingCandidate,
    DrugGrounding,
    HealthSummary,
    InteractionResult,
    MedicationAddConfirmationPending,
    MedicationDraft,
    MedicationRecord,
    TurnInterpretation,
    VitalLogRecord,
)
from medbuddy.llm.schemas import MedicationUpdateResolution, VitalLogExtraction

# Keys: ``preferred_name``, ``age_years``, ``gender``, ``emergency_contact``,
# ``health_notes``, ``timezone``, ``locale``.
ProfilePatch = dict[str, Any]


@runtime_checkable
class LineMessagingPort(Protocol):
    """LINE allows multiple messages in a single reply — use batch for text + audio."""

    async def reply_message_batch(
        self, reply_token: str, messages: list[dict[str, Any]]
    ) -> None: ...

    async def reply_text(self, reply_token: str, text: str) -> None: ...

    async def reply_audio_url(self, reply_token: str, audio_url: str, duration_ms: int) -> None: ...

    async def push_message_batch(self, to_user_id: str, messages: list[dict[str, Any]]) -> None: ...

    async def get_message_content(self, message_id: str) -> bytes: ...


@runtime_checkable
class SpeechToTextPort(Protocol):
    async def transcribe_m4a(self, audio: bytes, *, language_code: str | None = None) -> str: ...


@runtime_checkable
class LLMPort(Protocol):
    """LLM adapters must expose a stable id for drug-cache provenance (mock vs real model id)."""

    @property
    def drug_cache_provenance_id(self) -> str:
        """Model or adapter id stored with personalized drug-cache rows (e.g. ``mock_llm``, ``gpt-4.1-mini``)."""
        ...

    async def interpret_user_turn(
        self, user_text: str, *, recent_context: str | None = None
    ) -> TurnInterpretation:
        """Structured intent + adherence slots; server dispatches tools using these fields."""
        ...

    async def extract_profile_patch(self, user_text: str, *, locale: str) -> ProfilePatch:
        """Structured profile fields from chat (LLM). Empty dict if nothing to update."""

    async def extract_locale_intent(self, user_text: str) -> str | None:
        """If the user wants English or zh-TW replies, return ``en`` or ``zh-TW``; else ``None``."""

    async def compose_reply(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        history: list[ConversationTurn],
        user_message: str,
        locale: str,
    ) -> str: ...

    async def simplify_drug_text_to_patient_zh(self, raw_label: str, *, locale: str) -> str: ...

    async def extract_medication_draft(
        self, user_text: str, *, locale: str
    ) -> MedicationDraft | None: ...

    async def resolve_medication_removal_id(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> str | None: ...

    async def resolve_medication_update(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> MedicationUpdateResolution | None: ...

    async def extract_vital_log(
        self, user_text: str, *, locale: str
    ) -> VitalLogExtraction | None: ...

    async def compose_medication_added_reply(
        self,
        *,
        patient_context: str,
        drug_grounding: str | None,
        saved: MedicationRecord,
        user_message: str,
        locale: str,
    ) -> str: ...

    async def check_interactions_structured(
        self,
        *,
        user_message: str,
        medications: list[MedicationRecord],
        patient_context: str,
        drug_grounding: str | None,
        locale: str,
    ) -> InteractionResult:
        """Structured drug-interaction analysis.  Default impl returns a text-only stub."""
        ...

    async def generate_health_summary(
        self,
        *,
        user_row: dict[str, Any],
        medications: list[MedicationRecord],
        recent_conversation: list[ConversationTurn],
        patient_context: str,
        locale: str,
    ) -> HealthSummary:
        """Generate a doctor-ready health summary for the patient."""
        ...


@runtime_checkable
class DrugDataPort(Protocol):
    async def fetch_tfda_snippet(self, query: str) -> DrugGrounding | None: ...

    async def fetch_openfda_label_snippet(self, query: str) -> DrugGrounding | None: ...


@runtime_checkable
class UserDataPort(Protocol):
    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]: ...

    async def save_onboarding_profile(
        self,
        line_user_id: str,
        *,
        preferred_name: str,
        age_years: int | None,
        gender: str | None,
        emergency_contact: str | None,
        health_notes: str | None,
        timezone: str | None = None,
        locale: str = "zh-TW",
    ) -> dict[str, Any]: ...

    async def patch_user_profile(
        self, line_user_id: str, fields: ProfilePatch
    ) -> dict[str, Any]: ...

    async def list_medications(self, line_user_id: str) -> list[MedicationRecord]: ...

    async def add_medication(
        self, line_user_id: str, draft: MedicationDraft
    ) -> MedicationRecord: ...

    async def delete_medication(self, line_user_id: str, medication_id: str) -> bool: ...

    async def patch_medication(
        self, line_user_id: str, medication_id: str, fields: dict[str, Any]
    ) -> MedicationRecord | None: ...

    async def add_vital_log(
        self,
        line_user_id: str,
        *,
        kind: str,
        display_summary: str,
        payload: dict[str, Any],
        notes: str | None = None,
    ) -> VitalLogRecord: ...

    async def sync_upcoming_dose_events(self, line_user_id: str) -> list[tuple[str, datetime]]:
        """Replace future pending dose rows and return ``(dose_event_id, scheduled_at)`` for enqueue."""
        ...

    async def get_dose_event_for_reminder(
        self, dose_event_id: str
    ) -> DoseEventReminderPayload | None: ...

    async def get_dose_event_for_nudge(
        self,
        dose_event_id: str,
        *,
        expected_nudge_count: int,
        max_nudges: int,
    ) -> DoseEventReminderPayload | None: ...

    async def try_mark_reminder_sent(self, dose_event_id: str) -> bool: ...

    async def try_increment_reminder_nudge(
        self, dose_event_id: str, *, expected_nudge_count: int
    ) -> bool: ...

    async def mark_pending_doses_taken(
        self, line_user_id: str, *, notes: str | None = None
    ) -> int: ...

    async def mark_pending_doses_missed(
        self, line_user_id: str, *, notes: str | None = None
    ) -> int: ...

    async def list_pending_dose_candidates(
        self, line_user_id: str, *, max_items: int = 5
    ) -> list[DoseEventPendingCandidate]:
        """Pending doses scheduled at or before now, newest first."""

    async def list_recent_taken_dose_candidates(
        self, line_user_id: str, *, max_items: int = 5
    ) -> list[DoseEventPendingCandidate]:
        """Recently taken doses for note attachment disambiguation, newest first."""

    async def get_dose_clarification_pending(
        self, line_user_id: str
    ) -> DoseClarificationPending | None: ...

    async def set_dose_clarification_pending(
        self, line_user_id: str, pending: DoseClarificationPending | None
    ) -> None: ...

    async def get_medication_add_confirmation_pending(
        self, line_user_id: str
    ) -> MedicationAddConfirmationPending | None: ...

    async def set_medication_add_confirmation_pending(
        self, line_user_id: str, pending: MedicationAddConfirmationPending | None
    ) -> None: ...

    async def mark_dose_events_taken(
        self,
        line_user_id: str,
        dose_event_ids: list[str],
        *,
        notes: str | None = None,
    ) -> int: ...

    async def append_note_to_dose_events(
        self,
        line_user_id: str,
        dose_event_ids: list[str],
        *,
        notes: str,
    ) -> int: ...

    async def append_note_to_recent_taken_dose(self, line_user_id: str, *, notes: str) -> int:
        """Merge ``notes`` into ``dose_events.notes`` for the most recent taken dose (see impl)."""

    async def list_dose_event_ids_for_reconcile(self, *, before_utc: datetime) -> list[str]: ...


@runtime_checkable
class ConversationStorePort(Protocol):
    async def get_recent_turns(
        self, line_user_id: str, max_turns: int
    ) -> list[ConversationTurn]: ...

    async def append_turn(self, line_user_id: str, turn: ConversationTurn) -> None: ...
