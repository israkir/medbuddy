from medbuddy.integrations.stt.stt_google import (
    _normalize_language_code,
    _recognition_request_params,
)


def test_normalize_language_code_maps_short_en_to_en_us() -> None:
    assert _normalize_language_code("en") == "en-US"


def test_normalize_language_code_preserves_region_tag() -> None:
    assert _normalize_language_code("en-GB") == "en-GB"


def test_normalize_language_code_normalizes_underscore_separator() -> None:
    assert _normalize_language_code("zh_TW") == "zh-TW"


def test_recognition_params_zh_tw_global_uses_chirp_asia_southeast1() -> None:
    loc, model, lang = _recognition_request_params("zh-TW", "global")
    assert loc == "asia-southeast1"
    assert model == "chirp"
    assert lang == "cmn-Hant-TW"


def test_recognition_params_zh_tw_respects_non_global_config() -> None:
    loc, model, lang = _recognition_request_params("zh-TW", "us-central1")
    assert loc == "us-central1"
    assert model == "chirp"
    assert lang == "cmn-Hant-TW"


def test_recognition_params_en_us_global_uses_long() -> None:
    loc, model, lang = _recognition_request_params("en-US", "global")
    assert loc == "global"
    assert model == "long"
    assert lang == "en-US"
