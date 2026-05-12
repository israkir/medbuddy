"""OpenAI Chat Completions adapter (e.g. gpt-4.1-mini)."""

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
    DrugConditionConcernsExtraction,
    HealthConditionItem,
    HealthConditionsExtraction,
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
    HealthConditionRecord,
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
from openai import OpenAI as _OpenAIClient

log = logging.getLogger(__name__)

T = TypeVar("T")


class OpenAILLM(LLMPort):
    def __init__(
        self,
        *,
        api_key: str,
        locale: str = "zh-TW",
        model: str = "gpt-4.1-mini",
    ) -> None:
        self._client: Any = _OpenAIClient(api_key=api_key)
        self._model = model
        self._locale = locale

    @property
    def drug_cache_provenance_id(self) -> str:
        return self._model

    def _generate_sync(self, model: str, prompt: str) -> str:
        t0 = time.perf_counter()
        try:
            resp = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        except Exception:
            log.error(
                "OpenAI chat completion failed: model=%s prompt_chars=%d",
                model,
                len(prompt),
                exc_info=True,
            )
            raise
        out = (resp.choices[0].message.content or "").strip()
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        usage = getattr(resp, "usage", None)
        pt = getattr(usage, "prompt_tokens", None) if usage is not None else None
        ct = getattr(usage, "completion_tokens", None) if usage is not None else None
        log.info(
            "OpenAI chat completion ok: model=%s prompt_chars=%d response_chars=%d "
            "duration_ms=%.1f prompt_tokens=%r completion_tokens=%r",
            model,
            len(prompt),
            len(out),
            elapsed_ms,
            pt,
            ct,
        )
        return out

    def _generate_structured_sync(self, model: str, prompt: str, schema: type[T]) -> T:
        t0 = time.perf_counter()
        schema_name = schema.__name__
        try:
            resp = self._client.chat.completions.parse(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format=schema,
                temperature=0.1,
            )
        except Exception:
            log.error(
                "OpenAI structured completion failed: model=%s schema=%s prompt_chars=%d",
                model,
                schema_name,
                len(prompt),
                exc_info=True,
            )
            raise
        msg = resp.choices[0].message
        refusal = getattr(msg, "refusal", None)
        if refusal:
            log.warning(
                "OpenAI structured completion refusal: model=%s schema=%s prompt_chars=%d",
                model,
                schema_name,
                len(prompt),
            )
            raise LLMParseError(f"Model refusal for {schema.__name__}: {str(refusal)[:200]}")
        if msg.parsed is not None:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            usage = getattr(resp, "usage", None)
            pt = getattr(usage, "prompt_tokens", None) if usage is not None else None
            ct = getattr(usage, "completion_tokens", None) if usage is not None else None
            log.info(
                "OpenAI structured completion ok: model=%s schema=%s prompt_chars=%d "
                "duration_ms=%.1f prompt_tokens=%r completion_tokens=%r",
                model,
                schema_name,
                len(prompt),
                elapsed_ms,
                pt,
                ct,
            )
            return msg.parsed
        raw = (msg.content or "").strip()
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
        usage = getattr(resp, "usage", None)
        pt = getattr(usage, "prompt_tokens", None) if usage is not None else None
        ct = getattr(usage, "completion_tokens", None) if usage is not None else None
        log.info(
            "OpenAI structured completion ok: model=%s schema=%s prompt_chars=%d "
            "duration_ms=%.1f prompt_tokens=%r completion_tokens=%r (parsed_from_text)",
            model,
            schema_name,
            len(prompt),
            elapsed_ms,
            pt,
            ct,
        )
        return parsed

    def _interpret_turn_sync(
        self, user_text: str, *, recent_context: str | None = None
    ) -> TurnInterpretation:
        prompt = format_intent_classification_prompt(
            user_text=user_text, recent_context=recent_context
        )
        try:
            parsed: IntentClassification = self._generate_structured_sync(
                self._model, prompt, IntentClassification
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
            "Profile fields may include preferred name, age, gender, emergency contact, "
            "timezone, and reply language (en/zh-TW). "
            "Do NOT extract allergies or chronic medical conditions here — those use a separate tool. "
            "For emergency contacts: extract all contacts/channels they mention (phone/email/LINE/WhatsApp). "
            "Populate emergency_contacts as a list and mark the first one as primary when implied. "
            "Do NOT set preferred_name to a contact's first name unless they are clearly renaming themselves.\n\n"
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
        for key in (
            "preferred_name",
            "age_years",
            "gender",
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

    def _extract_health_conditions_sync(
        self, user_text: str, *, locale: str
    ) -> list[HealthConditionItem]:
        _ = locale
        prompt = (
            "Extract persistent health conditions from the user's message as structured rows. "
            "Categories: allergy (drug/food/material reactions), condition (chronic or long-term "
            "diagnosis), history (past significant events they want kept on file). "
            "Use action remove only when they clearly revoke a named condition.\n\n"
            f"User message:\n{user_text}"
        )
        try:
            parsed = self._generate_structured_sync(self._model, prompt, HealthConditionsExtraction)
        except LLMParseError:
            log.warning("extract_health_conditions: structured parse failed")
            return []
        return list(parsed.conditions)

    async def extract_health_conditions(
        self, user_text: str, *, locale: str
    ) -> list[HealthConditionItem]:
        return await asyncio.to_thread(
            self._extract_health_conditions_sync, user_text, locale=locale
        )

    def _check_drug_condition_interactions_sync(
        self,
        drug_name: str,
        conditions: list[HealthConditionRecord],
        *,
        locale: str,
    ) -> list[str]:
        if not conditions or not (drug_name or "").strip():
            return []
        lines = []
        for c in conditions:
            if not c.is_active:
                continue
            extra = f" ({c.severity})" if c.severity else ""
            lines.append(f"- [{c.category}] {c.name}{extra}")
        block = "\n".join(lines)
        prompt = (
            f"Drug (generic or brand name): {drug_name.strip()}\n"
            f"Patient conditions (active):\n{block}\n\n"
            "Return JSON matching the schema. For each concern, set severity none/low/moderate/high "
            "based on plausible clinical interaction or allergy risk. Only moderate or high should have "
            "a non-empty message — one short patient-safe sentence each, no diagnosis, urge confirming "
            "with their clinician or pharmacist. Use locale-appropriate language hints: "
            f"{locale}."
        )
        try:
            parsed = self._generate_structured_sync(
                self._model, prompt, DrugConditionConcernsExtraction
            )
        except LLMParseError:
            log.warning("check_drug_condition_interactions: structured parse failed")
            return []
        out: list[str] = []
        for item in parsed.concerns:
            if item.severity in ("moderate", "high") and (item.message or "").strip():
                out.append((item.message or "").strip())
        return out

    async def check_drug_condition_interactions(
        self,
        drug_name: str,
        conditions: list[HealthConditionRecord],
        *,
        locale: str,
    ) -> list[str]:
        return await asyncio.to_thread(
            self._check_drug_condition_interactions_sync,
            drug_name,
            conditions,
            locale=locale,
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
        prompt = f"{t('llm.simplify_intro', locale=loc)}{raw_label}"
        return self._generate_sync(self._model, prompt)

    async def simplify_drug_text_to_patient_zh(self, raw_label: str, *, locale: str) -> str:
        return await asyncio.to_thread(self._simplify_sync, raw_label, locale=locale)

    def _extract_medication_sync(
        self,
        user_text: str,
        locale: str,
        recent_context: str | None,
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
                self._model, prompt, MedicationExtraction
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
            return self._generate_structured_sync(self._model, prompt, MedicationUpdateResolution)
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
            return self._generate_structured_sync(self._model, prompt, VitalLogExtraction)
        except LLMParseError:
            log.warning("extract_vital: structured parse failed")
            return None

    async def extract_vital_log(self, user_text: str, *, locale: str) -> VitalLogExtraction | None:
        loc = locale or self._locale
        return await asyncio.to_thread(self._extract_vital_sync, user_text, loc)

    def _compose_medication_added_sync(
        self,
        *,
        patient_context: str,
        drug_grounding: str | None,
        saved: MedicationRecord,
        user_message: str,
        locale: str,
        companion_task_key: str = "medication_added_companion",
        suppress_horizon_appendix: bool = False,
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
        appendix = reminder_compose_appendix(
            saved, loc, suppress_horizon_appendix=suppress_horizon_appendix
        )
        prompt = (
            f"{lang_lock}\n\n"
            f"{persona}\n\n{task}\n\n"
            f"{t('llm.patient_background', locale=loc)}\n{patient_context}\n\n"
            f"{t('llm.reference', locale=loc)}\n{drug}\n\n"
            f"{facts}{extra}{appendix}\n\n"
            f"{t('llm.user_label', locale=loc)}{user_message}\n\n"
            f"{lang_lock}"
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
        suppress_horizon_appendix: bool = False,
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
            suppress_horizon_appendix=suppress_horizon_appendix,
        )

    async def compose_medication_added_primary(
        self,
        *,
        patient_context: str,
        drug_grounding: str | None,
        saved: MedicationRecord,
        user_message: str,
        locale: str,
        suppress_horizon_appendix: bool = False,
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
            suppress_horizon_appendix=suppress_horizon_appendix,
        )

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
        return self._generate_structured_sync(self._model, prompt, InteractionCheckResult)

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
        _ = user_row
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
        return self._generate_structured_sync(self._model, prompt, HealthSummaryResult)

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

    def _complete_chat_with_tools_sync(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str | None, list[ChatToolCall] | None]:
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception:
            log.error(
                "OpenAI chat.completions tools failed: model=%s messages=%d tools=%d",
                self._model,
                len(messages),
                len(tools),
                exc_info=True,
            )
            raise
        msg = resp.choices[0].message
        if msg.tool_calls:
            calls = [
                ChatToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=(tc.function.arguments or "").strip() or "{}",
                )
                for tc in msg.tool_calls
            ]
            return (msg.content, calls)
        out = (msg.content or "").strip()
        return (out or None, None)

    async def complete_chat_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[str | None, list[ChatToolCall] | None]:
        return await asyncio.to_thread(self._complete_chat_with_tools_sync, messages, tools)
