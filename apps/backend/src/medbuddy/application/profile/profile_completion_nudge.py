"""Append an occasional reminder when onboarding / profile fields are still missing."""

from __future__ import annotations

import hashlib
from typing import Any

from medbuddy.config import Settings
from medbuddy.core.i18n import t
from medbuddy.llm.prompts.persona import format_profile_gaps
from medbuddy.models.domain import ConversationTurn


def _stable_phase(user_key: str, modulus: int) -> int:
    if modulus <= 0:
        return 0
    digest = hashlib.sha256(user_key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def current_user_turn_index(history_before_latest_user_message: list[ConversationTurn]) -> int:
    """How many user messages this thread includes after the current turn (not yet in history)."""
    prior_users = sum(1 for turn in history_before_latest_user_message if turn.role == "user")
    return prior_users + 1


def append_profile_completion_nudge_if_due(
    *,
    settings: Settings,
    user_key: str,
    user_row: dict[str, Any],
    reply: str,
    locale: str,
    history_before_latest_user_message: list[ConversationTurn],
) -> str:
    """Append a short footer when profile gaps exist and this turn hits the nudge cadence."""
    interval = settings.profile_completion_nudge_every_n_user_turns
    if interval <= 0:
        return reply
    if not format_profile_gaps(user_row, locale=locale).strip():
        return reply
    idx = current_user_turn_index(history_before_latest_user_message)
    phase = _stable_phase(user_key, interval)
    if (idx - phase) % interval != 0:
        return reply
    footer = t("profile.completion_nudge_footer", locale=locale)
    return f"{reply}\n\n{footer}"
