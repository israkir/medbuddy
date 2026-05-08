"""Gemini adapter — google-genai SDK."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, TypeVar

from medbuddy.core.errors import LLMParseError
from medbuddy.core.i18n import t
from medbuddy.integrations.llm._common import language_lock, strip_json_fence
from medbuddy.llm.intent_classification_prompt import format_intent_classification_prompt
from medbuddy.llm.medication_draft_build import (
    dose_or_schedule_display,
    medication_draft_from_extraction,
)
from medbuddy.llm.turn_interpretation import (
    turn_interpretation_from_classification,
    turn_interpretation_on_parse_failure,
)
from medbuddy.llm.agent_types import ChatToolCall
from medbuddy.llm.schemas import (
    AgentOrchestratorStep,
    HealthSummaryResult,
    IntentClassification,
    InteractionCheckResult,
    LocaleIntentExtraction,
    MedicationExtraction,
    MedicationUpdateResolution,
    MedicationSummaryItem,
    ProfilePatchExtraction,
    RemovalResolution,
    VitalLogExtraction,
)
from medbuddy.models.domain import (
    ConversationTurn,
    HealthSummary,
    InteractionResult,
    MedicationDraft,
    MedicationRecord,
    TurnInterpretation,
)
from medbuddy.llm.prompts.persona import get_system_persona
from medbuddy.protocols import LLMPort, ProfilePatch
from medbuddy.reminders.prefs import reminder_compose_appendix
from medbuddy.core.locale import normalize_locale_patch
from medbuddy.core.timezone import normalize_timezone_patch
from medbuddy.application.profile.emergency_contacts import (
    normalize_emergency_contacts,
)
from google import genai as _genai
from google.genai import types as _genai_types

log = logging.getLogger(__name__)

T = TypeVar("T")


class GeminiLLM(LLMPort):
    def __init__(
        self,
        *,
        api_key: str,
        locale: str = "zh-TW",
        intent_model: str = "gemini-2.5-flash",
    ) -> None:
        self._client: Any = _genai.Client(api_key=api_key)
        self._genai_types = _genai_types
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
        t0 = time.perf_counter()
        try:
            resp = self._client.models.generate_content(model=model, contents=prompt)
        except Exception:
            log.error(
                "Gemini generate_content failed: model=%s prompt_chars=%d",
                model,
                len(prompt),
                exc_info=True,
            )
            raise
        out = (resp.text or "").strip()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        meta = getattr(resp, "usage_metadata", None)
        pt = getattr(meta, "prompt_token_count", None) if meta is not None else None
        ct = getattr(meta, "candidates_token_count", None) if meta is not None else None
        log.info(
            "Gemini generate_content ok: model=%s prompt_chars=%d response_chars=%d "
            "duration_ms=%.1f prompt_token_count=%r candidates_token_count=%r",
            model,
            len(prompt),
            len(out),
            elapsed_ms,
            pt,
            ct,
        )
        return out

    def _generate_structured_sync(self, model: str, prompt: str, schema: type[T]) -> T:
        """Generate content and parse into a Pydantic schema via response_schema."""
        t0 = time.perf_counter()
        schema_name = schema.__name__
        config = self._genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        )
        try:
            resp = self._client.models.generate_content(model=model, contents=prompt, config=config)
        except Exception:
            log.error(
                "Gemini structured generate_content failed: model=%s schema=%s prompt_chars=%d",
                model,
                schema_name,
                len(prompt),
                exc_info=True,
            )
            raise

        meta = getattr(resp, "usage_metadata", None)
        pt = getattr(meta, "prompt_token_count", None) if meta is not None else None
        ct = getattr(meta, "candidates_token_count", None) if meta is not None else None

        # Prefer the SDK's parsed object (available when response_schema is honoured)
        if hasattr(resp, "parsed") and resp.parsed is not None:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            log.info(
                "Gemini structured ok: model=%s schema=%s prompt_chars=%d duration_ms=%.1f "
                "prompt_token_count=%r candidates_token_count=%r",
                model,
                schema_name,
                len(prompt),
                elapsed_ms,
                pt,
                ct,
            )
            return resp.parsed  # type: ignore[return-value]

        # Fallback: parse the text ourselves
        raw = (resp.text or "").strip()
        if not raw:
            raise LLMParseError(f"Empty response for schema {schema.__name__}")
        try:
            data = json.loads(strip_json_fence(raw))
            parsed = schema.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            raise LLMParseError(
                f"Could not parse {schema.__name__} from model output: {raw[:200]}"
            ) from exc
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        log.info(
            "Gemini structured ok: model=%s schema=%s prompt_chars=%d duration_ms=%.1f "
            "prompt_token_count=%r candidates_token_count=%r (parsed_from_text)",
            model,
            schema_name,
            len(prompt),
            elapsed_ms,
            pt,
            ct,
        )
        return parsed

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
            "Profile fields may include preferred name, age, gender, emergency contact, health notes, "
            "timezone, and reply language (en/zh-TW). "
            "For emergency contacts: extract all contacts/channels they mention (phone/email/LINE/WhatsApp). "
            "Populate emergency_contacts as a list and mark the first one as primary when implied. "
            "Do NOT set preferred_name to a contact's first name unless they are clearly renaming themselves. "
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
        for key in (
            "preferred_name",
            "age_years",
            "gender",
            "health_notes",
            "timezone",
            "locale",
        ):
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
            elif key == "locale":
                normalized = normalize_locale_patch(val)
                if normalized is not None:
                    out[key] = normalized
            elif key == "timezone":
                normalized_tz = normalize_timezone_patch(val)
                if normalized_tz is not None:
                    out[key] = normalized_tz
            elif isinstance(val, str) and val.strip():
                out[key] = val.strip()
        contacts = normalize_emergency_contacts(data.get("emergency_contacts"))
        if contacts:
            out["emergency_contacts"] = contacts
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
        drug = drug_grounding or t("llm.no_drug_data", locale=loc)
        lang_lock = language_lock(loc)
        prompt = (
            f"{lang_lock}\n\n"
            f"{system_persona}\n\n"
            f"{t('llm.patient_background', locale=loc)}\n{patient_context}\n\n"
            f"{t('llm.reference', locale=loc)}\n{drug}\n\n"
            f"{t('llm.recent_conversation', locale=loc)}\n{hist_lines}\n\n"
            f"{t('llm.user_label', locale=loc)}{user_message}\n\n"
            f"{t('llm.reply_instruction', locale=loc)}\n\n"
            f"{lang_lock}"
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
        prompt = f"{t('llm.simplify_intro', locale=loc)}{raw_label}"
        return self._generate_sync(self._chat_model, prompt)

    async def simplify_drug_text_to_patient_zh(self, raw_label: str, *, locale: str) -> str:
        return await asyncio.to_thread(self._simplify_sync, raw_label, locale=locale)

    # ------------------------------------------------------------------
    # LLMPort — medication extraction (structured output)
    # ------------------------------------------------------------------

    def _extract_medication_sync(
        self, user_text: str, locale: str, recent_context: str | None
    ) -> MedicationDraft | None:
        loc = locale
        recent_block = ""
        if recent_context and recent_context.strip():
            recent_block = (
                f"{t('llm.extract_medication_recent_context', locale=loc)}\n"
                f"{recent_context.strip()}\n\n"
            )
        prompt = (
            f"{t('llm.extract_medication_intro', locale=loc)}\n"
            f"{recent_block}"
            f"{t('llm.extract_medication_reminder_rules', locale=loc)}\n"
            "Return JSON only with keys: name, dosage, schedule, instructions, "
            "first_reminder_in_minutes, materialize_daily_reminders, reminder_horizon_days, "
            "needs_horizon_confirmation, daily_reminder_local_hhmm, daily_reminder_local_hhmm_list.\n"
            f"{t('llm.user_label', locale=loc)} {user_text}"
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
        self,
        user_text: str,
        *,
        locale: str,
        recent_context: str | None = None,
    ) -> MedicationDraft | None:
        loc = locale or self._locale
        return await asyncio.to_thread(
            self._extract_medication_sync, user_text, loc, recent_context
        )

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
            f"{t('llm.resolve_remove_intro', locale=loc)}\n"
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

    def _resolve_update_sync(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        locale: str,
    ) -> MedicationUpdateResolution | None:
        loc = locale
        catalog = [
            {"id": m.id, "name": m.name, "dosage": m.dosage, "schedule": m.schedule}
            for m in medications
        ]
        prompt = (
            f"{t('llm.resolve_update_intro', locale=loc)}\n"
            f"Medications: {json.dumps(catalog, ensure_ascii=False)}\n"
            "Return JSON only with keys: medication_id, name, dosage, schedule, instructions, clear_instructions.\n"
            f"User: {user_text}"
        )
        try:
            return self._generate_structured_sync(
                self._chat_model, prompt, MedicationUpdateResolution
            )
        except LLMParseError:
            log.warning("resolve_update: structured parse failed")
            return None

    async def resolve_medication_update(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> MedicationUpdateResolution | None:
        loc = locale or self._locale
        return await asyncio.to_thread(self._resolve_update_sync, user_text, medications, loc)

    def _extract_vital_sync(self, user_text: str, locale: str) -> VitalLogExtraction | None:
        loc = locale
        prompt = f"{t('llm.extract_vital_intro', locale=loc)}\nUser: {user_text}"
        try:
            return self._generate_structured_sync(self._chat_model, prompt, VitalLogExtraction)
        except LLMParseError:
            log.warning("extract_vital: structured parse failed")
            return None

    async def extract_vital_log(self, user_text: str, *, locale: str) -> VitalLogExtraction | None:
        loc = locale or self._locale
        return await asyncio.to_thread(self._extract_vital_sync, user_text, loc)

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
        companion_task_key: str = "medication_added_companion",
    ) -> str:
        loc = locale or self._locale
        lang_lock = language_lock(loc)
        persona = get_system_persona(locale=loc)
        task = t(f"llm.{companion_task_key}", locale=loc)
        drug = drug_grounding or t("llm.no_drug_data", locale=loc)
        un = t("medication.unspecified", locale=loc)
        facts = t(
            "llm.added_saved_facts",
            locale=loc,
            name=saved.name,
            dosage=dose_or_schedule_display(saved.dosage, unspecified_label=un),
            schedule=dose_or_schedule_display(saved.schedule, unspecified_label=un),
        )
        extra = ""
        if saved.instructions:
            extra = "\n" + t(
                "llm.added_notes_from_user",
                locale=loc,
                text=saved.instructions,
            )
        appendix = reminder_compose_appendix(saved, loc)
        prompt = (
            f"{lang_lock}\n\n"
            f"{persona}\n\n{task}\n\n"
            f"{t('llm.patient_background', locale=loc)}\n{patient_context}\n\n"
            f"{t('llm.reference', locale=loc)}\n{drug}\n\n"
            f"{facts}{extra}{appendix}\n\n"
            f"{t('llm.user_label', locale=loc)}{user_message}\n\n"
            f"{lang_lock}"
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
            companion_task_key="medication_added_companion",
        )

    async def compose_medication_added_primary(
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
            companion_task_key="medication_added_primary_before_crosscheck",
        )

    # ------------------------------------------------------------------
    # NEW — structured drug interaction check
    # ------------------------------------------------------------------

    def _interaction_analysis_prompt(
        self,
        *,
        user_message: str,
        medications: list[MedicationRecord],
        patient_context: str,
        drug_grounding: str | None,
        locale: str,
        post_add_continuation: bool,
    ) -> str:
        loc = locale or self._locale
        lang_lock = language_lock(loc)
        un = t("medication.unspecified", locale=loc)
        med_list = "\n".join(
            f"- {m.name} {dose_or_schedule_display(m.dosage, unspecified_label=un)} "
            f"({dose_or_schedule_display(m.schedule, unspecified_label=un)})"
            for m in medications
        )
        grounding = drug_grounding or t("llm.no_drug_data", locale=loc)
        persona = get_system_persona(locale=loc)
        task_block = (
            f"{t('llm.post_add_interaction_crosscheck_task', locale=loc)}\n\n"
            f"{t('llm.interaction_structured_output_note', locale=loc)}\n\n"
            if post_add_continuation
            else (
                f"{t('llm.medication_companion_interactions', locale=loc)}\n\n"
                f"{t('llm.interaction_structured_output_note', locale=loc)}\n\n"
            )
        )
        tail = (
            ""
            if post_add_continuation
            else (
                "Analyse all potential drug-drug and drug-condition interactions for this patient. "
                "Be conservative — flag anything clinically relevant, including moderate risks. "
                "Use the patient's actual medication list. "
                "Always include a disclaimer that the patient should consult their doctor."
            )
        )
        return (
            f"{lang_lock}\n\n"
            f"{persona}\n\n"
            f"{task_block}"
            f"Patient context:\n{patient_context}\n\n"
            f"Current medications:\n{med_list}\n\n"
            f"Drug reference data:\n{grounding}\n\n"
            f"User question: {user_message}\n\n"
            f"{tail}"
            f"{lang_lock}"
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
        prompt = self._interaction_analysis_prompt(
            user_message=user_message,
            medications=medications,
            patient_context=patient_context,
            drug_grounding=drug_grounding,
            locale=loc,
            post_add_continuation=False,
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

    def _post_add_interaction_crosscheck_sync(
        self,
        *,
        user_message: str,
        medications: list[MedicationRecord],
        patient_context: str,
        drug_grounding: str | None,
        locale: str,
    ) -> InteractionCheckResult:
        loc = locale or self._locale
        prompt = self._interaction_analysis_prompt(
            user_message=user_message,
            medications=medications,
            patient_context=patient_context,
            drug_grounding=drug_grounding,
            locale=loc,
            post_add_continuation=True,
        )
        return self._generate_structured_sync(self._chat_model, prompt, InteractionCheckResult)

    async def post_add_interaction_crosscheck(
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
            self._post_add_interaction_crosscheck_sync,
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
        health_issue_events_block: str = "",
    ) -> HealthSummaryResult:
        loc = locale or self._locale
        lang_lock = language_lock(loc)
        persona = get_system_persona(locale=loc)
        un = t("medication.unspecified", locale=loc)
        med_lines = (
            "\n".join(
                f"- {m.name} {dose_or_schedule_display(m.dosage, unspecified_label=un)}, "
                f"{dose_or_schedule_display(m.schedule, unspecified_label=un)}"
                + (f" | notes: {m.instructions}" if m.instructions else "")
                for m in medications
            )
            or "None recorded."
        )

        convo_lines = (
            "\n".join(f"[{turn.role}] {turn.content}" for turn in recent_conversation[-20:])
            or "No recent conversation."
        )

        issues_section = (
            health_issue_events_block.strip()
            if health_issue_events_block.strip()
            else "None logged."
        )

        prompt = (
            f"{lang_lock}\n\n"
            f"{persona}\n\n"
            "You are generating a doctor-ready health summary for a patient.\n\n"
            f"Patient profile signals:\n{patient_context}\n\n"
            f"Current medications:\n{med_lines}\n\n"
            "Logged health-related issues (saved app timeline: routing-intent messages and vital "
            "readings; chronological):\n"
            f"{issues_section}\n\n"
            f"Recent conversation history (last 20 turns):\n{convo_lines}\n\n"
            "Generate a structured summary that:\n"
            "1. Is concise enough for a doctor to read in 30 seconds\n"
            "2. Lists all current medications with their likely therapeutic purpose\n"
            "3. Uses the logged health-related issues and conversation to extract symptoms, side "
            "effects, wellness concerns, emergencies, vitals, and adherence issues\n"
            "4. Flags the top 3-5 concerns the doctor should know\n"
            "5. Suggests questions the patient might want to ask\n"
            f"6. Is written ENTIRELY in the required language — {lang_lock}\n"
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
        health_issue_events_block: str = "",
    ) -> HealthSummary:
        loc = locale or self._locale
        result = await asyncio.to_thread(
            self._generate_health_summary_sync,
            user_row=user_row,
            medications=medications,
            recent_conversation=recent_conversation,
            patient_context=patient_context,
            locale=loc,
            health_issue_events_block=health_issue_events_block,
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

    def _gemini_complete_chat_with_tools_sync(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str | None, list[ChatToolCall] | None]:
        parts: list[str] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                parts.append(f"[system]\n{m.get('content', '')}")
            elif role == "user":
                parts.append(f"[user]\n{m.get('content', '')}")
            elif role == "assistant":
                tc = m.get("tool_calls")
                if tc:
                    parts.append(f"[assistant tool_calls] {tc}")
                else:
                    parts.append(f"[assistant]\n{m.get('content', '')}")
            elif role == "tool":
                parts.append(f"[tool result id={m.get('tool_call_id')}]\n{m.get('content', '')}")
        transcript = "\n\n".join(parts)
        catalog: list[str] = []
        for item in tools:
            fn = item.get("function")
            if isinstance(fn, dict):
                catalog.append(f"- {fn.get('name')}: {fn.get('description', '')}")
        catalog_txt = "\n".join(catalog)
        loc = self._locale
        lang_lock = language_lock(loc)
        prompt = (
            f"{lang_lock}\nYou are the MedBuddy agent planner.\n"
            f"Tools:\n{catalog_txt}\n\nConversation:\n{transcript}\n\n"
            "Return JSON matching AgentOrchestratorStep: either reply_text set (final user reply) "
            "OR tool_calls set with tool names and arguments objects — not both empty.\n"
            f"{lang_lock}"
        )
        try:
            step = self._generate_structured_sync(self._chat_model, prompt, AgentOrchestratorStep)
        except LLMParseError:
            log.warning("Gemini orchestrator step structured parse failed")
            return (None, None)
        if step.tool_calls:
            calls = [
                ChatToolCall(
                    id=f"g{i}",
                    name=tc.name,
                    arguments=json.dumps(tc.arguments) if tc.arguments else "{}",
                )
                for i, tc in enumerate(step.tool_calls)
            ]
            return (None, calls)
        if step.reply_text and step.reply_text.strip():
            return (step.reply_text.strip(), None)
        return (None, None)

    async def complete_chat_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str | None, list[ChatToolCall] | None]:
        return await asyncio.to_thread(self._gemini_complete_chat_with_tools_sync, messages, tools)
