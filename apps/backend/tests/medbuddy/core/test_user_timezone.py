"""Tests for IANA timezone helpers."""

from medbuddy.core.timezone import (
    DEFAULT_USER_TIMEZONE,
    effective_user_timezone,
    is_valid_iana_timezone,
    normalize_timezone_patch,
)


def test_effective_default() -> None:
    assert effective_user_timezone(None) == DEFAULT_USER_TIMEZONE
    assert effective_user_timezone("") == DEFAULT_USER_TIMEZONE
    assert effective_user_timezone("not_a_zone") == DEFAULT_USER_TIMEZONE


def test_effective_valid() -> None:
    assert effective_user_timezone("America/New_York") == "America/New_York"


def test_is_valid() -> None:
    assert is_valid_iana_timezone("Asia/Taipei") is True
    assert is_valid_iana_timezone("") is False
    assert is_valid_iana_timezone("Mars/Phobos") is False


def test_normalize_patch() -> None:
    assert normalize_timezone_patch(None) is None
    assert normalize_timezone_patch("  America/Los_Angeles  ") == "America/Los_Angeles"
    assert normalize_timezone_patch("bad") is None
