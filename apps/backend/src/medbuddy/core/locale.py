"""App UI locale for standalone users (BCP 47 tags supported by the Expo client)."""

from __future__ import annotations

ALLOWED_APP_LOCALES = frozenset({"en", "zh-TW"})


def effective_user_locale(value: object | None) -> str:
    if isinstance(value, str) and value in ALLOWED_APP_LOCALES:
        return value
    return "zh-TW"


def normalize_locale_patch(value: object) -> str | None:
    """Return a locale to persist, or None if the patch should not change locale."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s in ALLOWED_APP_LOCALES:
            return s
    return None
