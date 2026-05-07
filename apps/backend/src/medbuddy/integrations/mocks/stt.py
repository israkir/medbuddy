import asyncio

from medbuddy.core.i18n import t
from medbuddy.protocols import SpeechToTextPort


class MockSpeechToText(SpeechToTextPort):
    """Returns deterministic Traditional Chinese for tests."""

    def __init__(self, *, locale: str = "zh-TW", fixed_transcript: str | None = None) -> None:
        self.fixed_transcript = fixed_transcript or t("mocks.stt.default_transcript", locale=locale)
        self.last_audio_len = 0

    async def transcribe_m4a(self, audio: bytes, *, language_code: str | None = None) -> str:
        await asyncio.sleep(0)
        self.last_audio_len = len(audio)
        return self.fixed_transcript
