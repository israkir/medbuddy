import pytest

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.extensibility.intent_hooks import (
    clear_intent_hooks,
    register_intent_hook,
    try_intent_hooks,
)
from medbuddy.models.domain import Intent


@pytest.mark.asyncio
async def test_intent_hook_short_circuits_llm(app_services: AppServices):
    clear_intent_hooks()

    async def hook(
        intent: Intent,
        svc: AppServices,
        user_text: str,
    ) -> str | None:
        _ = user_text
        if intent is Intent.REQUEST_SUMMARY:
            return t("tests.intent_hook_reply", locale=svc.settings.locale)
        return None

    try:
        register_intent_hook(hook)
        out = await try_intent_hooks(Intent.REQUEST_SUMMARY, app_services, "給我摘要")
        assert out is not None
        assert out == t("tests.intent_hook_reply", locale=app_services.settings.locale)
    finally:
        clear_intent_hooks()
