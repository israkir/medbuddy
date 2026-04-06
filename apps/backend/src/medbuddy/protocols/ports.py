"""Integration boundaries — implement with mocks, HTTP clients, or future adapters."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from medbuddy.models.domain import (
    ConversationTurn,
    DrugGrounding,
    Intent,
    MedicationDraft,
    MedicationRecord,
)


@runtime_checkable
class LineMessagingPort(Protocol):
    """LINE allows multiple messages in a single reply — use batch for text + audio."""

    async def reply_message_batch(
        self, reply_token: str, messages: list[dict[str, Any]]
    ) -> None: ...

    async def reply_text(self, reply_token: str, text: str) -> None: ...

    async def reply_audio_url(self, reply_token: str, audio_url: str, duration_ms: int) -> None: ...

    async def get_message_content(self, message_id: str) -> bytes: ...


@runtime_checkable
class SpeechToTextPort(Protocol):
    async def transcribe_m4a(self, audio: bytes) -> str: ...


@runtime_checkable
class TextToSpeechPort(Protocol):
    async def synthesize_to_m4a_url(self, text: str, base_public_url: str) -> tuple[str, int]: ...


@runtime_checkable
class LLMPort(Protocol):
    async def classify_intent(self, user_text: str) -> Intent: ...

    async def compose_reply(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        history: list[ConversationTurn],
        user_message: str,
    ) -> str: ...

    async def simplify_drug_text_to_patient_zh(self, raw_label: str) -> str: ...

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

    async def compose_medication_added_reply(
        self,
        *,
        patient_context: str,
        drug_grounding: str | None,
        saved: MedicationRecord,
        user_message: str,
        locale: str,
    ) -> str: ...


@runtime_checkable
class DrugDataPort(Protocol):
    async def fetch_tfda_snippet(self, query: str) -> DrugGrounding | None: ...

    async def fetch_openfda_label_snippet(self, query: str) -> DrugGrounding | None: ...


@runtime_checkable
class ObjectStoragePort(Protocol):
    async def upload_temp_audio(
        self,
        *,
        data: bytes,
        content_type: str,
        suffix: str,
    ) -> str: ...

    async def delete_object(self, public_url: str) -> None: ...


@runtime_checkable
class UserDataPort(Protocol):
    async def get_or_create_user(self, line_user_id: str) -> dict[str, Any]: ...

    async def list_medications(self, line_user_id: str) -> list[MedicationRecord]: ...

    async def add_medication(
        self, line_user_id: str, draft: MedicationDraft
    ) -> MedicationRecord: ...

    async def delete_medication(self, line_user_id: str, medication_id: str) -> bool: ...


@runtime_checkable
class ConversationStorePort(Protocol):
    async def get_recent_turns(
        self, line_user_id: str, max_turns: int
    ) -> list[ConversationTurn]: ...

    async def append_turn(self, line_user_id: str, turn: ConversationTurn) -> None: ...
