import asyncio
from urllib.parse import urlparse

from medbuddy.protocols.ports import ObjectStoragePort


class MockObjectStorage(ObjectStoragePort):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def upload_temp_audio(self, *, data: bytes, content_type: str, suffix: str) -> str:
        await asyncio.sleep(0)
        key = f"tmp/{len(self.objects)}{suffix}"
        url = f"https://mock-storage.example/{key}"
        self.objects[url] = data
        _ = content_type
        return url

    async def delete_object(self, public_url: str) -> None:
        await asyncio.sleep(0)
        self.deleted.append(public_url)
        self.objects.pop(public_url, None)
        # also strip host for tests
        path = urlparse(public_url).path
        for k in list(self.objects):
            if path in k:
                self.objects.pop(k, None)
