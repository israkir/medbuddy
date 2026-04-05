from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from medbuddy.config import get_settings
from medbuddy.container import build_app_services
from medbuddy.core.line_signature import verify_line_signature
from medbuddy.engine.orchestrator import handle_line_event
from medbuddy.engine.types import AppServices
from medbuddy.integrations.real.local_public_storage import get_file

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.services = build_app_services(settings)
    log.info("MedBuddy started mock_external=%s", settings.mock_external_services)
    yield


app = FastAPI(title="MedBuddy", lifespan=lifespan)


def services(request: Request) -> AppServices:
    return request.app.state.services


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    return "ok"


@app.get("/internal-media/{file_id:path}")
async def internal_media(file_id: str) -> Response:
    data = get_file(file_id)
    if data is None:
        raise HTTPException(status_code=404)
    return Response(content=data, media_type="application/octet-stream")


@app.post("/v1/line/webhook")
async def line_webhook(
    request: Request,
    svc: AppServices = Depends(services),
) -> dict[str, str]:
    settings = get_settings()
    raw = await request.body()
    sig = request.headers.get("X-Line-Signature")

    if settings.mock_external_services and not settings.line_channel_secret:
        log.debug("Skipping LINE signature verification (mock without secret)")
    elif not verify_line_signature(
        body=raw,
        channel_secret=settings.line_channel_secret,
        signature_header=sig,
    ):
        raise HTTPException(status_code=401, detail="invalid signature")

    try:
        body = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="invalid json") from e

    for event in body.get("events") or []:
        await handle_line_event(event, svc)

    return {"status": "ok"}
