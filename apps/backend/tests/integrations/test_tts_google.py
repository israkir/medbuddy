from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from medbuddy.integrations.tts.tts_google import GoogleTextToSpeech, _normalize_language_code


def test_normalize_language_code_maps_short_en_to_en_us() -> None:
    assert _normalize_language_code("en") == "en-US"


def test_normalize_language_code_default_zh_tw_when_empty() -> None:
    assert _normalize_language_code("") == "zh-TW"


def test_google_tts_explicit_credentials_file_uses_service_account() -> None:
    storage = MagicMock()
    fake_creds = MagicMock(name="creds")
    with patch(
        "medbuddy.integrations.tts.tts_google.service_account.Credentials.from_service_account_file",
        return_value=fake_creds,
    ) as from_file:
        with patch(
            "medbuddy.integrations.tts.tts_google.texttospeech.TextToSpeechClient",
        ) as client_cls:
            GoogleTextToSpeech(
                storage=storage,
                credentials_path="/secrets/gcp-tts.json",
            )
    from_file.assert_called_once_with("/secrets/gcp-tts.json")
    client_cls.assert_called_once_with(credentials=fake_creds)


@pytest.mark.asyncio
async def test_google_tts_synthesize_uploads_and_returns_url() -> None:
    storage = MagicMock()
    storage.upload_temp_audio = AsyncMock(
        return_value="https://example.com/internal-media/abc.mp3",
    )

    fake_resp = MagicMock()
    fake_resp.audio_content = b"id3fake"

    with patch(
        "medbuddy.integrations.tts.tts_google.texttospeech.TextToSpeechClient",
    ) as client_cls:
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = fake_resp
        client_cls.return_value = mock_client

        tts = GoogleTextToSpeech(
            storage=storage,
            pinned_language_code=None,
            fallback_locale="zh-TW",
            voice_name="zh-TW-Neural2-A",
        )
        url, duration_ms = await tts.synthesize_to_m4a_url(
            "你好世界", "https://pub.example", language_code="zh-TW"
        )

    assert url == "https://example.com/internal-media/abc.mp3"
    assert duration_ms == max(1000, min(600_000, len("你好世界") * 120))
    storage.upload_temp_audio.assert_awaited_once()
    kwargs = storage.upload_temp_audio.await_args.kwargs
    assert kwargs["content_type"] == "audio/mpeg"
    assert kwargs["suffix"] == ".mp3"
    assert kwargs["data"] == b"id3fake"

    mock_client.synthesize_speech.assert_called_once()
    call_kw = mock_client.synthesize_speech.call_args.kwargs
    assert call_kw["input"].text == "你好世界"
    assert call_kw["voice"].language_code == "zh-TW"
    assert call_kw["voice"].name == "zh-TW-Neural2-A"
    assert call_kw["timeout"] == 60.0


@pytest.mark.asyncio
async def test_google_tts_uses_per_call_language_when_unpinned() -> None:
    storage = MagicMock()
    storage.upload_temp_audio = AsyncMock(
        return_value="https://example.com/internal-media/abc.mp3",
    )
    fake_resp = MagicMock()
    fake_resp.audio_content = b"x"

    with patch(
        "medbuddy.integrations.tts.tts_google.texttospeech.TextToSpeechClient",
    ) as client_cls:
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = fake_resp
        client_cls.return_value = mock_client

        tts = GoogleTextToSpeech(
            storage=storage,
            pinned_language_code=None,
            fallback_locale="zh-TW",
            voice_name=None,
        )
        await tts.synthesize_to_m4a_url("Hi", "https://pub.example", language_code="en")

    call_kw = mock_client.synthesize_speech.call_args.kwargs
    assert call_kw["voice"].language_code == "en-US"


@pytest.mark.asyncio
async def test_google_tts_pinned_language_overrides_per_call() -> None:
    storage = MagicMock()
    storage.upload_temp_audio = AsyncMock(
        return_value="https://example.com/internal-media/abc.mp3",
    )
    fake_resp = MagicMock()
    fake_resp.audio_content = b"x"

    with patch(
        "medbuddy.integrations.tts.tts_google.texttospeech.TextToSpeechClient",
    ) as client_cls:
        mock_client = MagicMock()
        mock_client.synthesize_speech.return_value = fake_resp
        client_cls.return_value = mock_client

        tts = GoogleTextToSpeech(
            storage=storage,
            pinned_language_code="zh-TW",
            fallback_locale="en-US",
            voice_name=None,
        )
        await tts.synthesize_to_m4a_url("Hi", "https://pub.example", language_code="en")

    call_kw = mock_client.synthesize_speech.call_args.kwargs
    assert call_kw["voice"].language_code == "zh-TW"
