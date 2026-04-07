"""OpenAI Chat Completions adapter (e.g. gpt-4.1-mini).

Implements :class:`medbuddy.protocols.ports.LLMPort` with the same behaviour as
:class:`medbuddy.integrations.gemini_llm.GeminiLLM`, using structured outputs via
``client.chat.completions.parse`` for Pydantic schemas.

Requires optional dependency: ``pip install 'medbuddy-api[llm]'`` (``openai`` package).
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
from medbuddy.llm.intent_map import map_intent_label
from medbuddy.llm.medication_draft_build import medication_draft_from_extraction
from medbuddy.llm.schemas import (
    DoseConfirmationNoteExtraction,
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
    Intent,
    InteractionResult,
    MedicationDraft,
    MedicationRecord,
)
from medbuddy.prompts.persona import get_system_persona
from medbuddy.protocols.ports import LLMPort, ProfilePatch
from medbuddy.reminders.prefs import reminder_compose_appendix

log = logging.getLogger(__name__)

try:
    from openai import OpenAI as _OpenAIClient
except ImportError:
    _OpenAIClient = None

T = TypeVar("T")


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


class OpenAILLM(LLMPort):
    def __init__(
        self,
        *,
        api_key: str,
        locale: str = "zh-TW",
        model: str = "gpt-4.1-mini",
    ) -> None:
        if _OpenAIClient is None:
            raise ImportError(
                "Install medbuddy-api with the `llm` extra: pip install 'medbuddy-api[llm]'"
            )
        self._client: Any = _OpenAIClient(api_key=api_key)
        self._model = model
        self._locale = locale

    def _generate_sync(self, model: str, prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()

    def _generate_structured_sync(self, model: str, prompt: str, schema: type[T]) -> T:
        resp = self._client.chat.completions.parse(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format=schema,
            temperature=0.1,
        )
        msg = resp.choices[0].message
        refusal = getattr(msg, "refusal", None)
        if refusal:
            raise LLMParseError(f"Model refusal for {schema.__name__}: {str(refusal)[:200]}")
        if msg.parsed is not None:
            return msg.parsed
        raw = (msg.content or "").strip()
        if not raw:
            raise LLMParseError(f"Empty response for schema {schema.__name__}")
        try:
            data = json.loads(_strip_json_fence(raw))
            return schema.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            raise LLMParseError(
                f"Could not parse {schema.__name__} from model output: {raw[:200]}"
            ) from exc

    def _classify_sync(self, user_text: str, *, recent_context: str | None = None) -> Intent:
        followup_rule = (
            "Never use off_topic for very short replies that answer the assistant about "
            "medications, adherence, reminders, or scheduling — even if the text alone looks vague "
            '(e.g. "一次", "三天", "7", "once", "yes", "ok", "每天"). '
            "Those are general_question (or a matching clinical intent), not off_topic. "
        )
        base = (
            "Classify the user message into exactly one intent: "
            "add_medication, list_medications, remove_medication, confirm_dose, "
            "explain_medication, interaction_check, log_vital, request_summary, "
            "update_profile, update_locale, off_topic, general_question. "
            "Use update_profile only when the user is sharing or correcting stored profile "
            "information (how to address them, age, emergency contact, allergies or persistent "
            "health notes on file). "
            "Do not use update_profile for medication side effects, symptoms, or one-off notes "
            "for a doctor about a specific drug or dose — use general_question or confirm_dose "
            "(if they took the medication) instead. "
            "Use update_locale when they want to change the assistant reply language "
            "(English vs Traditional Chinese), including paraphrases like "
            '"I\'d prefer English" or "請用中文回覆". '
            "Do not use update_locale when they only want a drug explanation translated. "
            + followup_rule
            + "Use off_topic only when the user is clearly changing topic to something unrelated "
            "to care — e.g. weather, sports scores, politics, coding homework, random chit-chat "
            "with no medication or health angle. If there is any health or medication angle, "
            "prefer general_question or the best matching clinical intent, not off_topic."
        )
        if recent_context:
            prompt = (
                f"{base}\n\n"
                "Recent conversation (for context only; classify only the latest user line below):\n"
                f"{recent_context}\n\n"
                f"Latest user message to classify:\n{user_text}"
            )
        else:
            prompt = f"{base}\n\nUser: {user_text}"
        try:
            parsed: IntentClassification = self._generate_structured_sync(
                self._model, prompt, IntentClassification
            )
        except LLMParseError:
            log.warning("classify_intent: structured parse failed, using general_question")
            return Intent.GENERAL_QUESTION
        return map_intent_label(parsed.intent)

    async def classify_intent(self, user_text: str, *, recent_context: str | None = None) -> Intent:
        return await asyncio.to_thread(
            self._classify_sync, user_text, recent_context=recent_context
        )

    def _extract_locale_intent_sync(self, user_text: str) -> str | None:
        prompt = (
            "Decide if the user is asking to change the assistant's reply language "
            "to English (en) or Traditional Chinese for Taiwan (zh-TW). "
            "If they are not asking to switch reply language, set target_locale to null. "
            "Do not treat requests to explain medical text in another language as a UI switch.\n\n"
            f"User: {user_text}"
        )
        try:
            parsed: LocaleIntentExtraction = self._generate_structured_sync(
                self._model, prompt, LocaleIntentExtraction
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
                self._model, prompt, ProfilePatchExtraction
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

    def _extract_dose_confirmation_note_sync(self, user_text: str, *, locale: str) -> str | None:
        _ = locale
        prompt = (
            "The user is confirming they took a scheduled medication. "
            "If they mention a side effect, symptom, or anything they want noted for this dose "
            "(for their doctor or records), put it in note; otherwise note must be null.\n\n"
            f"User: {user_text}"
        )
        try:
            parsed: DoseConfirmationNoteExtraction = self._generate_structured_sync(
                self._model, prompt, DoseConfirmationNoteExtraction
            )
        except LLMParseError:
            log.warning("extract_dose_confirmation_note: structured parse failed")
            return None
        if parsed.note is None:
            return None
        n = parsed.note.strip()
        return n if n else None

    async def extract_dose_confirmation_note(self, user_text: str, *, locale: str) -> str | None:
        return await asyncio.to_thread(
            self._extract_dose_confirmation_note_sync, user_text, locale=locale
        )

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
        return self._generate_sync(self._model, prompt)

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

    def _simplify_sync(self, raw_label: str, *, locale: str) -> str:
        loc = locale or self._locale
        prompt = f"{t('gemini.simplify_intro', locale=loc)}{raw_label}"
        return self._generate_sync(self._model, prompt)

    async def simplify_drug_text_to_patient_zh(self, raw_label: str, *, locale: str) -> str:
        return await asyncio.to_thread(self._simplify_sync, raw_label, locale=locale)

    def _extract_medication_sync(self, user_text: str, locale: str) -> MedicationDraft | None:
        loc = locale
        prompt = (
            f"{t('gemini.extract_medication_intro', locale=loc)}\n"
            f"{t('gemini.extract_medication_reminder_rules', locale=loc)}\n"
            "Return JSON only with keys: name, dosage, schedule, instructions, "
            "first_reminder_in_minutes, materialize_daily_reminders, reminder_horizon_days, "
            "needs_horizon_confirmation, daily_reminder_local_hhmm.\n"
            f"User: {user_text}"
        )
        try:
            extracted: MedicationExtraction = self._generate_structured_sync(
                self._model, prompt, MedicationExtraction
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
                self._model, prompt, RemovalResolution
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
        return self._generate_sync(self._model, prompt)

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
        return self._generate_structured_sync(self._model, prompt, InteractionCheckResult)

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

    def _generate_health_summary_sync(
        self,
        *,
        user_row: dict[str, Any],
        medications: list[MedicationRecord],
        recent_conversation: list[ConversationTurn],
        patient_context: str,
        locale: str,
    ) -> HealthSummaryResult:
        _ = user_row
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
        return self._generate_structured_sync(self._model, prompt, HealthSummaryResult)

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
                purpose="",
                notes=m.instructions,
            )
            for m in medications
        ]
        return HealthSummary(
            generated_at=datetime.now(UTC),
            user_key="",
            locale=loc,
            medications=med_items,
            result=result,
        )
