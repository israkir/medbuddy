import asyncio
from datetime import UTC, datetime
from typing import Any

from medbuddy.i18n import t
from medbuddy.llm.schemas import (
    HealthSummaryResult,
    InteractionCheckResult,
    MedicationUpdateResolution,
    MedicationSummaryItem,
    VitalLogExtraction,
)
from medbuddy.models.domain import (
    ConversationTurn,
    HealthSummary,
    Intent,
    InteractionResult,
    MedicationDraft,
    MedicationRecord,
    TurnInterpretation,
)
from medbuddy.protocols.ports import LLMPort, ProfilePatch


class MockLLM(LLMPort):
    """Test double: no keyword intent routing.

    Set ``intent=`` (and optional ``record_pending_dose_as_taken``, ``dose_adherence_note``, …)
    to mirror production structured output from ``interpret_user_turn``. Defaults:
    ``interpret_user_turn`` → ``general_question`` with adherence fields off unless
    ``intent`` is ``confirm_dose`` (then ``record_pending_dose_as_taken`` defaults true).
    ``extract_medication_draft`` / ``extract_locale_intent`` / ``resolve_medication_removal_id``
    return ``None`` unless overridden.
    """

    def __init__(
        self,
        intent: Intent | None = None,
        *,
        locale: str = "zh-TW",
        reply_template: str | None = None,
        profile_patch: ProfilePatch | None = None,
        dose_adherence_note: str | None = None,
        record_pending_dose_as_taken: bool | None = None,
        medication_draft: MedicationDraft | None = None,
        removal_medication_id: str | None = None,
        medication_update: MedicationUpdateResolution | None = None,
        vital_log: VitalLogExtraction | None = None,
        locale_intent: str | None = None,
    ) -> None:
        self._intent = intent
        self._locale = locale
        self.reply_template = reply_template or t("mocks.llm.reply_template", locale=locale)
        self._profile_patch = profile_patch
        self._dose_adherence_note = dose_adherence_note
        self._record_pending_dose_as_taken = record_pending_dose_as_taken
        self._medication_draft = medication_draft
        self._removal_medication_id = removal_medication_id
        self._medication_update = medication_update
        self._vital_log = vital_log
        self._locale_intent = locale_intent
        self.last_interpret_user_turn_input: str | None = None

    @property
    def drug_cache_provenance_id(self) -> str:
        return "mock_llm"

    async def interpret_user_turn(
        self, user_text: str, *, recent_context: str | None = None
    ) -> TurnInterpretation:
        await asyncio.sleep(0)
        self.last_interpret_user_turn_input = user_text
        _ = recent_context
        it = self._intent if self._intent is not None else Intent.GENERAL_QUESTION
        record = self._record_pending_dose_as_taken
        if record is None:
            record = it == Intent.CONFIRM_DOSE
        return TurnInterpretation(
            intent=it,
            reasoning="mock",
            record_pending_dose_as_taken=record,
            dose_adherence_note=self._dose_adherence_note,
        )

    async def extract_profile_patch(self, user_text: str, *, locale: str) -> ProfilePatch:
        await asyncio.sleep(0)
        _ = (user_text, locale)
        if self._profile_patch is not None:
            return dict(self._profile_patch)
        return {}

    async def extract_locale_intent(self, user_text: str) -> str | None:
        await asyncio.sleep(0)
        _ = user_text
        return self._locale_intent

    async def compose_reply(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        history: list[ConversationTurn],
        user_message: str,
        locale: str,
    ) -> str:
        await asyncio.sleep(0)
        _ = (system_persona, patient_context, drug_grounding, history, locale)
        return self.reply_template.format(user_message=user_message)

    async def simplify_drug_text_to_patient_zh(self, raw_label: str, *, locale: str) -> str:
        await asyncio.sleep(0)
        excerpt = raw_label[:200]
        loc = locale or self._locale
        return t("mocks.llm.simplify_prefix", locale=loc, excerpt=excerpt)

    async def extract_medication_draft(
        self, user_text: str, *, locale: str
    ) -> MedicationDraft | None:
        await asyncio.sleep(0)
        _ = (user_text, locale)
        return self._medication_draft

    async def resolve_medication_removal_id(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> str | None:
        await asyncio.sleep(0)
        _ = (user_text, medications, locale)
        return self._removal_medication_id

    async def compose_medication_added_reply(
        self,
        *,
        patient_context: str,
        drug_grounding: str | None,
        saved: MedicationRecord,
        user_message: str,
        locale: str,
    ) -> str:
        await asyncio.sleep(0)
        _ = (patient_context, user_message)
        summary = (drug_grounding or "").replace("\n", " ").strip()[:160] or t(
            "gemini.no_drug_data", locale=locale
        )
        return t(
            "mocks.llm.medication_added",
            locale=locale,
            name=saved.name,
            dosage=saved.dosage,
            schedule=saved.schedule,
            drug_summary=summary,
        )

    async def resolve_medication_update(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> MedicationUpdateResolution | None:
        await asyncio.sleep(0)
        _ = (user_text, medications, locale)
        return self._medication_update

    async def extract_vital_log(self, user_text: str, *, locale: str) -> VitalLogExtraction | None:
        await asyncio.sleep(0)
        _ = (user_text, locale)
        return self._vital_log

    async def check_interactions_structured(
        self,
        *,
        user_message: str,
        medications: list[MedicationRecord],
        patient_context: str,
        drug_grounding: str | None,
        locale: str,
    ) -> InteractionResult:
        await asyncio.sleep(0)
        med_names = [m.name for m in medications]
        result = InteractionCheckResult(
            medications_checked=med_names,
            interactions=[],
            overall_severity="none",
            summary=t("mocks.llm.reply_template", locale=locale).format(user_message=user_message),
            disclaimer=t("mocks.llm.interaction_disclaimer", locale=locale),
        )
        return InteractionResult(query=user_message, result=result)

    async def generate_health_summary(
        self,
        *,
        user_row: dict[str, Any],
        medications: list[MedicationRecord],
        recent_conversation: list[ConversationTurn],
        patient_context: str,
        locale: str,
    ) -> HealthSummary:
        await asyncio.sleep(0)
        med_items = [
            MedicationSummaryItem(
                name=m.name,
                dosage=m.dosage,
                schedule=m.schedule,
                purpose=t("mocks.llm.summary_purpose_placeholder", locale=locale),
                notes=m.instructions,
            )
            for m in medications
        ]
        med_names = [m.name for m in medications] or [t("mocks.llm.summary_no_meds", locale=locale)]
        result = HealthSummaryResult(
            summary_for_doctor=t(
                "mocks.llm.health_summary_doctor",
                locale=locale,
                med_list=", ".join(med_names),
            ),
            key_concerns=[t("mocks.llm.summary_concern_placeholder", locale=locale)],
            reported_symptoms=[],
            medication_adherence_notes=t("mocks.llm.summary_adherence_placeholder", locale=locale),
            recommended_questions=[t("mocks.llm.summary_question_placeholder", locale=locale)],
        )
        return HealthSummary(
            generated_at=datetime.now(UTC),
            user_key="",
            locale=locale,
            medications=med_items,
            result=result,
        )
