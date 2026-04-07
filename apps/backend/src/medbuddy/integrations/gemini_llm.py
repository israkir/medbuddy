"""Gemini adapter — requires optional dependency google-genai.

Improvements over the original:
- ``generate_structured()`` uses Gemini's ``response_schema`` parameter
  with a Pydantic model, eliminating manual JSON-fence stripping.
- ``check_interactions_structured()`` returns a typed ``InteractionResult``
  with severity-graded ``InteractionPair`` objects.
- ``generate_health_summary()`` produces a doctor-ready ``HealthSummary``
  as a Pydantic-validated structured output.
- All sync helpers are wrapped in ``asyncio.to_thread`` (unchanged).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any, TypeVar

from medbuddy.exceptions import LLMParseError
from medbuddy.i18n import t
from medbuddy.llm.intent_classification_prompt import format_intent_classification_prompt
from medbuddy.llm.medication_draft_build import medication_draft_from_extraction
from medbuddy.llm.turn_interpretation import (
    turn_interpretation_from_classification,
    turn_interpretation_on_parse_failure,
)
from medbuddy.llm.schemas import (
    HealthSummaryResult,
    IntentClassification,
    InteractionCheckResult,
    LocaleIntentExtraction,
    MedicationExtraction,
    MedicationSummaryItem,
    ProfilePatchExtraction,
    RemovalResolution,
)
from medbuddy.models.domain import (
    ConversationTurn,
    HealthSummary,
    InteractionResult,
    MedicationDraft,
    MedicationRecord,
    TurnInterpretation,
)
from medbuddy.prompts.persona import get_system_persona
from medbuddy.protocols.ports import LLMPort, ProfilePatch
from medbuddy.reminders.prefs import reminder_compose_appendix

log = logging.getLogger(__name__)

T = TypeVar("T")


def _strip_json_fence(raw: str) -> str:
    """Fallback JSON fence stripper for models that ignore response_mime_type."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


