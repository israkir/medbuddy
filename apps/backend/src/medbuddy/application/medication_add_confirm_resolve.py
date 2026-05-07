"""Resolve pending add-medication confirmation before intent classification."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from medbuddy.agents.tools.medication_crud import persist_medication_add_from_draft
from medbuddy.services import AppServices
from medbuddy.core.i18n import t

_YES_EN = frozenset(
    {
        "yes",
        "y",
        "ok",
        "okay",
        "sure",
        "confirm",
        "yeah",
        "yep",
    }
)
_YES_ZH = frozenset({"好", "可以", "確認", "是", "對", "嗯", "恩", "行"})
_NO_EN = frozenset({"no", "n", "nope", "cancel", "stop"})
_NO_ZH = frozenset({"不要", "取消", "不用", "算了", "否", "別"})


def _normalize_confirm_reply(text: str) -> str:
    s = (text or "").strip()
    for strip in (".", "。", "!", "！", "?", "？"):
        s = s.strip(strip)
    return s.strip()


def _parse_add_medication_confirm(
    text: str,
) -> Literal["not_handled", "yes", "no"]:
    raw = _normalize_confirm_reply(text)
    if not raw:
        return "not_handled"
    tl = raw.lower()
    if tl in _YES_EN or raw in _YES_ZH:
        return "yes"
    if tl in _NO_EN or raw in _NO_ZH:
        return "no"
    return "not_handled"


async def try_resolve_pending_medication_add_confirmation(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
    locale: str,
) -> str | None:
    """If user is answering a pending incomplete-medication prompt, apply and return reply."""
    pending = await svc.users.get_medication_add_confirmation_pending(user_key)
    if pending is None:
        return None
    now = datetime.now(UTC)
    exp = (
        pending.expires_at if pending.expires_at.tzinfo else pending.expires_at.replace(tzinfo=UTC)
    )
    if now > exp:
        await svc.users.set_medication_add_confirmation_pending(user_key, None)
        return None

    choice = _parse_add_medication_confirm(user_text)
    if choice == "not_handled":
        # Do NOT clear the pending state — the user may be asking a follow-up question
        # (e.g. "what does this drug do?") while we are still waiting for their yes/no.
        # The normal agent flow will answer the question; the pending state remains active
        # so the next yes/no reply is still caught here.
        return None

    await svc.users.set_medication_add_confirmation_pending(user_key, None)
    if choice == "no":
        return t("medication.add_confirm_cancelled", locale=locale)

    result = await persist_medication_add_from_draft(
        svc,
        user_key=user_key,
        user_text=user_text,
        draft=pending.draft,
        locale=locale,
    )
    return result.reply
