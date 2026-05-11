"""Acknowledgment copy for saved emergency contacts."""

from medbuddy.application.profile.emergency_contacts import (
    emergency_contact_save_ack,
    emergency_contacts_redacted_hint,
)


def test_emergency_contact_ack_rel_name_phone_en() -> None:
    rows = [
        {
            "channel_type": "phone",
            "channel_value": "0912345678",
            "is_primary": True,
            "relationship": "daughter",
            "contact_name": "Kathy",
        }
    ]
    msg = emergency_contact_save_ack(rows, locale="en")
    assert "daughter" in msg
    assert "Kathy" in msg
    assert "phone" in msg
    assert "0912345678" in msg
    assert "primary emergency contact" in msg


def test_emergency_contact_ack_multi_uses_primary_en() -> None:
    rows = [
        {
            "channel_type": "phone",
            "channel_value": "0900000000",
            "is_primary": False,
            "relationship": "son",
            "contact_name": "Dan",
        },
        {
            "channel_type": "phone",
            "channel_value": "0911111111",
            "is_primary": True,
            "relationship": "daughter",
            "contact_name": "Kathy",
        },
    ]
    msg = emergency_contact_save_ack(rows, locale="en")
    assert "2 emergency contacts" in msg
    assert "Kathy" in msg
    assert "Dan" not in msg


def test_emergency_contact_ack_zh_tw_fullwidth_detail() -> None:
    rows = [
        {
            "channel_type": "phone",
            "channel_value": "0912345678",
            "is_primary": True,
            "relationship": "女兒",
            "contact_name": "Kathy",
        }
    ]
    msg = emergency_contact_save_ack(rows, locale="zh-TW")
    assert "0912345678" in msg
    assert "（0912345678）" in msg
    assert "主要" in msg


# ---------------------------------------------------------------------------
# Tests for emergency_contacts_redacted_hint (tokenised LLM hint)
# ---------------------------------------------------------------------------


def test_redacted_hint_empty_when_no_contacts() -> None:
    hint, token_map = emergency_contacts_redacted_hint([], locale="en")
    assert hint == ""
    assert token_map == {}


def test_redacted_hint_single_contact_en() -> None:
    rows = [
        {
            "channel_type": "phone",
            "channel_value": "0912345678",
            "is_primary": True,
            "relationship": "daughter",
        }
    ]
    hint, token_map = emergency_contacts_redacted_hint(rows, locale="en")
    assert "[EMERGENCY_CONTACT_1]" in hint
    assert "0912345678" not in hint, "PII must not appear in the hint block"
    assert "phone" in hint
    assert "daughter" in hint
    assert token_map["[EMERGENCY_CONTACT_1]"] == "daughter 0912345678"


def test_redacted_hint_multi_contacts_token_map() -> None:
    rows = [
        {
            "channel_type": "phone",
            "channel_value": "0900000000",
            "is_primary": True,
            "relationship": "son",
        },
        {
            "channel_type": "line",
            "channel_value": "john_line",
            "is_primary": False,
            "relationship": "friend",
        },
    ]
    hint, token_map = emergency_contacts_redacted_hint(rows, locale="en")
    assert "[EMERGENCY_CONTACT_1]" in hint
    assert "[EMERGENCY_CONTACT_2]" in hint
    assert "0900000000" not in hint
    assert "john_line" not in hint
    assert len(token_map) == 2
    assert token_map["[EMERGENCY_CONTACT_1]"] == "son 0900000000"
    assert token_map["[EMERGENCY_CONTACT_2]"] == "friend john_line"


def test_redacted_hint_zh_tw() -> None:
    rows = [
        {
            "channel_type": "phone",
            "channel_value": "0912345678",
            "is_primary": True,
            "relationship": "女兒",
        }
    ]
    hint, token_map = emergency_contacts_redacted_hint(rows, locale="zh-TW")
    assert "[EMERGENCY_CONTACT_1]" in hint
    assert "0912345678" not in hint
    assert token_map["[EMERGENCY_CONTACT_1]"] == "女兒 0912345678"
