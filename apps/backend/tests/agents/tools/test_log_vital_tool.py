"""Tests for vital sign logging."""

from __future__ import annotations

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.application.vital_log_build import vital_payload_and_summary
from tests.helpers import make_mock_settings
from medbuddy.container import build_app_services
from medbuddy.core.errors import VitalExtractionError
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.llm.schemas import VitalLogExtraction
from medbuddy.models.domain import HEALTH_ROUTING_INTENT_VITAL, Intent


def test_vital_payload_blood_pressure() -> None:
    ext = VitalLogExtraction(kind="blood_pressure", systolic=120, diastolic=80)
    kind, summary, payload, notes = vital_payload_and_summary(ext, locale="en")
    assert kind == "blood_pressure"
    assert payload["systolic"] == 120
    assert payload["diastolic"] == 80
    assert "120" in summary and "80" in summary
    assert notes is None


def test_vital_payload_rejects_invalid_bp() -> None:
    ext = VitalLogExtraction(kind="blood_pressure", systolic=120, diastolic=None)
    with pytest.raises(VitalExtractionError):
        vital_payload_and_summary(ext, locale="en")


@pytest.mark.asyncio
async def test_log_vital_end_to_end_blood_pressure() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-log-vital-bp"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    svc.llm = MockLLM(
        intent=Intent.LOG_VITAL,
        locale="en",
        vital_log=VitalLogExtraction(kind="blood_pressure", systolic=118, diastolic=76),
    )
    reply = (
        await run_assistant_text_turn(
            svc, user_key=key, user_text="my blood pressure was 118 over 76"
        )
    ).reply
    assert "118" in reply and "76" in reply
    vitals = svc.users._vitals.get(key, [])  # noqa: SLF001 — mock store
    assert len(vitals) == 1
    assert vitals[0].payload["systolic"] == 118
    assert vitals[0].kind == "blood_pressure"
    assert vitals[0].routing_intent == HEALTH_ROUTING_INTENT_VITAL


@pytest.mark.asyncio
async def test_log_vital_extraction_failure_user_message() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-log-vital-fail"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    svc.llm = MockLLM(intent=Intent.LOG_VITAL, locale="en", vital_log=None)
    reply = (await run_assistant_text_turn(svc, user_key=key, user_text="log something")).reply
    assert "didn" in reply.lower() or "clear" in reply.lower()
