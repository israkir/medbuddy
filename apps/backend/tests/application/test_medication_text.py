"""Medication add / list / remove via assistant text (mock LLM + in-memory users)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from medbuddy.container import build_app_services
from medbuddy.deps import get_services
from medbuddy.core.i18n import t
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.main import app
from medbuddy.models.domain import Intent, MedicationDraft, MedicationRecord


def _headers(*, user: str = "u-med-text") -> dict[str, str]:
    return {"X-App-User-Id": user}


@pytest.mark.asyncio
async def test_messages_add_medication(mock_settings) -> None:
    uid = "user-add-1"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    svc.llm = MockLLM(
        intent=Intent.ADD_MEDICATION,
        medication_draft=MedicationDraft(
            name="阿斯匹靈",
            dosage="100mg",
            schedule="每天飯後",
            instructions="飯後服用",
        ),
    )
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "新增阿斯匹靈 100mg 每天飯後"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    body = r.json()
    reply = body["reply"]
    assert "阿斯匹靈" in reply
    assert "每天飯後" in reply
    assert "常用於" in reply
    assert body["metadata"].get("education_cue_shown") == "add"
    meds = await svc.users.list_medications(uid)
    assert len(meds) == 1
    assert meds[0].name == "阿斯匹靈"


@pytest.mark.asyncio
async def test_messages_add_medication_when_classifier_returns_add_intent(mock_settings) -> None:
    """Production uses LLM structured output for intent; tests pin ADD_MEDICATION + extraction."""
    uid = "user-add-intent-1"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    svc.llm = MockLLM(
        intent=Intent.ADD_MEDICATION,
        medication_draft=MedicationDraft(
            name="majezik",
            dosage="100mg",
            schedule="after meal",
            first_reminder_in_minutes=2,
            materialize_daily_reminders=False,
            instructions="after meal",
        ),
    )
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "add majezik 100mg daily after meal, in 2 mins"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert "majezik" in reply.lower()
    meds = await svc.users.list_medications(uid)
    assert len(meds) == 1
    assert meds[0].name.lower() == "majezik"


@pytest.mark.asyncio
async def test_messages_list_medications(mock_settings) -> None:
    uid = "user-list-1"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    svc.llm = MockLLM(intent=Intent.LIST_MEDICATIONS)
    svc.users.seed_medication(
        uid,
        MedicationRecord(
            id=str(uuid.uuid4()),
            name="Metformin",
            dosage="500mg",
            schedule="晚餐後",
        ),
    )
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "我的藥清單"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    body = r.json()
    reply = body["reply"]
    assert "Metformin" in reply
    assert t("medication.list_intro", locale=mock_settings.locale) in reply
    assert "常用於" in reply or "做什麼用" in reply
    assert body["metadata"].get("education_cue_shown") == "list"


@pytest.mark.asyncio
async def test_messages_remove_medication(mock_settings) -> None:
    uid = "user-rm-1"
    mid = str(uuid.uuid4())
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    svc.llm = MockLLM(intent=Intent.REMOVE_MEDICATION, removal_medication_id=mid)
    svc.users.seed_medication(
        uid,
        MedicationRecord(id=mid, name="普拿疼", dosage="1顆", schedule="痛時"),
    )
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "停藥普拿疼"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert "普拿疼" in reply
    meds = await svc.users.list_medications(uid)
    assert meds == []


@pytest.mark.asyncio
async def test_messages_emergency_contact_line_saved_despite_add_intent(mock_settings) -> None:
    """Taiwan mobile + family wording persists when intent classifier misroutes to add_medication."""
    uid = "user-ec-fast-1"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    svc.llm = MockLLM(intent=Intent.ADD_MEDICATION)
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "my son, David, 0900111111"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    row = await svc.users.get_or_create_user(uid)
    contacts = row.get("emergency_contacts") or []
    assert contacts
    assert contacts[0]["channel_type"] == "phone"
    assert "0900111111" in str(contacts[0]["channel_value"])


@pytest.mark.asyncio
async def test_messages_update_profile_multi_contacts_from_patch(mock_settings) -> None:
    uid = "user-profile-multi-contact"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    svc.llm = MockLLM(
        intent=Intent.UPDATE_PROFILE,
        profile_patch={
            "emergency_contacts": [
                {
                    "contact_name": "David",
                    "relationship": "son",
                    "channel_type": "phone",
                    "channel_value": "0900111222",
                    "is_primary": True,
                },
                {
                    "contact_name": "Amy",
                    "relationship": "daughter",
                    "channel_type": "line",
                    "channel_value": "amy_line_id",
                    "is_primary": False,
                },
            ]
        },
    )
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "Add my son David 0900111222 and daughter Amy LINE amy_line_id"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    row = await svc.users.get_or_create_user(uid)
    contacts = row.get("emergency_contacts") or []
    assert len(contacts) == 2
    assert contacts[0]["channel_type"] == "phone"
    assert contacts[1]["channel_type"] == "line"


@pytest.mark.asyncio
async def test_messages_update_profile(mock_settings) -> None:
    uid = "user-profile-1"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    svc.llm = MockLLM(
        intent=Intent.UPDATE_PROFILE,
        profile_patch={"preferred_name": "陳阿姨", "age_years": 72},
    )
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "我叫陳阿姨，今年72歲"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    reply = r.json()["reply"]
    assert "72" in reply
    row = await svc.users.get_or_create_user(uid)
    assert row["preferred_name"] == "陳阿姨"
    assert row["age_years"] == 72


@pytest.mark.asyncio
async def test_messages_explain_medication_replies(mock_settings) -> None:
    """Explain-medication intent runs compose path (mock LLM) and returns text."""
    uid = "user-explain-1"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    svc.llm = MockLLM(intent=Intent.EXPLAIN_MEDICATION)
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "解釋一下阿斯匹靈是做什麼用的"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    assert len(r.json()["reply"].strip()) > 0


@pytest.mark.asyncio
async def test_messages_emergency_with_saved_contact_simulates_notify(mock_settings) -> None:
    """EMERGENCY intent short-circuits the tool loop; still surface simulated contact notify + metadata."""
    uid = "user-emergency-notify"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    await svc.users.get_or_create_user(uid)
    await svc.users.patch_user_profile(
        uid,
        {
            "locale": "en",
            "emergency_contacts": [
                {
                    "relationship": "daughter",
                    "channel_type": "phone",
                    "channel_value": "0912345678",
                    "is_primary": True,
                }
            ],
        },
    )
    svc.llm = MockLLM(intent=Intent.EMERGENCY, locale="en")
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "i am fainting"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"].get("simulated_emergency_notification") is True
    assert "0912345678" in body["reply"]
    assert "Simulation" in body["reply"]


@pytest.mark.asyncio
async def test_messages_emergency_without_saved_contact_no_notify_metadata(mock_settings) -> None:
    uid = "user-emergency-no-contact"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    await svc.users.get_or_create_user(uid)
    await svc.users.patch_user_profile(uid, {"locale": "en", "emergency_contacts": []})
    svc.llm = MockLLM(intent=Intent.EMERGENCY, locale="en")
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "i am fainting"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    body = r.json()
    assert body["metadata"].get("simulated_emergency_notification") is not True
    assert "Simulation" not in body["reply"]
