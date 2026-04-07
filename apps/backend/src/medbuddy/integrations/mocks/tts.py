"""Deterministic short m4a clip for tests and mock integration mode."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from medbuddy.protocols.ports import TextToSpeechPort

log = logging.getLogger(__name__)

_SILENT_M4A = (Path(__file__).resolve().parent / "silent_reply.m4a").read_bytes()
_DURATION_MS = 250


class MockTextToSpeech(TextToSpeechPort):
    async def synthesize_m4a(self, text: str, *, language_code: str) -> tuple[bytes, int]:
        await asyncio.sleep(0)
        preview = (text[:80] + "…") if len(text) > 80 else text
        log.debug(
            "Mock TTS: locale=%s chars=%d preview=%r",
            language_code,
            len(text),
            preview,
        )
        return _SILENT_M4A, _DURATION_MS