class GeminiLLM(LLMPort):
    def __init__(
        self,
        *,
        api_key: str,
        locale: str = "zh-TW",
        intent_model: str = "gemini-2.5-flash",
    ) -> None:
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as e:
            raise ImportError(
                "Install medbuddy-api with the `llm` extra: pip install 'medbuddy-api[llm]'"
            ) from e
        self._client: Any = genai.Client(api_key=api_key)
        self._genai_types = genai_types
        self._intent_model = intent_model
        self._chat_model = intent_model
        self._locale = locale

    @property
    def drug_cache_provenance_id(self) -> str:
        return self._intent_model

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_sync(self, model: str, prompt: str) -> str:
        resp = self._client.models.generate_content(model=model, contents=prompt)
        return (resp.text or "").strip()

    def _generate_structured_sync(self, model: str, prompt: str, schema: type[T]) -> T:
        """Generate content and parse into a Pydantic schema via response_schema."""
        config = self._genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        )
        resp = self._client.models.generate_content(model=model, contents=prompt, config=config)

        # Prefer the SDK's parsed object (available when response_schema is honoured)
        if hasattr(resp, "parsed") and resp.parsed is not None:
            return resp.parsed  # type: ignore[return-value]

        # Fallback: parse the text ourselves
        raw = (resp.text or "").strip()
        if not raw:
            raise LLMParseError(f"Empty response for schema {schema.__name__}")
        try:
            data = json.loads(_strip_json_fence(raw))
            return schema.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            raise LLMParseError(
                f"Could not parse {schema.__name__} from model output: {raw[:200]}"
            ) from exc

    # ------------------------------------------------------------------
    # LLMPort — intent classification
    # ------------------------------------------------------------------

    def _interpret_turn_sync(
        self, user_text: str, *, recent_context: str | None = None
    ) -> TurnInterpretation:
        prompt = format_intent_classification_prompt(
            user_text=user_text, recent_context=recent_context
        )
        try:
            parsed: IntentClassification = self._generate_structured_sync(
                self._intent_model, prompt, IntentClassification
            )
        except LLMParseError:
            log.warning("interpret_user_turn: structured parse failed; safe fallback")
            return turn_interpretation_on_parse_failure()
        return turn_interpretation_from_classification(parsed)

    async def interpret_user_turn(
        self, user_text: str, *, recent_context: str | None = None
    ) -> TurnInterpretation:
        return await asyncio.to_thread(
            self._interpret_turn_sync, user_text, recent_context=recent_context
        )

    def _extract_locale_intent_sync(self, user_text: str) -> str | None:
        prompt = (
            "Decide if the user is asking to change the assistant reply language "
            "to English (en) or Traditional Chinese Taiwan (zh-TW). "
            "If not, set target_locale to null.\n\n"
            f"User: {user_text}"
        )
        try:
            parsed: LocaleIntentExtraction = self._generate_structured_sync(
                self._intent_model, prompt, LocaleIntentExtraction
            )
        except LLMParseError:
            log.warning("extract_locale_intent: structured parse failed")
            return None
        return parsed.target_locale

    async def extract_locale_intent(self, user_text: str) -> str | None:
        return await asyncio.to_thread(self._extract_locale_intent_sync, user_text)

    def _extract_profile_patch_sync(self, user_text: str, *, locale: str) -> ProfilePatch:
        _ = locale
        prompt = (
            "Extract profile fields the user wants to save. Only fill a field if it is clearly "
            "stated. Use null for anything not explicitly given. "
            "Do not treat one-off medication side effects or dose comments as health_notes — "
            "those belong in conversation, not the long-term profile unless they say they want "
            "it saved on their profile or as allergies.\n\n"
            f"User message:\n{user_text}"
        )
        try:
            extracted: ProfilePatchExtraction = self._generate_structured_sync(
                self._chat_model, prompt, ProfilePatchExtraction
            )
        except LLMParseError:
            log.warning("extract_profile_patch: structured parse failed")
            return {}
        data = extracted.model_dump(exclude_none=True)
        out: ProfilePatch = {}
        for key in ("preferred_name", "age_years", "gender", "emergency_contact", "health_notes"):
            if key not in data:
                continue
            val = data[key]
            if key == "age_years":
                if isinstance(val, int) and 0 <= val <= 120:
                    out[key] = val
                elif isinstance(val, float) and val.is_integer():
                    ai = int(val)
                    if 0 <= ai <= 120:
                        out[key] = ai
            elif key == "gender" and isinstance(val, str):
                g = val.strip().lower().replace("-", "_")
                if g == "nonbinary":
                    g = "non_binary"
                allowed = {"female", "male", "non_binary", "prefer_not_say", "other"}
                if g in allowed:
                    out[key] = g
            elif isinstance(val, str) and val.strip():
                out[key] = val.strip()
        return out

    async def extract_profile_patch(self, user_text: str, *, locale: str) -> ProfilePatch:
        return await asyncio.to_thread(self._extract_profile_patch_sync, user_text, locale=locale)

    # ------------------------------------------------------------------
    # LLMPort — reply composition
    # ------------------------------------------------------------------

    def _compose_sync(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        history: list[ConversationTurn],
        user_message: str,
        locale: str,
    ) -> str:
        hist_lines = "\n".join(f"{turn.role}: {turn.content}" for turn in history)
        loc = locale or self._locale
        drug = drug_grounding or t("gemini.no_drug_data", locale=loc)
        prompt = (
            f"{system_persona}\n\n"
            f"{t('gemini.patient_background', locale=loc)}\n{patient_context}\n\n"
            f"{t('gemini.reference', locale=loc)}\n{drug}\n\n"
            f"{t('gemini.recent_conversation', locale=loc)}\n{hist_lines}\n\n"
            f"{t('gemini.user_label', locale=loc)}{user_message}\n\n"
            f"{t('gemini.reply_instruction', locale=loc)}"
        )
        return self._generate_sync(self._chat_model, prompt)

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
        return await asyncio.to_thread(
            self._compose_sync,
            system_persona=system_persona,
            patient_context=patient_context,
            drug_grounding=drug_grounding,
            history=history,
            user_message=user_message,
            locale=locale,
        )

    # ------------------------------------------------------------------
    # LLMPort — drug text simplification
    # ------------------------------------------------------------------

    def _simplify_sync(self, raw_label: str, *, locale: str) -> str:
        loc = locale or self._locale
        prompt = f"{t('gemini.simplify_intro', locale=loc)}{raw_label}"
        return self._generate_sync(self._chat_model, prompt)

    async def simplify_drug_text_to_patient_zh(self, raw_label: str, *, locale: str) -> str:
        return await asyncio.to_thread(self._simplify_sync, raw_label, locale=locale)

    # ------------------------------------------------------------------
    # LLMPort — medication extraction (structured output)
    # ------------------------------------------------------------------

    def _extract_medication_sync(self, user_text: str, locale: str) -> MedicationDraft | None:
        loc = locale
        prompt = (
            f"{t('gemini.extract_medication_intro', locale=loc)}\n"
            f"{t('gemini.extract_medication_reminder_rules', locale=loc)}\n"
            "Return JSON only with keys: name, dosage, schedule, instructions, "
            "first_reminder_in_minutes, materialize_daily_reminders, reminder_horizon_days, "
            "needs_horizon_confirmation, daily_reminder_local_hhmm, daily_reminder_local_hhmm_list.\n"
            f"User: {user_text}"
        )
        try:
            extracted: MedicationExtraction = self._generate_structured_sync(
                self._chat_model, prompt, MedicationExtraction
            )
        except LLMParseError:
            log.warning("extract_medication: structured parse failed, skipping")
            return None

        un = t("medication.unspecified", locale=loc)
        return medication_draft_from_extraction(extracted, unspecified=un)

    async def extract_medication_draft(
        self, user_text: str, *, locale: str
    ) -> MedicationDraft | None:
        loc = locale or self._locale
        return await asyncio.to_thread(self._extract_medication_sync, user_text, loc)

    # ------------------------------------------------------------------
    # LLMPort — medication removal resolution (structured output)
    # ------------------------------------------------------------------

    def _resolve_remove_sync(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        locale: str,
    ) -> str | None:
        loc = locale
        catalog = [{"id": m.id, "name": m.name} for m in medications]
        prompt = (
            f"{t('gemini.resolve_remove_intro', locale=loc)}\n"
            f"Medications: {json.dumps(catalog, ensure_ascii=False)}\n"
            'Return JSON only: {"medication_id":"<uuid>" or null}\n'
            f"User: {user_text}"
        )
        try:
            resolved: RemovalResolution = self._generate_structured_sync(
                self._chat_model, prompt, RemovalResolution
            )
        except LLMParseError:
            log.warning("resolve_remove: structured parse failed")
            return None

        mid = resolved.medication_id
        return mid.strip() if mid and mid.strip() else None

    async def resolve_medication_removal_id(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> str | None:
        loc = locale or self._locale
        return await asyncio.to_thread(self._resolve_remove_sync, user_text, medications, loc)

    # ------------------------------------------------------------------
    # LLMPort — medication-added reply
    # ------------------------------------------------------------------

    def _compose_medication_added_sync(
        self,
        *,
        patient_context: str,
        drug_grounding: str | None,
        saved: MedicationRecord,
        user_message: str,
        locale: str,
    ) -> str:
        loc = locale or self._locale
        persona = get_system_persona(locale=loc)
        task = t("gemini.medication_added_companion", locale=loc)
        drug = drug_grounding or t("gemini.no_drug_data", locale=loc)
        facts = t(
            "gemini.added_saved_facts",
            locale=loc,
            name=saved.name,
            dosage=saved.dosage,
            schedule=saved.schedule,
        )
        extra = ""
        if saved.instructions:
            extra = "\n" + t(
                "gemini.added_notes_from_user",
                locale=loc,
                text=saved.instructions,
            )
        appendix = reminder_compose_appendix(saved, loc)
        prompt = (
            f"{persona}\n\n{task}\n\n"
            f"{t('gemini.patient_background', locale=loc)}\n{patient_context}\n\n"
            f"{t('gemini.reference', locale=loc)}\n{drug}\n\n"
            f"{facts}{extra}{appendix}\n\n"
            f"{t('gemini.user_label', locale=loc)}{user_message}"
        )
        return self._generate_sync(self._chat_model, prompt)

    async def compose_medication_added_reply(
        self,
        *,
        patient_context: str,
        drug_grounding: str | None,
        saved: MedicationRecord,
        user_message: str,
        locale: str,
    ) -> str:
        loc = locale or self._locale
        return await asyncio.to_thread(
            self._compose_medication_added_sync,
            patient_context=patient_context,
            drug_grounding=drug_grounding,
            saved=saved,
            user_message=user_message,
            locale=loc,
        )

    # ------------------------------------------------------------------
    # NEW — structured drug interaction check
    # ------------------------------------------------------------------

    def _check_interactions_sync(
        self,
        *,
        user_message: str,
        medications: list[MedicationRecord],
        patient_context: str,
        drug_grounding: str | None,
        locale: str,
    ) -> InteractionCheckResult:
        loc = locale or self._locale
        med_list = "\n".join(f"- {m.name} {m.dosage} ({m.schedule})" for m in medications)
        grounding = drug_grounding or t("gemini.no_drug_data", locale=loc)
        persona = get_system_persona(locale=loc)
        prompt = (
            f"{persona}\n\n"
            f"{t('gemini.medication_companion_interactions', locale=loc)}\n\n"
            f"{t('gemini.interaction_structured_output_note', locale=loc)}\n\n"
            f"Patient context:\n{patient_context}\n\n"
            f"Current medications:\n{med_list}\n\n"
            f"Drug reference data:\n{grounding}\n\n"
            f"User question: {user_message}\n\n"
            "Analyse all potential drug-drug and drug-condition interactions for this patient. "
            "Be conservative — flag anything clinically relevant, including moderate risks. "
            "Use the patient's actual medication list. "
            "Always include a disclaimer that the patient should consult their doctor."
        )
        return self._generate_structured_sync(self._chat_model, prompt, InteractionCheckResult)

    async def check_interactions_structured(
        self,
        *,
        user_message: str,
        medications: list[MedicationRecord],
        patient_context: str,
        drug_grounding: str | None,
        locale: str,
    ) -> InteractionResult:
        loc = locale or self._locale
        result = await asyncio.to_thread(
            self._check_interactions_sync,
            user_message=user_message,
            medications=medications,
            patient_context=patient_context,
            drug_grounding=drug_grounding,
            locale=loc,
        )
        return InteractionResult(query=user_message, result=result)

    # ------------------------------------------------------------------
    # NEW — doctor-ready health summary
    # ------------------------------------------------------------------

    def _generate_health_summary_sync(
        self,
        *,
        user_row: dict[str, Any],
        medications: list[MedicationRecord],
        recent_conversation: list[ConversationTurn],
        patient_context: str,
        locale: str,
    ) -> HealthSummaryResult:
        loc = locale or self._locale
        persona = get_system_persona(locale=loc)

        med_lines = (
            "\n".join(
                f"- {m.name} {m.dosage}, {m.schedule}"
                + (f" | notes: {m.instructions}" if m.instructions else "")
                for m in medications
            )
            or "None recorded."
        )

        convo_lines = (
            "\n".join(f"[{turn.role}] {turn.content}" for turn in recent_conversation[-20:])
            or "No recent conversation."
        )

        prompt = (
            f"{persona}\n\n"
            "You are generating a doctor-ready health summary for a patient.\n\n"
            f"Patient profile signals:\n{patient_context}\n\n"
            f"Current medications:\n{med_lines}\n\n"
            f"Recent conversation history (last 20 turns):\n{convo_lines}\n\n"
            "Generate a structured summary that:\n"
            "1. Is concise enough for a doctor to read in 30 seconds\n"
            "2. Lists all current medications with their likely therapeutic purpose\n"
            "3. Extracts any symptoms, side effects, or adherence issues mentioned recently\n"
            "4. Flags the top 3-5 concerns the doctor should know\n"
            "5. Suggests questions the patient might want to ask\n"
            "6. Is written in the patient's language preference\n"
            "Do NOT include any PII (real names, phone numbers, ID numbers)."
        )
        return self._generate_structured_sync(self._chat_model, prompt, HealthSummaryResult)

    async def generate_health_summary(
        self,
        *,
        user_row: dict[str, Any],
        medications: list[MedicationRecord],
        recent_conversation: list[ConversationTurn],
        patient_context: str,
        locale: str,
    ) -> HealthSummary:
        loc = locale or self._locale
        result = await asyncio.to_thread(
            self._generate_health_summary_sync,
            user_row=user_row,
            medications=medications,
            recent_conversation=recent_conversation,
            patient_context=patient_context,
            locale=loc,
        )
        med_items = [
            MedicationSummaryItem(
                name=m.name,
                dosage=m.dosage,
                schedule=m.schedule,
                purpose="",  # populated by LLM in result.summary_for_doctor
                notes=m.instructions,
            )
            for m in medications
        ]
        return HealthSummary(
            generated_at=datetime.now(UTC),
            user_key="",  # set by caller
            locale=loc,
            medications=med_items,
            result=result,
        )
