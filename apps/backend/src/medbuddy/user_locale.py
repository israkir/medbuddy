"""App UI locale for standalone users (BCP 47 tags supported by the Expo client)."""

from __future__ import annotations

import re
import unicodedata

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


def parse_locale_request_from_text(user_text: str) -> str | None:
    """If the user clearly asks to switch reply/UI language, return ``en`` or ``zh-TW``.

    Conservative: avoids matching mixed requests like “請用英文說明…” (explain in English).
    """
    raw = unicodedata.normalize("NFKC", user_text or "").strip()
    if not raw:
        return None
    # “Explain this in English” — not a UI locale switch
    if re.search(r"請用英文\s*(?:說明|解釋|翻譯|介紹|告訴)", raw):
        return None
    if re.search(r"(?i)in\s+english.+(?:explain|translate|describe|tell\s+me)", raw):
        return None

    en_patterns = (
        r"(?i)\b(?:switch|change)\s+(?:the\s+)?(?:reply\s+)?language\s+to\s+english\b",
        r"(?i)\b(?:switch|change)\s+to\s+english\b",
        r"(?i)\b(?:use|speak|talk|reply|answer)\s+(?:in\s+)?english\b",
        r"(?i)\blanguage\s*:\s*english\b",
        r"請用英文",
        r"改用英文",
        r"切換(?:成|到|為)?英文",
        r"用英文(?:回覆|回答|說話|聊天)",
        r"改(?:成|為)英文",
    )
    zh_patterns = (
        r"(?i)\b(?:switch|change)\s+(?:to\s+)?(?:traditional\s+chinese|zh[- ]?tw)\b",
        r"(?i)\b(?:use|speak|reply)\s+(?:in\s+)?(?:traditional\s+chinese|mandarin)\b",
        r"請用中文",
        r"改用中文",
        r"切換(?:成|到|為)?(?:繁體)?中文",
        r"用中文(?:回覆|回答|說話|聊天)",
        r"改(?:成|為)中文",
        r"改回中文",
    )

    for p in en_patterns:
        if re.search(p, raw):
            return "en"
    for p in zh_patterns:
        if re.search(p, raw):
            return "zh-TW"
    return None
