"""Resolve pending reminder-horizon confirmation (how many days for daily reminders).

After a medication is saved with ``needs_horizon_confirmation=True``, a
``ReminderHorizonPending`` state is stored.  The next time the user sends a
message that clearly states a number of days (e.g. "3 days", "一週", "7"),
this resolver intercepts it, patches the medication metadata, and re-syncs
reminders — producing the expected N * doses_per_day dose events.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from medbuddy.services import AppServices
from medbuddy.core.i18n import t
from medbuddy.reminders.lifecycle import sync_and_enqueue_reminders

_DAYS_PATTERNS = [
    # "3 days", "3 天", "3 日", "3d"
    re.compile(r"\b(\d+)\s*(?:days?|天|日|d)\b", re.IGNORECASE),
    # "one week", "1 week", "一週", "一周"
    re.compile(r"\b(1|one|一)\s*(?:week|週|周)\b", re.IGNORECASE),
    re.compile(r"\b(2|two|兩|两)\s*(?:weeks?|週|周)\b", re.IGNORECASE),
    re.compile(r"\b(3|three|三)\s*(?:weeks?|週|周)\b", re.IGNORECASE),
    re.compile(r"\b(4|four|四)\s*(?:weeks?|週|周)\b", re.IGNORECASE),
    # word-numeral days: "seven days", "十四天", etc.
    re.compile(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|"
        r"twenty|thirty|sixty|ninety|"
        r"一|二|三|四|五|六|七|八|九|十|十四|三十)\s*(?:days?|天|日)\b",
        re.IGNORECASE,
    ),
    # bare integer — the whole message is just a number, OR a number at the end
    # after optional filler words ("yes 7", "about 7")
    re.compile(r"(?:^|[\s,，、])(\d+)\s*$"),
]

_WEEK_MULTIPLIERS: dict[str, int] = {
    "1": 7,
    "one": 7,
    "一": 7,
    "2": 14,
    "two": 14,
    "兩": 14,
    "两": 14,
    "3": 21,
    "three": 21,
    "三": 21,
    "4": 28,
    "four": 28,
    "四": 28,
}

_DAY_WORD_VALUES: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "sixty": 60,
    "ninety": 90,
    # zh-TW digit words
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十四": 14,
    "三十": 30,
}


def _parse_horizon_days(text: str) -> int | None:
    """Return 1–90 day count from user text, or None if not clearly stated."""
    s = text.strip()
    # week-based patterns (index 1–4)
    for pat_idx in range(1, 5):
        m = _DAYS_PATTERNS[pat_idx].search(s)
        if m:
            key = m.group(1).lower()
            return _WEEK_MULTIPLIERS.get(key)
    # explicit digit-days: "3 days", "3 天"
    m = _DAYS_PATTERNS[0].search(s)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 90:
            return n
    # word-numeral days: "seven days", "七天"
    m = _DAYS_PATTERNS[5].search(s)
    if m:
        key = m.group(1).lower()
        n = _DAY_WORD_VALUES.get(key)
        if n is not None and 1 <= n <= 90:
            return n
    # bare number at end of message: "7", "yes 7", "about 7"
    m = _DAYS_PATTERNS[6].search(s)
    if m:
        n = int(m.group(1))
        if 1 <= n <= 90:
            return n
    return None


async def try_resolve_pending_reminder_horizon(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
    locale: str,
) -> str | None:
    """If there is a pending reminder-horizon question and the user supplied a day count, apply it.

    Returns the confirmation reply, or ``None`` when the message is not a
    recognisable horizon answer (letting the normal agent flow handle it).
    """
    pending = await svc.users.get_reminder_horizon_pending(user_key)
    if pending is None:
        return None

    now = datetime.now(UTC)
    exp = (
        pending.expires_at if pending.expires_at.tzinfo else pending.expires_at.replace(tzinfo=UTC)
    )
    if now > exp:
        await svc.users.set_reminder_horizon_pending(user_key, None)
        return t("reminder.horizon_expired_ack", locale=locale, name=pending.medication_name)

    days = _parse_horizon_days(user_text)
    if days is None:
        # Not a clear day-count answer — keep pending, let the normal flow answer
        # any other question the user asked.
        return None

    # Resolve target medication first.
    medications = await svc.users.list_medications(user_key)
    target = next((m for m in medications if m.id == pending.medication_id), None)
    if target is None:
        # Medication was removed in the meantime — just confirm gracefully.
        await svc.users.set_reminder_horizon_pending(user_key, None)
        return t("reminder.horizon_confirmed_generic", locale=locale, days=days)

    updated = await svc.users.merge_medication_raw_metadata(
        user_key,
        pending.medication_id,
        {
            "needs_horizon_confirmation": False,
            "materialize_daily": True,
            "horizon_days": days,
        },
    )
    if updated is None:
        # Keep pending so the user can retry.
        return None

    await svc.users.set_reminder_horizon_pending(user_key, None)
    await sync_and_enqueue_reminders(svc, user_key)

    return t(
        "reminder.horizon_confirmed",
        locale=locale,
        name=pending.medication_name,
        days=days,
    )
