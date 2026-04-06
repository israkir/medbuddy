"""Detect and apply chat-driven locale changes (LINE and mobile share the same user store)."""

from __future__ import annotations

from typing import Any

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.models.domain import Intent
from medbuddy.protocols.ports import LLMPort
from medbuddy.user_locale import (
    effective_user_locale,
    normalize_locale_patch,
    parse_locale_request_from_text,
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
    """Return a short ack if the message requests a locale change; otherwise ``None``.

    Fast path: :func:`parse_locale_request_from_text`. If that misses but the classifier
    returned ``update_locale``, asks the LLM for structured ``en`` / ``zh-TW`` extraction.
    """
    current = effective_user_locale(user_row.get("locale"))
    requested_raw = parse_locale_request_from_text(user_text)
    if requested_raw is None and intent == Intent.UPDATE_LOCALE:
        requested_raw = await llm.extract_locale_intent(user_text)
    if requested_raw is None:
        if intent == Intent.UPDATE_LOCALE:
            return t("locale.unclear", locale=current)
        return None
    requested = normalize_locale_patch(requested_raw)
    if requested is None:
        if intent == Intent.UPDATE_LOCALE:
            return t("locale.unclear", locale=current)
        return None
    if requested == current:
        label = _language_label(target_locale=current, message_locale=current)
        return t("locale.unchanged", locale=current, label=label)
    await svc.users.patch_user_profile(user_key, {"locale": requested})
    label = _language_label(target_locale=requested, message_locale=requested)
    return t("locale.updated", locale=requested, label=label)
