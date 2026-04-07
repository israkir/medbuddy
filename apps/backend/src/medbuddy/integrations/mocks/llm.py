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
from medbuddy.protocols.ports import LLMPort, ProfilePatch
from medbuddy.user_locale import parse_locale_request_from_text


class MockLLM(LLMPort):
    """Templated replies for CI. Intent classification uses narrow defaults unless ``intent=`` is fixed — production uses OpenAI / Gemini."""

    def __init__(
        self,
        intent: Intent | None = None,
        *,
        locale: str = "zh-TW",
        reply_template: str | None = None,
        profile_patch: ProfilePatch | None = None,
        dose_note: str | None = None,
    ) -> None:
        self._intent = intent
        self._locale = locale
        self.reply_template = reply_template or t("mocks.llm.reply_template", locale=locale)
        self._profile_patch = profile_patch
        self._dose_note = dose_note
        self.last_classify_input: str | None = None

    async def classify_intent(self, user_text: str, *, recent_context: str | None = None) -> Intent:
        await asyncio.sleep(0)
        self.last_classify_input = user_text
        _ = recent_context
        if self._intent is not None:
            return self._intent
        ut = user_text.strip()
        lowered = ut.lower()
        if re.search(r"(?i)天氣|weather|forecast|講個笑話|tell me a joke", ut):
            return Intent.OFF_TOPIC
        if any(
            x in lowered
            for x in (
                "switch to english",
                "use english",
                "prefer english",
                "english replies",
                "i prefer english",
                "請用中文",
                "traditional chinese",
                "改用繁體",
            )
        ):
            return Intent.UPDATE_LOCALE
        if (
            "解釋" in user_text
            or "explain " in lowered
            or "what's " in lowered
            or "what is " in lowered
        ):
            return Intent.EXPLAIN_MEDICATION
        if any(k in user_text for k in ("清單", "哪些藥", "list med", "my medications")):
            return Intent.LIST_MEDICATIONS
        if "新增" in ut or "加入" in ut or lowered.startswith("add "):
            return Intent.ADD_MEDICATION
        if any(k in user_text for k in ("停藥", "remove ", "stop taking")):
            return Intent.REMOVE_MEDICATION
        if "交互" in user_text or "interaction" in lowered:
            return Intent.INTERACTION_CHECK
        if "摘要" in user_text or "summary" in lowered:
            return Intent.REQUEST_SUMMARY
        if re.search(r"(?i)(吃了|已吃|took|taken|i took|i've taken)", ut):
            return Intent.CONFIRM_DOSE
        if "血壓" in user_text or "血糖" in user_text:
            return Intent.LOG_VITAL
        return Intent.GENERAL_QUESTION

    async def extract_profile_patch(self, user_text: str, *, locale: str) -> ProfilePatch:
        await asyncio.sleep(0)
        _ = (user_text, locale)
        if self._profile_patch is not None:
            return dict(self._profile_patch)
        return {}

    async def extract_dose_confirmation_note(self, user_text: str, *, locale: str) -> str | None:
        await asyncio.sleep(0)
        _ = (user_text, locale)
        if self._dose_note is not None:
            return self._dose_note
        return None

    async def extract_locale_intent(self, user_text: str) -> str | None:
        await asyncio.sleep(0)
        direct = parse_locale_request_from_text(user_text)
        if direct is not None:
            return direct
        ut = user_text.lower()
        if re.search(
            r"(?i)prefer\s+english|english\s+replies|i\s+want\s+english|"
            r"i'?d\s+rather\s+(?:use|have|read)\s+english|only\s+english",
            ut,
        ) and not re.search(r"請用英文\s*說明", user_text):
            return "en"
        if re.search(
            r"(?i)prefer\s+chinese|traditional\s+chinese|mandarin|zh[- ]?tw|"
            r"請用中文|改用中文|only\s+chinese",
            ut,
        ):
            return "zh-TW"
        return None

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
        un = t("medication.unspecified", locale=locale)
        minutes_m = re.search(r"(\d+)\s*分鐘", user_text)
        first_min: int | None = None
        if minutes_m:
            first_min = max(1, int(minutes_m.group(1)))
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
                    first_reminder_in_minutes=first_min,
                    materialize_daily_reminders=first_min is None,
                    needs_horizon_confirmation=False,
                )
        low = user_text.lower()
        if low.startswith("add "):
            rest = user_text[4:].strip()
            parts = re.split(r"[\s,;]+", rest)
            parts = [p for p in parts if p]
            if not parts:
                return None
            en_min = re.search(r"in\s+(\d+)\s*(?:min|minutes?)", low)
            fm = max(1, int(en_min.group(1))) if en_min else first_min
            return MedicationDraft(
                name=parts[0],
                dosage=parts[1] if len(parts) > 1 else un,
                schedule=parts[2] if len(parts) > 2 else un,
                first_reminder_in_minutes=fm,
                materialize_daily_reminders=fm is None,
                needs_horizon_confirmation=False,
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
