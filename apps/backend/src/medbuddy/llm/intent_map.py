"""Map classifier string labels to :class:`~medbuddy.models.domain.Intent`."""

from __future__ import annotations

import re

from medbuddy.models.domain import Intent


def map_intent_label(label: str) -> Intent:
    raw = label.strip().lower()
    if raw == "update_locale":
        return Intent.UPDATE_PROFILE
    for intent in Intent:
        if raw == intent.value:
            return intent
    for intent in Intent:
        if re.search(rf"\b{re.escape(intent.value)}\b", raw):
            return intent
    for intent in Intent:
        if intent.value in raw:
            return intent
    return Intent.GENERAL_QUESTION
