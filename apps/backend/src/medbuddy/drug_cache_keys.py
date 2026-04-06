"""Stable keys for Supabase drug reference and personalization caches."""

from __future__ import annotations

import hashlib

from medbuddy.models.domain import Intent, MedicationRecord

# Must match ``drug_reference_cache.source`` values used by ``CachingDrugData``.
DRUG_REFERENCE_SOURCE_TFDA = "tfda"
DRUG_REFERENCE_SOURCE_OPENFDA = "openfda"


def normalize_query_key(query: str) -> str:
    """Normalize user drug search text for ``drug_reference_cache.query_key``."""
    return " ".join(query.strip().casefold().split())


def personalization_fingerprint(*, intent: Intent, user_text: str, patient_context: str) -> str:
    """Include medication-list snapshot so edits invalidate cached LLM wording."""
    med_h = hashlib.sha256(patient_context.encode("utf-8")).hexdigest()[:20]
    q = normalize_query_key(user_text)
    return f"{intent.value}:{q}:{med_h}"


def resolve_medication_id_for_personalization(
    medications: list[MedicationRecord], user_text: str
) -> str | None:
    """If exactly one list entry's name appears in normalized user text, return its id."""
    ut = normalize_query_key(user_text)
    if not ut:
        return None
    matches = [m.id for m in medications if (mn := normalize_query_key(m.name)) and mn in ut]
    return matches[0] if len(matches) == 1 else None
