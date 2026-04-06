import asyncio
import re
from datetime import UTC, datetime
from typing import Any

from medbuddy.i18n import t
from medbuddy.llm.schemas import (
    HealthSummaryResult,
    InteractionCheckResult,
    MedicationSummaryItem,
)
from medbuddy.models.domain import (
    ConversationTurn,
    HealthSummary,
    Intent,
    InteractionResult,
    MedicationDraft,
    MedicationRecord,
)
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
        ut = user_text.strip()
        lowered = ut.lower()
        med_add = "新增" in ut or "加入" in ut or lowered.startswith("add ")
        if not med_add and re.search(
            r"我叫|叫我|今年\s*\d{1,3}|\d{1,3}\s*歲|歲了|電話|手機|聯絡|過敏|備註|"
            r"my name is|call me|\d{1,3}\s*years old|emergency|allerg",
            ut,
            re.I,
        ):
            return Intent.UPDATE_PROFILE
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
        if "摘要" in user_text or "總結" in user_text or "summary" in lowered:
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
            summary=t("mocks.llm.reply_template", locale=locale).format(
                user_message=user_message
            ),
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
                notes=m.instructions_zh,
            )
            for m in medications
        ]
        med_names = [m.name for m in medications] or [
            t("mocks.llm.summary_no_meds", locale=locale)
        ]
        result = HealthSummaryResult(
            summary_for_doctor=t(
                "mocks.llm.health_summary_doctor",
                locale=locale,
                med_list=", ".join(med_names),
            ),
            key_concerns=[t("mocks.llm.summary_concern_placeholder", locale=locale)],
            reported_symptoms=[],
            medication_adherence_notes=t(
                "mocks.llm.summary_adherence_placeholder", locale=locale
            ),
            recommended_questions=[
                t("mocks.llm.summary_question_placeholder", locale=locale)
            ],
        )
        return HealthSummary(
            generated_at=datetime.now(UTC),
            user_key="",
            locale=locale,
            medications=med_items,
            result=result,
        )
