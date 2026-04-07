"""In-process public URLs for prototypes without Supabase (not for multi-instance)."""

from __future__ import annotations

import asyncio
import uuid

from medbuddy.protocols.ports import InternalMediaPort, ObjectStoragePort

_FILES: dict[str, bytes] = {}


def get_file(file_id: str) -> bytes | None:
    return _FILES.get(file_id)


class LocalPublicObjectStorage(ObjectStoragePort, InternalMediaPort):
    """Stores bytes in memory; URLs must be served by the API (`/internal-media/{id}`)."""

    def __init__(self, *, public_base_url: str) -> None:
        self._public_base_url = public_base_url.rstrip("/")

    async def get_blob(self, file_id: str) -> bytes | None:
        await asyncio.sleep(0)
        return get_file(file_id)

    async def upload_temp_audio(
        self,
        *,
        data: bytes,
        content_type: str,
        suffix: str,
    ) -> str:
        await asyncio.sleep(0)
        _ = content_type
        fid = f"{uuid.uuid4().hex}{suffix}"
        _FILES[fid] = data
        return f"{self._public_base_url}/internal-media/{fid}"

    async def delete_object(self, public_url: str) -> None:
        await asyncio.sleep(0)
        if "/internal-media/" not in public_url:
            return
        fid = public_url.rsplit("/internal-media/", 1)[-1]
        _FILES.pop(fid, None)
