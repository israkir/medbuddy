"""Supabase (Postgres) implementations of user and conversation persistence.

This module is kept as the public entry-point for backward compatibility.
The implementation is split across focused submodules:

- supabase_client.py      — create_supabase_client()
- supabase_profile.py     — SupabaseProfileMixin (profile + pending-state methods)
- supabase_medications.py — SupabaseMedicationMixin (medication CRUD)
- supabase_dose_events.py — SupabaseDoseEventMixin (dose event methods)
- supabase_conversations.py — SupabaseConversationStore
"""

from __future__ import annotations

from typing import Any

from medbuddy.config import Settings
from medbuddy.protocols import UserDataPort

from .supabase_client import create_supabase_client
from .supabase_conversations import SupabaseConversationStore
from .supabase_dose_events import SupabaseDoseEventMixin
from .supabase_medications import SupabaseMedicationMixin
from .supabase_profile import SupabaseProfileMixin

__all__ = [
    "SupabaseConversationStore",
    "SupabaseUserData",
    "create_supabase_client",
]


class SupabaseUserData(
    SupabaseProfileMixin, SupabaseMedicationMixin, SupabaseDoseEventMixin, UserDataPort
):
    """Users + medications backed by Supabase Postgres.

    Methods are organised across three mixins:
    - SupabaseProfileMixin     — profile, vital-log and pending-state methods
    - SupabaseMedicationMixin  — medication CRUD
    - SupabaseDoseEventMixin   — dose event scheduling and status methods
    """

    def __init__(self, client: Any, settings: Settings) -> None:
        self._client = client
        self._settings = settings
