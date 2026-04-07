"""Tests for marking doses missed via ReportMissedDoseTool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from medbuddy.agents.tools.report_missed_dose import ReportMissedDoseTool
from medbuddy.config import Settings
from medbuddy.container import build_app_services
from medbuddy.models.domain import MedicationDraft


@pytest.mark.asyncio
async def test_report_missed_dose_marks_latest_pending_window() -> None:
    settings = Settings(mock_external_services=True)
    svc = build_app_services(settings)
    key = "U-missed-dose"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(
        key,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(key)
    assert jobs
    dose_id, _ = jobs[0]
    svc.users._doses[dose_id]["scheduled_at"] = datetime.now(UTC) - timedelta(hours=2)  # noqa: SLF001

    tool = ReportMissedDoseTool()
    r1 = await tool.run(
        svc=svc,
        user_key=key,
        user_text="I forgot my dose this morning",
        locale="en",
    )
    assert "missed" in r1.reply.lower()
    assert svc.users._doses[dose_id].get("missed_at") is not None  # noqa: SLF001
    assert svc.users._doses[dose_id].get("taken_at") is None  # noqa: SLF001

    r2 = await tool.run(
        svc=svc,
        user_key=key,
        user_text="I forgot my dose this morning",
        locale="en",
    )
    assert "see a pending recent dose" in r2.reply.lower()

