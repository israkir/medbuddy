import asyncio

from medbuddy.protocols.ports import ObjectStoragePort, TextToSpeechPort


class MockTextToSpeech(TextToSpeechPort):
    """Uploads placeholder bytes so storage TTL/delete paths are exercised."""

    def __init__(self, storage: ObjectStoragePort) -> None:
        self._storage = storage
        self.last_text: str | None = None

    async def synthesize_to_m4a_url(self, text: str, base_public_url: str) -> tuple[str, int]:
        await asyncio.sleep(0)
        self.last_text = text
        url = await self._storage.upload_temp_audio(
            data=b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2",
            content_type="audio/mp4",
            suffix=".m4a",
        )
        _ = base_public_url
        return url, 3500
