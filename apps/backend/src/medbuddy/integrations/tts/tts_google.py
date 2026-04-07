"""Synthesize speech with Google Cloud Text-to-Speech; upload via ObjectStoragePort."""

from __future__ import annotations

import asyncio
import logging

from google.cloud import texttospeech_v1 as texttospeech
from google.oauth2 import service_account

from medbuddy.protocols.ports import ObjectStoragePort, TextToSpeechPort

_TTS_TIMEOUT_S = 60.0
log = logging.getLogger(__name__)


def _tts_client(credentials_path: str | None) -> texttospeech.TextToSpeechClient:
    """Use a dedicated key file when set; otherwise Application Default Credentials."""
    path = (credentials_path or "").strip()
    if path:
        creds = service_account.Credentials.from_service_account_file(path)
        return texttospeech.TextToSpeechClient(credentials=creds)
    return texttospeech.TextToSpeechClient()


def _normalize_language_code(language_code: str) -> str:
    """Map short locales to BCP-47 tags for Google TTS."""
    raw = (language_code or "").strip()
    if not raw:
        return "zh-TW"

    lower = raw.lower()
    aliases = {
        "en": "en-US",
        "zh": "zh-TW",
    }
    if lower in aliases:
        return aliases[lower]

    return raw.replace("_", "-")


class GoogleTextToSpeech(TextToSpeechPort):
    """If ``pinned_language_code`` is set (``GOOGLE_TTS_LANGUAGE_CODE``), it wins for every call.

    Otherwise each synthesis uses ``language_code`` from the caller (e.g. LINE user's profile
    locale), then ``fallback_locale`` (``MEDBUDDY_LOCALE``).
    """

    def __init__(
        self,
        *,
        storage: ObjectStoragePort,
        pinned_language_code: str | None = None,
        fallback_locale: str = "zh-TW",
        voice_name: str | None = None,
        credentials_path: str | None = None,
    ) -> None:
        self._storage = storage
        pin = (pinned_language_code or "").strip()
        self._pinned_language_code = pin or None
        self._fallback_locale = (fallback_locale or "").strip() or "zh-TW"
        self._voice_name = voice_name.strip() if voice_name and voice_name.strip() else None
        self._client = _tts_client(credentials_path)

    def _resolve_language(self, language_code: str | None) -> str:
        if self._pinned_language_code is not None:
            return _normalize_language_code(self._pinned_language_code)
        if language_code and str(language_code).strip():
            return _normalize_language_code(str(language_code))
        return _normalize_language_code(self._fallback_locale)

    async def synthesize_to_m4a_url(
        self,
        text: str,
        base_public_url: str,
        *,
        language_code: str | None = None,
    ) -> tuple[str, int]:
        _ = base_public_url
        trimmed = (text or "").strip()
        if not trimmed:
            trimmed = " "

        lang = self._resolve_language(language_code)
        voice_kw: dict[str, str] = {"language_code": lang}
        if self._voice_name:
            voice_kw["name"] = self._voice_name

        synthesis_input = texttospeech.SynthesisInput(text=trimmed)
        voice_params = texttospeech.VoiceSelectionParams(**voice_kw)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        )

        log.info(
            "Google TTS request start: chars=%d language=%s voice=%s timeout_s=%.1f",
            len(trimmed),
            lang,
            self._voice_name or "(default)",
            _TTS_TIMEOUT_S,
        )

        def _sync_call():
            return self._client.synthesize_speech(
                input=synthesis_input,
                voice=voice_params,
                audio_config=audio_config,
                timeout=_TTS_TIMEOUT_S,
            )

        try:
            response = await asyncio.to_thread(_sync_call)
        except Exception:
            log.error(
                "Google TTS request failed: chars=%d language=%s",
                len(trimmed),
                lang,
                exc_info=True,
            )
            raise

        data = bytes(response.audio_content or b"")
        if not data:
            log.warning("Google TTS returned empty audio: chars=%d", len(trimmed))

        url = await self._storage.upload_temp_audio(
            data=data,
            content_type="audio/mpeg",
            suffix=".mp3",
        )
        duration_ms = max(1000, min(600_000, len(trimmed) * 120))
        log.info("Google TTS complete: url_chars=%d audio_bytes=%d", len(url), len(data))
        return url, duration_ms
