"""POST audio to a self-hosted whisper.cpp HTTP service."""

from __future__ import annotations

import httpx

from medbuddy.protocols.ports import SpeechToTextPort


class WhisperHttpSTT(SpeechToTextPort):
    def __init__(self, *, base_url: str) -> None:
        self._url = base_url.rstrip("/") + "/transcribe"

    async def transcribe_m4a(self, audio: bytes) -> str:
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {"file": ("audio.m4a", audio, "audio/mp4")}
            r = await client.post(self._url, files=files)
            r.raise_for_status()
            data = r.json()
            return str(data.get("text") or data.get("transcript") or "").strip()
