"""Speech-to-text and text-to-speech interfaces."""

from __future__ import annotations

from typing import Protocol


class SpeechToTextPort(Protocol):
    async def transcribe_m4a(self, audio: bytes, *, language_code: str | None = None) -> str: ...


class TextToSpeechPort(Protocol):
    """Synthesize assistant reply audio for LINE (m4a AAC in an MP4 container)."""

    async def synthesize_m4a(self, text: str, *, language_code: str) -> tuple[bytes, int]:
        """Return ``(m4a_bytes, duration_ms)`` for use in LINE audio messages."""
        ...
