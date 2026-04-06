"""Gemini adapter — requires optional dependency google-genai."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from medbuddy.i18n import t
from medbuddy.models.domain import ConversationTurn, Intent, MedicationDraft, MedicationRecord
from medbuddy.prompts.persona import get_system_persona
from medbuddy.protocols.ports import LLMPort


def _strip_json_fence(raw: str) -> str:
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
        except ImportError as e:
            raise ImportError(
                "Install medbuddy-api with the `llm` extra: pip install 'medbuddy-api[llm]'"
            ) from e
        self._client: Any = genai.Client(api_key=api_key)
        self._intent_model = intent_model
        self._chat_model = intent_model
        self._locale = locale

    def _generate_sync(self, model: str, prompt: str) -> str:
        resp = self._client.models.generate_content(model=model, contents=prompt)
        return (resp.text or "").strip()

    def _classify_sync(self, user_text: str) -> Intent:
        prompt = (
            "Classify the user message into exactly one intent: "
            "add_medication, list_medications, remove_medication, confirm_dose, "
            "explain_medication, interaction_check, log_vital, request_summary, "
            "update_profile, general_question. "
            "Use update_profile when the user is sharing or correcting personal profile "
            "information (how to address them, age, emergency contact, allergies/health notes), "
            "not asking about a specific drug. "
            "Reply with only the snake_case label.\n\n"
            f"User: {user_text}"
        )
        raw = self._generate_sync(self._intent_model, prompt).lower()
        for intent in Intent:
            if re.search(rf"\b{re.escape(intent.value)}\b", raw):
                return intent
        for intent in Intent:
            if intent.value in raw:
                return intent
        return Intent.GENERAL_QUESTION

    async def classify_intent(self, user_text: str) -> Intent:
        return await asyncio.to_thread(self._classify_sync, user_text)

    def _compose_sync(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        history: list[ConversationTurn],
        user_message: str,
    ) -> str:
        hist_lines = "\n".join(f"{turn.role}: {turn.content}" for turn in history)
        loc = self._locale
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
    ) -> str:
        return await asyncio.to_thread(
            self._compose_sync,
            system_persona=system_persona,
            patient_context=patient_context,
            drug_grounding=drug_grounding,
            history=history,
            user_message=user_message,
        )

    def _simplify_sync(self, raw_label: str) -> str:
        loc = self._locale
        prompt = f"{t('gemini.simplify_intro', locale=loc)}{raw_label}"
        return self._generate_sync(self._chat_model, prompt)

    async def simplify_drug_text_to_patient_zh(self, raw_label: str) -> str:
        return await asyncio.to_thread(self._simplify_sync, raw_label)

    def _extract_medication_sync(self, user_text: str, locale: str) -> MedicationDraft | None:
        loc = locale
        prompt = (
            f"{t('gemini.extract_medication_intro', locale=loc)}\n"
            "Return JSON only with keys: "
            "name, dosage, schedule, instructions_zh (string or null).\n"
            f"User: {user_text}"
        )
        raw = self._generate_sync(self._chat_model, prompt)
        if not raw:
            return None
        try:
            obj = json.loads(_strip_json_fence(raw))
        except json.JSONDecodeError:
            return None
        name = str(obj.get("name") or "").strip()
        if not name:
            return None
        un = t("medication.unspecified", locale=loc)
        dosage = str(obj.get("dosage") or "").strip() or un
        schedule = str(obj.get("schedule") or "").strip() or un
        ins = obj.get("instructions_zh")
        instructions = None if ins is None else (str(ins).strip() or None)
        return MedicationDraft(
            name=name,
            dosage=dosage,
            schedule=schedule,
            instructions_zh=instructions,
        )

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
        raw = self._generate_sync(self._chat_model, prompt)
        if not raw:
            return None
        try:
            obj = json.loads(_strip_json_fence(raw))
        except json.JSONDecodeError:
            return None
        mid = obj.get("medication_id")
        if mid is None:
            return None
        s = str(mid).strip()
        return s if s else None

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
        if saved.instructions_zh:
            extra = "\n" + t(
                "gemini.added_notes_from_user",
                locale=loc,
                text=saved.instructions_zh,
            )
        prompt = (
            f"{persona}\n\n{task}\n\n"
            f"{t('gemini.patient_background', locale=loc)}\n{patient_context}\n\n"
            f"{t('gemini.reference', locale=loc)}\n{drug}\n\n"
            f"{facts}{extra}\n\n"
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
