"""User data interface — profiles, medications, dose events, and pending-state slots."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, Sequence

from medbuddy.models.domain import (
    DoseClarificationPending,
    DoseEventPendingCandidate,
    DoseEventReminderPayload,
    HealthIssueEventRecord,
    MedicationAddConfirmationPending,
    MedicationDraft,
    MedicationRecord,
    ReminderHorizonPending,
)

ProfilePatch = dict[str, Any]


class UserDataPort(Protocol):
    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]: ...

    async def save_onboarding_profile(
        self,
        line_user_id: str,
        *,
        preferred_name: str,
        age_years: int | None,
        gender: str | None,
        emergency_contacts: list[dict[str, Any]] | None,
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

    async def delete_all_medications(self, line_user_id: str) -> int:
        """Remove every medication row for the patient; return count deleted."""

    async def bulk_disable_reminders(
        self,
        line_user_id: str,
        *,
        medication_id: str | None = None,
    ) -> int:
        """Turn off daily reminder materialization for all meds or one medication; return rows patched."""

    async def merge_medication_raw_metadata(
        self,
        line_user_id: str,
        medication_id: str,
        reminder_patch: dict[str, Any],
    ) -> MedicationRecord | None:
        """Deep-merge keys under ``raw_metadata['reminder']`` and persist."""

    async def record_health_issue_event(
        self,
        line_user_id: str,
        *,
        routing_intent: str,
        user_message: str,
        locale: str,
    ) -> HealthIssueEventRecord:
        """Persist a classifier-routed health turn (symptoms, wellness, adherence, …)."""

    async def list_recent_health_issue_events(
        self,
        line_user_id: str,
        *,
        limit: int = 20,
        routing_intents: Sequence[str] | None = None,
    ) -> list[HealthIssueEventRecord]:
        """Most recent rows (newest first). When ``routing_intents`` is set, restrict to those intents."""

    async def list_recent_vital_logs(
        self, line_user_id: str, *, limit: int = 20
    ) -> list[HealthIssueEventRecord]:
        """Most recent structured vital rows (``routing_intent`` = ``log_vital``)."""

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
        user_message: str | None = None,
        locale: str | None = None,
    ) -> HealthIssueEventRecord:
        """Persist a structured vital reading (``routing_intent`` = ``log_vital``)."""

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

    async def list_upcoming_dose_events(
        self,
        line_user_id: str,
        *,
        from_utc: datetime,
        until_utc_exclusive: datetime,
        max_items: int = 96,
    ) -> list[DoseEventPendingCandidate]:
        """Pending (not taken, not missed) doses with ``from_utc <= scheduled_at < until_utc_exclusive``."""

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

    async def get_reminder_horizon_pending(
        self, line_user_id: str
    ) -> ReminderHorizonPending | None: ...

    async def set_reminder_horizon_pending(
        self, line_user_id: str, pending: ReminderHorizonPending | None
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
