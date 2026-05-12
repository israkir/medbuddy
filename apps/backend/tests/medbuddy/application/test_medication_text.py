"""Medication add / list / remove via assistant text (mock LLM + in-memory users)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from medbuddy.container import build_app_services
from medbuddy.deps import get_services
from medbuddy.core.i18n import t
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.main import app
from medbuddy.models.domain import Intent, MedicationDraft, MedicationRecord


class _ReminderFollowUpYesMockLLM(MockLLM):
    """Turn 1: general reply about vitamin C + 1-minute offer; turn 2: add via context + ``yes``."""

    def __init__(self) -> None:
        super().__init__(
            intent=Intent.GENERAL_QUESTION,
            locale="en",
            reply_template=(
                "Your vitamin C reminder is scheduled for 04:16, not in 1 minute from now. "
                "If you want, I can set a new reminder specifically for one minute from now. "
                "Would you like me to do that?"
            ),
        )

    async def interpret_user_turn(self, user_text: str, *, recent_context: str | None = None):
        if user_text.strip().lower() == "yes":
            self._intent = Intent.ADD_MEDICATION
        else:
            self._intent = Intent.GENERAL_QUESTION
        return await super().interpret_user_turn(user_text, recent_context=recent_context)

    async def extract_medication_draft(
        self,
        user_text: str,
        *,
        locale: str,
        recent_context: str | None = None,
    ):
        un = t("medication.unspecified", locale=locale)
        ut = user_text.strip().lower()
        rc = (recent_context or "").lower()
        affirm = ut in {"yes", "y", "ok", "sure"}
        if affirm and "vitamin c" in rc and ("1 minute" in rc or "one minute" in rc):
            return MedicationDraft(
                name="Vitamin C",
                dosage=un,
                schedule=un,
                first_reminder_in_minutes=1,
                materialize_daily_reminders=False,
            )
        return await super().extract_medication_draft(
            user_text, locale=locale, recent_context=recent_context
        )


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
        # Post-add no longer stacks education_purpose_line after successful compose
        # (only after i18n medication.added fallback); mock compose still embeds grounding.
        assert "參考摘錄" in reply or "TFDA" in reply
    assert body["metadata"].get("education_cue_shown") == "add"
    meds = await svc.users.list_medications(uid)
    assert len(meds) == 1
    assert meds[0].name == "阿斯匹靈"


@pytest.mark.asyncio
async def test_yes_after_reminder_offer_resolves_vitamin_c_from_context(mock_settings) -> None:
    """Regression: ``add_medication`` extraction receives prior turns so bare ``yes`` keeps the drug."""
    uid = "user-reminder-yes-ctx"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    await svc.users.get_or_create_user(uid)
    await svc.users.patch_user_profile(uid, {"locale": "en"})
    svc.llm = _ReminderFollowUpYesMockLLM()
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r1 = await client.post(
                    "/v1/app/messages",
                    json={"text": "I thought my vitamin C was in one minute"},
                    headers=_headers(user=uid),
                )
                assert r1.status_code == 200
                assert "vitamin c" in r1.json()["reply"].lower()

                r2 = await client.post(
                    "/v1/app/messages",
                    json={"text": "yes"},
                    headers=_headers(user=uid),
                )
                assert r2.status_code == 200
                reply2 = r2.json()["reply"].lower()
                assert "vitamin c" in reply2
                assert "i'd like to save" not in reply2
                assert "medication name" not in reply2
    finally:
        app.dependency_overrides.pop(get_services, None)

    meds = await svc.users.list_medications(uid)
    assert len(meds) == 1
    assert meds[0].name == "Vitamin C"


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
    assert "常見用途" in reply or "做什麼用" in reply
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
    primary = contacts[0]
    assert primary["is_primary"] is True
    assert primary["channel_type"] == "line"
    assert primary["channel_value"] == "amy_line_id"
    secondary = contacts[1]
    assert secondary["is_primary"] is False
    assert secondary["channel_type"] == "phone"


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
async def test_update_profile_persisted_when_planner_text_only(mock_settings) -> None:
    """Classifier UPDATE_PROFILE + extraction persists even when the tool planner returns prose only."""
    uid = "user-profile-planner-text-only"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    svc.llm = MockLLM(
        intent=Intent.UPDATE_PROFILE,
        locale="en",
        profile_patch={"preferred_name": "David", "age_years": 70, "gender": "male"},
        orchestrator_text_only=True,
    )
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "I'm David, 70, male"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    row = await svc.users.get_or_create_user(uid)
    assert row["preferred_name"] == "David"
    assert row["age_years"] == 70
    assert row["gender"] == "male"


@pytest.mark.asyncio
async def test_report_side_effects_applies_classifier_adherence_without_confirm_dose_tool(
    mock_settings,
) -> None:
    """Stage-1 adherence slots apply when the planner calls report_side_effects but not confirm_dose."""
    uid = "user-sfx-adherence-merge"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    await svc.users.get_or_create_user(uid)
    await svc.users.patch_user_profile(uid, {"locale": "en"})
    await svc.users.add_medication(
        uid,
        MedicationDraft(name="Aspirin", dosage="100mg", schedule="QD"),
    )
    jobs = await svc.users.sync_upcoming_dose_events(uid)
    assert jobs
    dose_id, _ = jobs[0]
    svc.users._doses[dose_id]["scheduled_at"] = datetime.now(UTC) - timedelta(
        hours=2
    )  # noqa: SLF001

    svc.llm = MockLLM(
        intent=Intent.REPORT_SIDE_EFFECTS,
        locale="en",
        record_pending_dose_as_taken=True,
        dose_adherence_note="Dizzy after taking it",
        orchestrator_tools_step1=[("report_side_effects", "{}")],
    )
    app.dependency_overrides[get_services] = lambda: svc
    try:
        with patch("medbuddy.channels.api.auth.get_settings", return_value=mock_settings):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                r = await client.post(
                    "/v1/app/messages",
                    json={"text": "I took aspirin and feel dizzy"},
                    headers=_headers(user=uid),
                )
    finally:
        app.dependency_overrides.pop(get_services, None)
    assert r.status_code == 200
    dose_row = svc.users._doses[dose_id]  # noqa: SLF001
    assert dose_row.get("taken_at") is not None
    assert "Dizzy" in (dose_row.get("notes") or "")


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
    assert "demo build" in body["reply"].lower()


@pytest.mark.asyncio
async def test_messages_emergency_lists_all_saved_contacts(mock_settings) -> None:
    """EMERGENCY intent should mention every emergency contact on file, not only the primary."""
    uid = "user-emergency-multi"
    transport = ASGITransport(app=app)
    svc = build_app_services(mock_settings)
    await svc.users.get_or_create_user(uid)
    await svc.users.patch_user_profile(
        uid,
        {
            "locale": "en",
            "emergency_contacts": [
                {
                    "relationship": "son",
                    "channel_type": "phone",
                    "channel_value": "0900111111",
                },
                {
                    "relationship": "daughter",
                    "channel_type": "phone",
                    "channel_value": "0922222222",
                },
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
    reply = body["reply"]
    assert "0900111111" in reply
    assert "0922222222" in reply
    assert "saved contacts" in reply.lower()
    assert "would be notified" in reply.lower()


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


# ---------------------------------------------------------------------------
# Duplicate-add dedup: adding the same medication name twice yields one row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_medication_dedup_same_name_returns_already_on_file(mock_settings) -> None:
    """Calling add_medication twice with the same name must return the dedup reply
    and must NOT create a second row in the medications table."""
    from medbuddy.application.assistant_turn import run_assistant_text_turn

    uid = "user-dedup-aspirin-1"
    svc = build_app_services(mock_settings)
    await svc.users.get_or_create_user(uid)
    await svc.users.patch_user_profile(uid, {"locale": "en"})
    # Pre-seed aspirin so the tool hits the dedup guard on the first call.
    await svc.users.add_medication(
        uid,
        MedicationDraft(
            name="Aspirin",
            dosage="100mg",
            schedule="once daily after breakfast",
        ),
    )
    svc.llm = MockLLM(
        intent=Intent.ADD_MEDICATION,
        locale="en",
        medication_draft=MedicationDraft(
            name="Aspirin",
            dosage="100mg",
            schedule="once daily after breakfast",
        ),
    )
    result = await run_assistant_text_turn(svc, user_key=uid, user_text="aspirin 100 mg once daily")
    meds = await svc.users.list_medications(uid)
    assert len(meds) == 1, "Dedup should prevent a second aspirin row"
    reply_lower = result.reply.lower()
    assert "already" in reply_lower or "update" in reply_lower


@pytest.mark.asyncio
async def test_add_medication_dedup_case_insensitive(mock_settings) -> None:
    """Dedup must be case-insensitive: 'ASPIRIN' matches 'aspirin'."""
    from medbuddy.application.assistant_turn import run_assistant_text_turn

    uid = "user-dedup-case-insensitive"
    svc = build_app_services(mock_settings)
    await svc.users.get_or_create_user(uid)
    await svc.users.patch_user_profile(uid, {"locale": "en"})
    await svc.users.add_medication(
        uid,
        MedicationDraft(name="ASPIRIN", dosage="100mg", schedule="once daily"),
    )
    svc.llm = MockLLM(
        intent=Intent.ADD_MEDICATION,
        locale="en",
        medication_draft=MedicationDraft(
            name="aspirin",
            dosage="100mg",
            schedule="once daily",
        ),
    )
    await run_assistant_text_turn(svc, user_key=uid, user_text="aspirin 100mg once daily")
    meds = await svc.users.list_medications(uid)
    assert len(meds) == 1
