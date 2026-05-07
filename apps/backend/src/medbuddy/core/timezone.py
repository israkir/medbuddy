"""User profile IANA timezone (defaults to Taipei) for reminders and local-time display."""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_USER_TIMEZONE = "Asia/Taipei"


def is_valid_iana_timezone(name: str) -> bool:
    s = name.strip()
    if not s:
        return False
    try:
        ZoneInfo(s)
    except (ZoneInfoNotFoundError, OSError):
        return False
    return True


def effective_user_timezone(stored: str | None) -> str:
    """Return stored zone if valid-looking, else default Taipei."""
    if stored is None:
        return DEFAULT_USER_TIMEZONE
    s = str(stored).strip()
    if not s:
        return DEFAULT_USER_TIMEZONE
    if is_valid_iana_timezone(s):
        return s
    return DEFAULT_USER_TIMEZONE


def normalize_timezone_patch(raw: object) -> str | None:
    """For profile patches: return validated IANA name, or None to clear / invalid skip."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    return s if is_valid_iana_timezone(s) else None
