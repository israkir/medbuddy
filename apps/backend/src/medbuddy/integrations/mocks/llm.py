import asyncio

from medbuddy.i18n import t
from medbuddy.models.domain import ConversationTurn, Intent
from medbuddy.protocols.ports import LLMPort


class MockLLM(LLMPort):
    """Deterministic intent + templated replies for CI."""

    def __init__(
        self,
        intent: Intent | None = None,
        *,
        locale: str = "zh-TW",
        reply_template: str | None = None,
    ) -> None:
        self._intent = intent
        self._locale = locale
        self.reply_template = reply_template or t("mocks.llm.reply_template", locale=locale)
        self.last_classify_input: str | None = None

    async def classify_intent(self, user_text: str) -> Intent:
        await asyncio.sleep(0)
        self.last_classify_input = user_text
        if self._intent is not None:
            return self._intent
        lowered = user_text.lower()
        if "藥" in user_text and ("加" in user_text or "新增" in user_text):
            return Intent.ADD_MEDICATION
        if "交互" in user_text or "一起" in user_text:
            return Intent.INTERACTION_CHECK
        if "摘要" in user_text or "總結" in user_text:
            return Intent.REQUEST_SUMMARY
        if "解釋" in user_text or "說明" in user_text:
            return Intent.EXPLAIN_MEDICATION
        if "dose" in lowered or "劑量" in user_text:
            return Intent.CONFIRM_DOSE
        if "血壓" in user_text or "血糖" in user_text:
            return Intent.LOG_VITAL
        return Intent.GENERAL_QUESTION

    async def compose_reply(
        self,
        *,
        system_persona: str,
        patient_context: str,
        drug_grounding: str | None,
        history: list[ConversationTurn],
        user_message: str,
    ) -> str:
        await asyncio.sleep(0)
        _ = (system_persona, patient_context, drug_grounding, history)
        return self.reply_template.format(user_message=user_message)

    async def simplify_drug_text_to_patient_zh(self, raw_label: str) -> str:
        await asyncio.sleep(0)
        excerpt = raw_label[:200]
        return t("mocks.llm.simplify_prefix", locale=self._locale, excerpt=excerpt)
