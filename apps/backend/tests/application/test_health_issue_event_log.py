"""Tests for classifier-intent health issue logging and summary formatting."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from medbuddy.agents.tools.health_summary import GenerateHealthSummaryTool
from medbuddy.application.health_events.health_issue_event_log import (
    should_log_routing_intent_health_issue,
)
from medbuddy.application.health_events.health_issue_events_format import (
    format_health_issue_events_for_summary,
)
from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.container import build_app_services
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.models.domain import HealthIssueEventRecord, Intent
from tests.helpers import make_mock_settings


def test_should_log_general_question_default_policy() -> None:
    s = make_mock_settings()
    assert should_log_routing_intent_health_issue(Intent.GENERAL_QUESTION, s) is True


def test_should_log_off_topic_default_policy() -> None:
    s = make_mock_settings()
    assert should_log_routing_intent_health_issue(Intent.OFF_TOPIC, s) is False


def test_should_log_default_excludes_log_vital_and_list_meds() -> None:
    s = make_mock_settings()
    assert should_log_routing_intent_health_issue(Intent.LOG_VITAL, s) is False
    assert should_log_routing_intent_health_issue(Intent.LIST_MEDICATIONS, s) is False


def test_should_log_explicit_allowlist() -> None:
    s = make_mock_settings(MEDBUDDY_HEALTH_ISSUE_LOG_INTENTS="emergency,general_question")
    assert should_log_routing_intent_health_issue(Intent.EMERGENCY, s) is True
    assert should_log_routing_intent_health_issue(Intent.REPORT_SIDE_EFFECTS, s) is False


def test_should_log_all_non_off_topic_includes_log_vital_intent_value() -> None:
    s = make_mock_settings(MEDBUDDY_HEALTH_ISSUE_LOG_INTENTS="all_non_off_topic")
    assert should_log_routing_intent_health_issue(Intent.OFF_TOPIC, s) is False
    assert should_log_routing_intent_health_issue(Intent.LOG_VITAL, s) is True


@pytest.mark.asyncio
async def test_maybe_record_logs_general_question_turn() -> None:
    svc = build_app_services(make_mock_settings())
    key = "U-hie-gq"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    svc.llm = MockLLM(intent=Intent.GENERAL_QUESTION, locale="en")
    await run_assistant_text_turn(svc, user_key=key, user_text="I feel a bit dizzy today")
    rows = svc.users._vitals.get(key, [])  # noqa: SLF001
    assert any(r.routing_intent == Intent.GENERAL_QUESTION.value for r in rows)


@pytest.mark.asyncio
async def test_health_summary_passes_logged_events_block_to_llm() -> None:
    svc = build_app_services(make_mock_settings())
    key = "U-hie-sum"
    await svc.users.get_or_create_user(key)
    await svc.users.record_health_issue_event(
        key,
        routing_intent=Intent.REPORT_SIDE_EFFECTS.value,
        user_message="mild nausea after lunch",
        locale="en",
    )
    llm = MockLLM(intent=Intent.REQUEST_SUMMARY, locale="en")
    svc.llm = llm
    tool = GenerateHealthSummaryTool()
    await tool.run(
        svc=svc,
        user_key=key,
        user_row=await svc.users.get_or_create_user(key),
        medications=[],
        locale="en",
    )
    assert llm.last_health_issue_events_block is not None
    assert "report_side_effects" in llm.last_health_issue_events_block
    assert "nausea" in llm.last_health_issue_events_block


def test_format_health_issue_events_chronological_lines() -> None:
    a = HealthIssueEventRecord(
        id="1",
        routing_intent="general_question",
        user_message="headache",
        locale="en",
        kind=None,
        display_summary=None,
        payload={},
        notes=None,
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    b = HealthIssueEventRecord(
        id="2",
        routing_intent="log_vital",
        user_message=None,
        locale="en",
        kind="blood_pressure",
        display_summary="118/76",
        payload={"systolic": 118},
        notes=None,
        created_at=datetime(2026, 1, 3, tzinfo=UTC),
    )
    text = format_health_issue_events_for_summary([b, a])
    assert text.index("headache") < text.index("118")
