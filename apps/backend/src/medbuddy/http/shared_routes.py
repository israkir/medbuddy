"""Infrastructure routes used by more than one channel (e.g. LINE audio URLs)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import PlainTextResponse

from medbuddy.integrations.local_public_storage import get_file

router = APIRouter(tags=["infrastructure"])


@router.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@router.get("/internal-media/{file_id:path}")
async def internal_media(file_id: str) -> Response:
    data = get_file(file_id)
    if data is None:
        raise HTTPException(status_code=404)
    return Response(content=data, media_type="application/octet-stream")
