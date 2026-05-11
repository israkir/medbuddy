"""Tests for reminder scheduled_at version check (R3) and conversation purge (P6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from medbuddy.container import build_app_services
from medbuddy.models.domain import MedicationDraft
from medbuddy.reminders.deliver import deliver_dose_reminder
from tests.helpers import make_mock_settings


@pytest.mark.asyncio
async def test_deliver_skips_when_scheduled_at_mismatch() -> None:
    """If the scheduled_at baked into the job no longer matches the live row, skip."""
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-version-check"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(key, MedicationDraft(name="Metformin", dosage="500mg", schedule="QD"))
    jobs = await svc.users.sync_upcoming_dose_events(key)
    dose_id, scheduled_at = jobs[0]

    stale_iso = (scheduled_at + timedelta(hours=1)).isoformat()
    sent = await deliver_dose_reminder(svc, dose_id, scheduled_at_iso=stale_iso)

    assert sent is False
    assert len(svc.line.pushes) == 0


@pytest.mark.asyncio
async def test_deliver_proceeds_when_scheduled_at_matches() -> None:
    """Delivery proceeds when scheduled_at matches (R3 happy path)."""
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-version-match"
    await svc.users.get_or_create_user(key)
    await svc.users.add_medication(key, MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"))
    jobs = await svc.users.sync_upcoming_dose_events(key)
    dose_id, scheduled_at = jobs[0]

    sent = await deliver_dose_reminder(svc, dose_id, scheduled_at_iso=scheduled_at.isoformat())

    assert sent is True
    assert len(svc.line.pushes) == 1


@pytest.mark.asyncio
async def test_conversation_purge_endpoint_deletes_old_turns() -> None:
    """POST /internal/conversations/purge removes turns older than retention window."""
    import httpx
    from httpx import ASGITransport, AsyncClient
    from medbuddy.main import app

    ms = make_mock_settings(MEDBUDDY_CRON_SECRET="testsecret", LINE_CHANNEL_SECRET="")
    app.state.services = build_app_services(ms)
    svc = app.state.services

    from medbuddy.models.domain import ConversationTurn
    uid = "U-purge-test"

    old_turn = ConversationTurn(
        role="user",
        content="old message",
        at=datetime.now(UTC) - timedelta(days=100),
    )
    recent_turn = ConversationTurn(
        role="user",
        content="recent message",
        at=datetime.now(UTC) - timedelta(days=5),
    )
    await svc.conversations.append_turn(uid, old_turn)
    await svc.conversations.append_turn(uid, recent_turn)

    transport = ASGITransport(app=app)
    with patch("medbuddy.channels.internal.routes.get_settings", return_value=ms):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/internal/conversations/purge",
                headers={"X-Cron-Secret": "testsecret"},
            )
    assert r.status_code == 200
    body = r.json()
    assert body["deleted"] == 1
    assert body["status"] == "ok"

    remaining = await svc.conversations.get_recent_turns(uid, max_turns=10)
    assert len(remaining) == 1
    assert remaining[0].content == "recent message"
