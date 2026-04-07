"""Send audio to Google Cloud Speech-to-Text V2 recognize API."""

from __future__ import annotations

import base64
import logging

import httpx

from medbuddy.protocols.ports import SpeechToTextPort

_STT_TIMEOUT_S = 120.0
log = logging.getLogger(__name__)


class GoogleSpeechToText(SpeechToTextPort):
    def __init__(
        self,
        *,
        api_key: str,
        project_id: str,
        location: str = "global",
        language_code: str = "zh-TW",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        loc = location.strip() or "global"
        self._url = (
            f"https://speech.googleapis.com/v2/projects/{project_id}/locations/{loc}"
            "/recognizers/_:recognize"
        )
        self._api_key = api_key
        self._language_code = language_code or "zh-TW"
        self._http = http_client

    async def transcribe_m4a(self, audio: bytes) -> str:
        audio_bytes = len(audio)
        log.info(
            "Google STT request start: audio_bytes=%d language=%s timeout_s=%.1f",
            audio_bytes,
            self._language_code,
            _STT_TIMEOUT_S,
        )
        payload = {
            "config": {
                "autoDecodingConfig": {},
                "languageCodes": [self._language_code],
                "model": "long",
            },
            "content": base64.b64encode(audio).decode("ascii"),
        }
        headers = {"x-goog-api-key": self._api_key}
        try:
            if self._http is not None:
                r = await self._http.post(
                    self._url, json=payload, headers=headers, timeout=_STT_TIMEOUT_S
                )
            else:
                async with httpx.AsyncClient(timeout=_STT_TIMEOUT_S) as client:
                    r = await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError:
            log.error(
                "Google STT request failed: audio_bytes=%d language=%s",
                audio_bytes,
                self._language_code,
                exc_info=True,
            )
            raise
        log.info(
            "Google STT response received: status_code=%d audio_bytes=%d",
            r.status_code,
            audio_bytes,
        )
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError:
            log.error(
                "Google STT non-success response: status_code=%d audio_bytes=%d",
                r.status_code,
                audio_bytes,
                exc_info=True,
            )
            raise
        data = r.json()
        results = data.get("results") or []
        parts: list[str] = []
        for item in results:
            alts = item.get("alternatives") or []
            if not alts:
                continue
            text = str(alts[0].get("transcript") or "").strip()
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
