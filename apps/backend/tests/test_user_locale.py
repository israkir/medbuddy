"""Unit tests for app UI locale normalization."""

from medbuddy.user_locale import (
    effective_user_locale,
    normalize_locale_patch,
    parse_locale_request_from_text,
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


def test_parse_locale_request_from_text_english() -> None:
    assert parse_locale_request_from_text("switch to English please") == "en"
    assert parse_locale_request_from_text("請用英文") == "en"
    assert parse_locale_request_from_text("改用英文回覆") == "en"


def test_parse_locale_request_from_text_chinese() -> None:
    assert parse_locale_request_from_text("switch to Traditional Chinese") == "zh-TW"
    assert parse_locale_request_from_text("請用中文") == "zh-TW"
    assert parse_locale_request_from_text("改回中文") == "zh-TW"


def test_parse_locale_request_from_text_not_switch() -> None:
    assert parse_locale_request_from_text("請用英文說明阿斯匹靈") is None
    assert parse_locale_request_from_text("what is aspirin") is None
