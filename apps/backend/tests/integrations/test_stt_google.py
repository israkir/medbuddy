from medbuddy.integrations.stt.stt_google import _normalize_language_code


def test_normalize_language_code_maps_short_en_to_en_us() -> None:
    assert _normalize_language_code("en") == "en-US"


def test_normalize_language_code_preserves_region_tag() -> None:
    assert _normalize_language_code("en-GB") == "en-GB"


def test_normalize_language_code_normalizes_underscore_separator() -> None:
    assert _normalize_language_code("zh_TW") == "zh-TW"
