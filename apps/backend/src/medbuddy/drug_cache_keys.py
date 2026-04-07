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


def _name_match_candidates(stored_name: str) -> list[str]:
    """Substrings to test against user text so list names with strength/branding still match.

    Examples: ``阿斯匹靈 (81mg)`` → also ``阿斯匹靈``; ``Metformin HCl`` → also ``metformin``.
    """
    n = stored_name.strip()
    if not n:
        return []
    norm = normalize_query_key(n)
    cands: list[str] = [norm]
    if "(" in n:
        base = n.split("(")[0].strip()
        if base:
            b = normalize_query_key(base)
            if b not in cands:
                cands.append(b)
    parts = norm.split()
    if len(parts) > 1:
        first = parts[0]
        if first not in cands:
            cands.append(first)
    return cands


def personalization_fingerprint(*, intent: Intent, user_text: str, patient_context: str) -> str:
    """Include medication-list snapshot so edits invalidate cached LLM wording."""
    med_h = hashlib.sha256(patient_context.encode("utf-8")).hexdigest()[:20]
    q = normalize_query_key(user_text)
    return f"{intent.value}:{q}:{med_h}"


def resolve_medication_id_for_personalization(
    medications: list[MedicationRecord],
    user_text: str,
    *,
    extra_query_text: str | None = None,
) -> str | None:
    """If exactly one list entry matches normalized user text, return its id.

    Matching uses :func:`_name_match_candidates` so stored names with parenthetical
    strength (e.g. ``阿斯匹靈 (81mg)``) or salt forms (``Metformin HCl``) still match
    short user queries (``解釋阿斯匹靈``, ``explain metformin``).

    ``extra_query_text`` is optional (e.g. redacted copy) merged into the same search blob.
    """
    chunks: list[str] = []
    for t in (user_text, extra_query_text):
        if t and (s := t.strip()):
            chunks.append(normalize_query_key(s))
    ut = " ".join(chunks).strip()
    if not ut:
        return None
    matches: list[str] = []
    for m in medications:
        if any(cand and cand in ut for cand in _name_match_candidates(m.name)):
            matches.append(m.id)
    return matches[0] if len(matches) == 1 else None
