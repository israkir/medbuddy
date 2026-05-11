"""Acknowledgment copy for saved emergency contacts."""

from medbuddy.application.profile.emergency_contacts import emergency_contact_save_ack


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
