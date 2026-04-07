"""Unit tests for app UI locale normalization."""

from medbuddy.user_locale import effective_user_locale, normalize_locale_patch


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
