"""Stable keys for Supabase drug reference and personalization caches."""

from __future__ import annotations

import hashlib

from medbuddy.models.domain import Intent


def normalize_query_key(query: str) -> str:
    """Normalize user drug search text for ``drug_reference_cache.query_key``."""
    return " ".join(query.strip().casefold().split())


def personalization_fingerprint(*, intent: Intent, user_text: str, patient_context: str) -> str:
    """Include medication-list snapshot so edits invalidate cached LLM wording."""
    med_h = hashlib.sha256(patient_context.encode("utf-8")).hexdigest()[:20]
    q = normalize_query_key(user_text)
    return f"{intent.value}:{q}:{med_h}"
