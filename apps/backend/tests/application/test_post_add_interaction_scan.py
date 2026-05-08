"""After adding a 2+ medication, a structured interaction scan is appended to the reply."""

from __future__ import annotations

import pytest

from medbuddy.agents.tools.medication_crud import persist_medication_add_from_draft
from medbuddy.container import build_app_services
from medbuddy.core.i18n import t
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.models.domain import MedicationDraft
from tests.helpers import make_mock_settings


@pytest.mark.asyncio
async def test_post_add_interaction_skipped_when_only_one_medication() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-post-ix-one"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    svc.llm = MockLLM(locale="en")
    draft = MedicationDraft(
        name="Aspirin",
        dosage="100mg",
        schedule="once daily",
        instructions=None,
    )
    result = await persist_medication_add_from_draft(
        svc, user_key=key, user_text="add aspirin", draft=draft, locale="en"
    )
    bridge = t("medication.post_add_interaction_bridge", locale="en")
    assert bridge not in result.reply


@pytest.mark.asyncio
async def test_post_add_interaction_appended_when_second_medication() -> None:
    settings = make_mock_settings()
    svc = build_app_services(settings)
    key = "U-post-ix-two"
    await svc.users.get_or_create_user(key)
    await svc.users.patch_user_profile(key, {"locale": "en"})
    await svc.users.add_medication(
        key,
        MedicationDraft(
            name="Metformin",
            dosage="500mg",
            schedule="twice daily",
            instructions=None,
        ),
    )
    svc.llm = MockLLM(locale="en")
    draft = MedicationDraft(
        name="Aspirin",
        dosage="100mg",
        schedule="once daily",
        instructions=None,
    )
    result = await persist_medication_add_from_draft(
        svc, user_key=key, user_text="add aspirin 100mg daily", draft=draft, locale="en"
    )
    bridge = t("medication.post_add_interaction_bridge", locale="en")
    assert bridge in result.reply
    ix_query = t("medication.post_add_interaction_user_query", locale="en", name="Aspirin")
    assert ix_query in result.reply
