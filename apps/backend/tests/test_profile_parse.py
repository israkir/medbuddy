"""Local profile parsing (no LLM)."""

from medbuddy.privacy.profile_parse import parse_profile_patch_from_text


def test_parse_zh_name_and_age() -> None:
    p = parse_profile_patch_from_text("我叫陳阿姨，今年72歲")
    assert p.get("preferred_name") == "陳阿姨"
    assert p.get("age_years") == 72


def test_parse_contact_and_notes_zh() -> None:
    p = parse_profile_patch_from_text("手機：0912-111-222 過敏：青黴素")
    assert "0912" in (p.get("emergency_contact") or "")
    assert "青黴素" in (p.get("health_notes") or "")
