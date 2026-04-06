import asyncio
import re

from medbuddy.i18n import t
from medbuddy.models.domain import ConversationTurn, Intent, MedicationDraft, MedicationRecord
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
        if any(k in user_text for k in ("清單", "哪些藥", "有什麼藥")) or (
            "我的藥" in user_text and "加" not in user_text and "新增" not in user_text
        ):
            return Intent.LIST_MEDICATIONS
        if any(k in user_text for k in ("停藥", "刪除藥", "不吃了", "移除藥", "不用吃了")):
            return Intent.REMOVE_MEDICATION
        if "新增" in user_text or "加入" in user_text:
            return Intent.ADD_MEDICATION
        if "藥" in user_text and "加" in user_text:
            return Intent.ADD_MEDICATION
        if lowered.startswith("add ") or " add " in f" {lowered} ":
            return Intent.ADD_MEDICATION
        if lowered.startswith("list med") or "my medications" in lowered:
            return Intent.LIST_MEDICATIONS
        if "remove " in lowered or "stop taking" in lowered or "delete med" in lowered:
            return Intent.REMOVE_MEDICATION
        if (
            "interaction" in lowered
            or "interactions" in lowered
            or "take together" in lowered
            or "mix with" in lowered
        ):
            return Intent.INTERACTION_CHECK
        if any(
            phrase in lowered
            for phrase in (
                "what is ",
                "what's ",
                "explain ",
                "purpose of",
                "why take",
                "why do i take",
                "what does ",
                " for?",
            )
        ):
            return Intent.EXPLAIN_MEDICATION
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

    async def extract_medication_draft(
        self, user_text: str, *, locale: str
    ) -> MedicationDraft | None:
        await asyncio.sleep(0)
        un = t("medication.unspecified", locale=locale)
        for marker in ("新增", "加入"):
            if marker in user_text:
                rest = user_text.split(marker, 1)[1].strip()
                rest = re.split(r"[，。；]", rest)[0].strip()
                parts = rest.split()
                if not parts:
                    return None
                return MedicationDraft(
                    name=parts[0],
                    dosage=parts[1] if len(parts) > 1 else un,
                    schedule=parts[2] if len(parts) > 2 else un,
                )
        low = user_text.lower()
        if low.startswith("add "):
            rest = user_text[4:].strip()
            parts = re.split(r"[\s,;]+", rest)
            parts = [p for p in parts if p]
            if not parts:
                return None
            return MedicationDraft(
                name=parts[0],
                dosage=parts[1] if len(parts) > 1 else un,
                schedule=parts[2] if len(parts) > 2 else un,
            )
        return None

    async def resolve_medication_removal_id(
        self,
        user_text: str,
        medications: list[MedicationRecord],
        *,
        locale: str,
    ) -> str | None:
        await asyncio.sleep(0)
        _ = locale
        lt = user_text.lower()
        for med in medications:
            if med.name.lower() in lt or lt in med.name.lower():
                return med.id
        return None

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
