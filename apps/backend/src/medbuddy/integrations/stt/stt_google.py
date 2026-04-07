"""Transcribe audio with Google Cloud Speech-to-Text V2 client library."""

from __future__ import annotations

import asyncio
import logging

from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech

from medbuddy.protocols.ports import SpeechToTextPort

_STT_TIMEOUT_S = 120.0
log = logging.getLogger(__name__)


def _normalize_language_code(language_code: str) -> str:
    """Map short locales to explicit BCP-47 tags accepted by Google STT."""
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


class GoogleSpeechToText(SpeechToTextPort):
    def __init__(
        self,
        *,
        project_id: str,
        location: str = "global",
        language_code: str = "zh-TW",
    ) -> None:
        loc = location.strip() or "global"
        self._recognizer = f"projects/{project_id}/locations/{loc}/recognizers/_"
        self._language_code = language_code or "zh-TW"
        self._client = speech_v2.SpeechClient()

    async def transcribe_m4a(self, audio: bytes, *, language_code: str | None = None) -> str:
        audio_bytes = len(audio)
        req_language = _normalize_language_code(language_code or self._language_code)
        log.info(
            "Google STT request start: audio_bytes=%d language=%s timeout_s=%.1f",
            audio_bytes,
            req_language,
            _STT_TIMEOUT_S,
        )
        request = cloud_speech.RecognizeRequest(
            recognizer=self._recognizer,
            config=cloud_speech.RecognitionConfig(
                auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
                language_codes=[req_language],
                model="long",
            ),
            content=audio,
        )
        try:
            resp = await asyncio.to_thread(
                self._client.recognize,
                request=request,
                timeout=_STT_TIMEOUT_S,
            )
        except Exception:
            log.error(
                "Google STT request failed: audio_bytes=%d language=%s",
                audio_bytes,
                req_language,
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
