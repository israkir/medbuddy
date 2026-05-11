"""In-memory (mock) implementation of UserDataPort.

This module is kept as the public entry-point for backward compatibility.
The implementation is split across focused submodules:

- profile.py     — MockProfileMixin (profile + pending-state methods)
- medications.py — MockMedicationMixin (medication CRUD)
- dose_events.py — MockDoseEventMixin (dose event methods)
"""

from __future__ import annotations

from typing import Any

from medbuddy.config import Settings, get_settings
from medbuddy.models.domain import HealthIssueEventRecord, MedicationRecord
from medbuddy.protocols import UserDataPort

from .dose_events import MockDoseEventMixin
from .medications import MockMedicationMixin
from .profile import MockProfileMixin

__all__ = ["MockUserData"]


class MockUserData(MockProfileMixin, MockMedicationMixin, MockDoseEventMixin, UserDataPort):
    """In-memory implementation of UserDataPort for tests and local dev.

    Methods are organised across three mixins:
    - MockProfileMixin     — profile, vital-log and pending-state methods
    - MockMedicationMixin  — medication CRUD
    - MockDoseEventMixin   — dose event scheduling and status methods
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings
        self._users: dict[str, dict[str, Any]] = {}
        self._meds: dict[str, list[MedicationRecord]] = {}
        self._vitals: dict[str, list[HealthIssueEventRecord]] = {}
        self._doses: dict[str, dict[str, Any]] = {}
        self._dose_clarification: dict[str, dict[str, Any] | None] = {}
        self._health_conditions: dict[str, list[dict[str, Any]]] = {}

    def _reminder_settings(self) -> Settings:
        return self._settings if self._settings is not None else get_settings()

    def seed_medication(self, line_user_id: str, med: MedicationRecord) -> None:
        self._meds.setdefault(line_user_id, []).append(med)
