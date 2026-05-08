"""App UI locale for standalone users (BCP 47 tags supported by the Expo client)."""

from __future__ import annotations

ALLOWED_APP_LOCALES = frozenset({"en", "zh-TW"})


def locale_from_language_hints(*tags: str | None) -> str:
    """Map BCP-47 or ISO-639-1 tags to ``en`` or ``zh-TW`` (matches Expo ``resolveInitialLanguage``).

    Unknown or unsupported primary languages fall back to ``zh-TW``.
    """
    for raw in tags:
        if not raw or not isinstance(raw, str):
            continue
        piece = raw.strip()
        if not piece:
            continue
        if ";" in piece:
            piece = piece.split(";", 1)[0].strip()
        if not piece:
            continue
        tag = piece.replace("_", "-")
        primary = tag.split("-", 1)[0].lower()
        lower = tag.lower()
        if primary == "zh" or lower.startswith("zh-"):
            return "zh-TW"
        if primary == "en":
            return "en"
    return "zh-TW"


def locale_from_client_language_headers(
    x_medbuddy_locale: str | None,
    accept_language: str | None,
) -> str | None:
    """Resolve locale from optional HTTP hints; ``None`` if no usable hint (skip profile patch)."""
    tags: list[str] = []
    if isinstance(x_medbuddy_locale, str) and x_medbuddy_locale.strip():
        tags.append(x_medbuddy_locale.strip())
    if isinstance(accept_language, str) and accept_language.strip():
        # Primary preference only (first entry; q-values apply within that entry's tag).
        first = accept_language.split(",", 1)[0].strip()
        if first:
            tags.append(first.split(";", 1)[0].strip())
    if not tags:
        return None
    return locale_from_language_hints(*tags)


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
