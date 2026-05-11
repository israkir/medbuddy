"""Tests for pending JSONB schema_version field (R6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from medbuddy.models.domain import (
    DoseClarificationPending,
    MedicationAddConfirmationPending,
    MedicationDraft,
    ReminderHorizonPending,
)

_EXP = datetime.now(UTC) + timedelta(hours=1)


def test_dose_clarification_to_json_includes_version() -> None:
    p = DoseClarificationPending(
        kind="pending_taken",
        option_ids=("id-1",),
        pending_note=None,
        expires_at=_EXP,
    )
    d = p.to_json()
    assert d["schema_version"] == 1


def test_dose_clarification_from_json_accepts_version_0_rows() -> None:
    """Pre-migration rows (no schema_version) still parse (backward compat)."""
    d = {
        "kind": "pending_taken",
        "option_ids": ["id-1"],
        "pending_note": None,
        "expires_at": _EXP.isoformat(),
    }
    result = DoseClarificationPending.from_json(d)
    assert result is not None
    assert result.kind == "pending_taken"


def test_dose_clarification_from_json_rejects_future_version() -> None:
    d = {
        "schema_version": 99,
        "kind": "pending_taken",
        "option_ids": ["id-1"],
        "expires_at": _EXP.isoformat(),
    }
    assert DoseClarificationPending.from_json(d) is None


def test_reminder_horizon_roundtrip_preserves_version() -> None:
    p = ReminderHorizonPending(medication_id="m1", medication_name="Aspirin", expires_at=_EXP)
    out = ReminderHorizonPending.from_json(p.to_json())
    assert out is not None
    assert out.medication_id == "m1"


def test_reminder_horizon_rejects_future_version() -> None:
    d = {
        "schema_version": 99,
        "kind": "reminder_horizon_pending",
        "medication_id": "m1",
        "medication_name": "Aspirin",
        "expires_at": _EXP.isoformat(),
    }
    assert ReminderHorizonPending.from_json(d) is None


def test_medication_add_confirm_roundtrip_preserves_version() -> None:
    draft = MedicationDraft(name="Metformin", dosage="500mg", schedule="QD")
    p = MedicationAddConfirmationPending(draft=draft, expires_at=_EXP)
    out = MedicationAddConfirmationPending.from_json(p.to_json())
    assert out is not None
    assert out.draft.name == "Metformin"


def test_medication_add_confirm_rejects_future_version() -> None:
    d = {
        "schema_version": 99,
        "kind": "medication_add_confirm",
        "draft": {},
        "expires_at": _EXP.isoformat(),
    }
    assert MedicationAddConfirmationPending.from_json(d) is None
