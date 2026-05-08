"""Resolve which string to use for drug-registry (OpenFDA/TFDA) lookup.

Short follow-ups like "sure" / 「好」 must not be sent as the registry query; we combine
optional tool args, the medication catalog, and recent assistant turns instead.
"""

from __future__ import annotations

import re

from medbuddy.integrations.caching_drugs import (
    _name_match_candidates,
    is_weak_grounding_query,
    normalize_query_key,
)
from medbuddy.models.domain import ConversationTurn, MedicationRecord

# Last-resort mentions in assistant text when catalog names do not match (e.g. not yet saved).
_ASSISTANT_DRUG_FALLBACKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bvitamin\s+c\b", re.I), "vitamin c"),
    (re.compile(r"\b維生素\s*c\b"), "維生素c"),
    (re.compile(r"維生素c"), "維生素c"),
)


def _medication_by_id(
    medications: list[MedicationRecord], medication_id: str
) -> MedicationRecord | None:
    mid = medication_id.strip()
    if not mid:
        return None
    for m in medications:
        if m.id == mid:
            return m
    return None


def _grounding_query_from_history(
    medications: list[MedicationRecord],
    history: list[ConversationTurn],
) -> str | None:
    """Match catalog medication names against recent assistant text; prefer last mention."""
    assistant_chunks: list[str] = []
    for turn in reversed(history):
        if turn.role != "assistant":
            continue
        c = (turn.content or "").strip()
        if c:
            assistant_chunks.append(c)
        if len(assistant_chunks) >= 3:
            break
    if not assistant_chunks:
        return None
    blob = "\n".join(assistant_chunks)
    blob_cf = blob.casefold()

    best_end: int = -1
    best_name: str | None = None
    for m in medications:
        name = (m.name or "").strip()
        if not name:
            continue
        for cand in _name_match_candidates(name):
            if not cand:
                continue
            ccf = cand.casefold()
            idx = blob_cf.rfind(ccf)
            if idx < 0:
                continue
            end = idx + len(ccf)
            if end > best_end:
                best_end = end
                best_name = name
    return best_name


def _fallback_from_assistant_blob(blob: str) -> str | None:
    for pat, label in _ASSISTANT_DRUG_FALLBACKS:
        if pat.search(blob):
            return label
    return None


def resolve_registry_lookup_query(
    *,
    user_text: str,
    history: list[ConversationTurn],
    medications: list[MedicationRecord],
    drug_query: str | None = None,
    medication_id: str | None = None,
) -> str | None:
    """Return the query string for OpenFDA/TFDA, or ``None`` to skip registry fetch.

    ``user_text`` is still the patient's actual message for compose/caching elsewhere;
    this function only decides what to send to label APIs.
    """
    tid = (drug_query or "").strip() or None
    mid_raw = (medication_id or "").strip() or None

    if mid_raw:
        med = _medication_by_id(medications, mid_raw)
        if med and (med.name or "").strip():
            return med.name.strip()

    if tid:
        tkey = normalize_query_key(tid)
        if not is_weak_grounding_query(tkey):
            return tid
        # Model gave a stopword — fall through to user text / history.

    ut = (user_text or "").strip()
    uk = normalize_query_key(ut)
    if not is_weak_grounding_query(uk):
        return ut

    hq = _grounding_query_from_history(medications, history)
    if hq:
        return hq

    assistant_chunks: list[str] = []
    for turn in reversed(history):
        if turn.role != "assistant":
            continue
        c = (turn.content or "").strip()
        if c:
            assistant_chunks.append(c)
        if len(assistant_chunks) >= 3:
            break
    if assistant_chunks:
        fb = _fallback_from_assistant_blob("\n".join(assistant_chunks))
        if fb:
            return fb

    return None
