"""Health summary tool — generates doctor-ready patient summaries.

This is the primary depth feature: a structured, bilingual summary that
a patient can share with their physician.  It aggregates:
  - Current medication list with inferred therapeutic purposes
  - Logged health issue timeline (classifier intents + structured vitals) and recent chat
  - Anonymised demographic signals (age band, gender — never PII)
  - Suggested questions for the next doctor visit

The LLM path uses ``generate_health_summary()`` which returns a
``HealthSummaryResult`` Pydantic schema, ensuring the output is
always well-structured regardless of model variation.
"""

from __future__ import annotations

import logging
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.services import AppServices
from medbuddy.models.domain import MedicationRecord
from medbuddy.application.health_events.health_issue_events_format import (
    format_health_issue_events_for_summary,
)
from medbuddy.application.patient_llm_context import patient_context_for_llm

log = logging.getLogger(__name__)

# How many recent conversation turns to include for symptom extraction
_SUMMARY_HISTORY_TURNS = 30


class GenerateHealthSummaryTool:
    """Generate a doctor-ready structured health summary for the patient."""

    name = "generate_health_summary"
    description = (
        "Produce a doctor-ready health summary: current medications with purpose, "
        "recent symptoms from conversation history, adherence notes, and suggested "
        "questions for the next appointment."
    )

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_row: dict[str, Any],
        medications: list[MedicationRecord],
        locale: str,
        **_: Any,
    ) -> ToolResult:
        history = await svc.conversations.get_recent_turns(user_key, _SUMMARY_HISTORY_TURNS)
        patient_ctx = await patient_context_for_llm(
            svc, user_key, user_row, medications, locale=locale
        )
        health_events = await svc.users.list_recent_health_issue_events(
            user_key,
            limit=svc.settings.health_issue_summary_events_limit,
        )
        health_block = format_health_issue_events_for_summary(health_events)

        log.info(
            "health_summary: generating user_key=%s med_count=%d history_turns=%d health_events=%d",
            user_key,
            len(medications),
            len(history),
            len(health_events),
        )

        summary = await svc.llm.generate_health_summary(
            user_row=user_row,
            medications=medications,
            recent_conversation=history,
            patient_context=patient_ctx,
            locale=locale,
            health_issue_events_block=health_block,
        )

        log.info(
            "health_summary: done user_key=%s severity=%s",
            user_key,
            "ok",
        )
        return ToolResult(
            reply=summary.as_text(),
            structured=summary,
            metadata={"generated_at": summary.generated_at.isoformat()},
        )
