"""Transcribe audio with Google Cloud Speech-to-Text V2 client library."""

from __future__ import annotations

import asyncio
import logging

from google.api_core.client_options import ClientOptions
from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech

from medbuddy.protocols import SpeechToTextPort

_STT_TIMEOUT_S = 120.0
# Mandarin (Traditional, Taiwan) is not available as zh-TW + model long on global; Google lists
# cmn-Hant-TW with chirp in regions such as asia-southeast1 (see supported-languages V2 doc).
_DEFAULT_MANDARIN_TW_LOCATION = "asia-southeast1"
log = logging.getLogger(__name__)


def _normalize_language_code(language_code: str) -> str:
    """Map short locales to explicit BCP-47 tags used in-app (LINE/UI locale tags)."""
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

    # Keep caller-provided region/script tags, but normalize separator casing.
    return raw.replace("_", "-")


def _recognition_request_params(locale_tag: str, configured_location: str) -> tuple[str, str, str]:
    """Return (recognizer_location, model, language_codes[0]) for Speech-to-Text V2."""
    cfg = (configured_location or "").strip() or "global"
    lower = locale_tag.lower()
    if lower in ("zh-tw", "cmn-hant-tw"):
        rec_loc = cfg if cfg != "global" else _DEFAULT_MANDARIN_TW_LOCATION
        return rec_loc, "chirp", "cmn-Hant-TW"
    return cfg, "long", locale_tag


def _speech_client(recognizer_location: str) -> speech_v2.SpeechClient:
    if recognizer_location == "global":
        return speech_v2.SpeechClient()
    return speech_v2.SpeechClient(
        client_options=ClientOptions(
            api_endpoint=f"{recognizer_location}-speech.googleapis.com",
        ),
    )


class GoogleSpeechToText(SpeechToTextPort):
    def __init__(
        self,
        *,
        project_id: str,
        location: str = "global",
        language_code: str = "zh-TW",
    ) -> None:
        self._project_id = project_id
        self._configured_location = location.strip() or "global"
        self._language_code = language_code or "zh-TW"
        self._clients: dict[str, speech_v2.SpeechClient] = {}

    def _client_for(self, recognizer_location: str) -> speech_v2.SpeechClient:
        if recognizer_location not in self._clients:
            self._clients[recognizer_location] = _speech_client(recognizer_location)
        return self._clients[recognizer_location]

    async def transcribe_m4a(self, audio: bytes, *, language_code: str | None = None) -> str:
        audio_bytes = len(audio)
        locale_tag = _normalize_language_code(language_code or self._language_code)
        rec_loc, model, api_language = _recognition_request_params(
            locale_tag, self._configured_location
        )
        recognizer = f"projects/{self._project_id}/locations/{rec_loc}/recognizers/_"
        log.info(
            "Google STT request start: audio_bytes=%d locale=%s api_language=%s "
            "model=%s location=%s timeout_s=%.1f",
            audio_bytes,
            locale_tag,
            api_language,
            model,
            rec_loc,
            _STT_TIMEOUT_S,
        )
        request = cloud_speech.RecognizeRequest(
            recognizer=recognizer,
            config=cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=[api_language],
                model=model,
            ),
            content=audio,
        )
        client = self._client_for(rec_loc)
        try:
            resp = await asyncio.to_thread(
                client.recognize,
                request=request,
                timeout=_STT_TIMEOUT_S,
            )
        except Exception:
            log.error(
                "Google STT request failed: audio_bytes=%d locale=%s api_language vb=%s model=%s location=%s",
                audio_bytes,
                locale_tag,
                api_language,
                model,
                rec_loc,
                exc_info=True,
            )
            raise
        log.info("Google STT response received: audio_bytes=%d", audio_bytes)
        results = list(resp.results or [])
        parts: list[str] = []
        for item in results:
            alts = list(item.alternatives or [])
            if not alts:
                continue
            text = str(alts[0].transcript or "").strip()
            if text:
                parts.append(text)
        transcript = " ".join(parts).strip()
        if transcript:
            log.info(
                "Google STT transcription complete: segments=%d transcript_chars=%d",
                len(parts),
                len(transcript),
            )
        else:
            log.warning(
                "Google STT transcription empty: results=%d audio_bytes=%d",
                len(results),
                audio_bytes,
            )
        return transcript
