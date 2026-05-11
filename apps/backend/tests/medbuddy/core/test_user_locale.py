"""Unit tests for app UI locale normalization."""

from medbuddy.core.locale import (
    effective_user_locale,
    locale_from_client_language_headers,
    locale_from_language_hints,
    normalize_locale_patch,
)


def test_effective_user_locale_accepts_allowed() -> None:
    assert effective_user_locale("en") == "en"
    assert effective_user_locale("zh-TW") == "zh-TW"


def test_effective_user_locale_defaults() -> None:
    assert effective_user_locale(None) == "zh-TW"
    assert effective_user_locale("") == "zh-TW"
    assert effective_user_locale("fr") == "zh-TW"


def test_normalize_locale_patch() -> None:
    assert normalize_locale_patch(" en ") == "en"
    assert normalize_locale_patch("en") == "en"
    assert normalize_locale_patch(None) is None
    assert normalize_locale_patch("  ") is None


def test_locale_from_language_hints() -> None:
    assert locale_from_language_hints("en") == "en"
    assert locale_from_language_hints("en-US") == "en"
    assert locale_from_language_hints("zh-TW") == "zh-TW"
    assert locale_from_language_hints("zh-CN") == "zh-TW"
    assert locale_from_language_hints("ja") == "zh-TW"
    assert locale_from_language_hints() == "zh-TW"


def test_locale_from_client_language_headers() -> None:
    assert locale_from_client_language_headers(None, None) is None
    assert locale_from_client_language_headers("", "") is None
    assert locale_from_client_language_headers("en-AU", None) == "en"
    assert locale_from_client_language_headers(None, "en-GB;q=0.9, zh-TW;q=0.8") == "en"
    assert locale_from_client_language_headers(None, "ja-JP, en;q=0.5") == "zh-TW"
