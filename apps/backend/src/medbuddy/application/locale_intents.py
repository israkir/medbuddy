"""Legacy locale helper (kept for compatibility, now routed via update_profile)."""

from __future__ import annotations

from typing import Any

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.models.domain import Intent
from medbuddy.protocols.ports import LLMPort
from medbuddy.user_locale import (
    effective_user_locale,
    normalize_locale_patch,
)


def _language_label(*, target_locale: str, message_locale: str) -> str:
    key = "locale.label_en" if target_locale == "en" else "locale.label_zh_tw"
    return t(key, locale=message_locale)


async def try_locale_change_reply(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
    user_row: dict[str, Any],
    intent: Intent,
    llm: LLMPort,
) -> str | None:
    """Return a short ack if the message requests a locale change; otherwise ``None``."""
    current = effective_user_locale(user_row.get("locale"))
    if intent == Intent.EMERGENCY:
        return None

    requested_raw = await llm.extract_locale_intent(user_text)
    if requested_raw is None:
        # Keep compatibility with older routing behaviour where locale changes
        # are extracted through the generic profile patch path.
        patch = await llm.extract_profile_patch(user_text, locale=current)
        requested_raw = patch.get("locale")
    if requested_raw is None:
        return None
    requested = normalize_locale_patch(requested_raw)
    if requested is None:
        return t("locale.unclear", locale=current)
    if requested == current:
        label = _language_label(target_locale=current, message_locale=current)
        return t("locale.unchanged", locale=current, label=label)
    await svc.users.patch_user_profile(user_key, {"locale": requested})
    label = _language_label(target_locale=requested, message_locale=requested)
    return t("locale.updated", locale=requested, label=label)
