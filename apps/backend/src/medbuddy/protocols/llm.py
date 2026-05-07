"""LLM adapter interface."""

from __future__ import annotations

from typing import Any, Protocol

from medbuddy.llm.agent_types import ChatToolCall
from medbuddy.models.domain import (
    ConversationTurn,
    HealthSummary,
    InteractionResult,
    MedicationDraft,
    MedicationRecord,
    TurnInterpretation,
)
from medbuddy.llm.schemas import MedicationUpdateResolution, VitalLogExtraction

ProfilePatch = dict[str, Any]


class LLMPort(Protocol):
    """LLM adapters must expose a stable id for drug-cache provenance (mock vs real model id)."""

    @property
    def drug_cache_provenance_id(self) -> str:
        """Model or adapter id stored with personalized drug-cache rows (e.g. ``mock_llm``, ``gpt-4.1-mini``)."""
        ...

    async def interpret_user_turn(
        self, user_text: str, *, recent_context: str | None = None
    ) -> TurnInterpretation:
        """Structured intent + adherence slots (routing hints for fast paths)."""
        ...

    async def complete_chat_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str | None, list[ChatToolCall] | None]:
        """One chat completion step with optional function tools (OpenAI-compatible messages).

        Returns ``(assistant_content, tool_calls)``. When ``tool_calls`` is non-empty,
        ``assistant_content`` may be None.
        """
        ...

    async def extract_profile_patch(self, user_text: str, *, locale: str) -> ProfilePatch:
        """Structured profile fields from chat (LLM). Empty dict if nothing to update."""

    async def extract_locale_intent(self, user_text: str) -> str | None:
        """If the user wants English or zh-TW replies, return ``en`` or ``zh-TW``; else ``None``."""

    async def compose_reply(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        history: list[ConversationTurn],
        user_message: str,
        locale: str,
    ) -> str: ...

    async def simplify_drug_text_to_patient_zh(self, raw_label: str, *, locale: str) -> str: ...

    async def extract_medication_draft(
        self, user_text: str, *, locale: str
    ) -> MedicationDraft | None: ...

    async def resolve_medication_removal_id(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> str | None: ...

    async def resolve_medication_update(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> MedicationUpdateResolution | None: ...

    async def extract_vital_log(
        self, user_text: str, *, locale: str
    ) -> VitalLogExtraction | None: ...

    async def compose_medication_added_reply(
        self,
        *,
        patient_context: str,
        drug_grounding: str | None,
        saved: MedicationRecord,
        user_message: str,
        locale: str,
    ) -> str: ...

    async def check_interactions_structured(
        self,
        *,
        user_message: str,
        medications: list[MedicationRecord],
        patient_context: str,
        drug_grounding: str | None,
        locale: str,
    ) -> InteractionResult:
        """Structured drug-interaction analysis.  Default impl returns a text-only stub."""
        ...

    async def generate_health_summary(
        self,
        *,
        user_row: dict[str, Any],
        medications: list[MedicationRecord],
        recent_conversation: list[ConversationTurn],
        patient_context: str,
        locale: str,
    ) -> HealthSummary:
        """Generate a doctor-ready health summary for the patient."""
        ...
