"""Gemini adapter — requires optional dependency google-generativeai."""

from __future__ import annotations

import asyncio
import re

from medbuddy.i18n import t
from medbuddy.models.domain import ConversationTurn, Intent
from medbuddy.protocols.ports import LLMPort


class GeminiLLM(LLMPort):
    def __init__(
        self,
        *,
        api_key: str,
        locale: str = "zh-TW",
        intent_model: str = "gemini-1.5-flash",
    ) -> None:
        try:
            import google.generativeai as genai  # type: ignore[import-untyped]
        except ImportError as e:
            raise ImportError(
                "Install medbuddy-api with the `llm` extra: pip install 'medbuddy-api[llm]'"
            ) from e
        genai.configure(api_key=api_key)
        self._genai = genai
        self._intent_model = intent_model
        self._chat_model = intent_model
        self._locale = locale

    def _classify_sync(self, user_text: str) -> Intent:
        prompt = (
            "Classify the user message into exactly one intent: "
            "add_medication, confirm_dose, explain_medication, interaction_check, "
            "log_vital, request_summary, general_question. "
            "Reply with only the snake_case label.\n\n"
            f"User: {user_text}"
        )
        model = self._genai.GenerativeModel(self._intent_model)
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip().lower()
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
        model = self._genai.GenerativeModel(self._chat_model)
        resp = model.generate_content(prompt)
        return (resp.text or "").strip()

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
        model = self._genai.GenerativeModel(self._chat_model)
        resp = model.generate_content(prompt)
        return (resp.text or "").strip()

    async def simplify_drug_text_to_patient_zh(self, raw_label: str) -> str:
        return await asyncio.to_thread(self._simplify_sync, raw_label)
