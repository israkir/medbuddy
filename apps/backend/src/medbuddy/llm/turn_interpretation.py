"""Build :class:`~medbuddy.models.domain.TurnInterpretation` from structured classification."""

from __future__ import annotations

from medbuddy.llm.intent_map import map_intent_label
from medbuddy.llm.schemas import IntentClassification
from medbuddy.models.domain import Intent, TurnInterpretation


def turn_interpretation_on_parse_failure() -> TurnInterpretation:
    return TurnInterpretation(
        intent=Intent.GENERAL_QUESTION,
        reasoning="classification parse failed",
        record_pending_dose_as_taken=False,
        dose_adherence_note=None,
    )


def turn_interpretation_from_classification(parsed: IntentClassification) -> TurnInterpretation:
    note = parsed.dose_adherence_note
    if isinstance(note, str):
        note = note.strip() or None
        if note and len(note) > 500:
            note = note[:500]
    reasoning = (parsed.reasoning or "").strip() or "—"
    return TurnInterpretation(
        intent=map_intent_label(parsed.intent),
        reasoning=reasoning,
        record_pending_dose_as_taken=bool(parsed.record_pending_dose_as_taken),
        dose_adherence_note=note,
    )
