"""Resolve pending dose disambiguation replies before intent classification."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t

_ALL_WORDS_EN = frozenset({"all", "both", "all of them"})
_ALL_WORDS_ZH = frozenset({"全部", "兩個都", "兩種都要", "都要"})


def _parse_clarification_choice(
    text: str, *, num_options: int
) -> Literal["not_a_choice", "invalid", "all"] | int:
    raw = (text or "").strip()
    if not raw:
        return "not_a_choice"
    tl = raw.lower()
    if num_options >= 2:
        if tl in _ALL_WORDS_EN or raw in _ALL_WORDS_ZH:
            return "all"
    m = re.fullmatch(r"[#＃]?\s*(\d+)\s*", raw)
    if not m:
        return "not_a_choice"
    n = int(m.group(1))
    if 1 <= n <= num_options:
        return n
    return "invalid"


async def try_resolve_pending_dose_clarification(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
    locale: str,
) -> str | None:
    """If user is answering a dose choice prompt, apply and return reply; else ``None``."""
    pending = await svc.users.get_dose_clarification_pending(user_key)
    if pending is None:
        return None
    now = datetime.now(UTC)
    exp = (
        pending.expires_at if pending.expires_at.tzinfo else pending.expires_at.replace(tzinfo=UTC)
    )
    if now > exp:
        await svc.users.set_dose_clarification_pending(user_key, None)
        return None

    choice = _parse_clarification_choice(user_text, num_options=len(pending.option_ids))
    if choice == "not_a_choice":
        await svc.users.set_dose_clarification_pending(user_key, None)
        return None
    if choice == "invalid":
        return t("medication.confirm_dose_clarify_invalid", locale=locale)

    if choice == "all":
        ids = list(pending.option_ids)
    else:
        ids = [pending.option_ids[choice - 1]]

    await svc.users.set_dose_clarification_pending(user_key, None)

    if pending.kind == "pending_taken":
        n = await svc.users.mark_dose_events_taken(user_key, ids, notes=pending.pending_note)
        if n <= 0:
            return t("medication.confirm_dose_none", locale=locale)
        if pending.pending_note:
            return t(
                "medication.confirm_dose_recorded_with_note",
                locale=locale,
                count=n,
                note=pending.pending_note,
            )
        return t("medication.confirm_dose_recorded", locale=locale, count=n)

    note = (pending.pending_note or "").strip()
    if not note:
        return t("medication.confirm_dose_none", locale=locale)
    n2 = await svc.users.append_note_to_dose_events(user_key, ids, notes=note)
    if n2 <= 0:
        return t("medication.confirm_dose_none", locale=locale)
    return t("medication.confirm_dose_note_appended", locale=locale, note=note)
