"""POST audio to a self-hosted whisper.cpp HTTP service."""

from __future__ import annotations

import httpx

from medbuddy.protocols.ports import SpeechToTextPort

_STT_TIMEOUT_S = 120.0


class WhisperHttpSTT(SpeechToTextPort):
    def __init__(
        self,
        *,
        base_url: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/transcribe"
        self._http = http_client

    async def transcribe_m4a(self, audio: bytes) -> str:
        files = {"file": ("audio.m4a", audio, "audio/mp4")}
        if self._http is not None:
            r = await self._http.post(self._url, files=files, timeout=_STT_TIMEOUT_S)
        else:
            async with httpx.AsyncClient(timeout=_STT_TIMEOUT_S) as client:
                r = await client.post(self._url, files=files)
        r.raise_for_status()
        data = r.json()
        return str(data.get("text") or data.get("transcript") or "").strip()
