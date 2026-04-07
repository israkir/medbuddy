"""FastAPI entry: mounts LINE webhook, standalone app API, and shared infrastructure routes."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from medbuddy.channels.line.routes import router as line_router
from medbuddy.channels.mobile.routes import router as mobile_router
from medbuddy.config import get_settings
from medbuddy.container import build_app_services
from medbuddy.http.shared_routes import router as shared_router
from medbuddy.logging_config import configure_logging

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    outbound_http: httpx.AsyncClient | None = None
    stt_http: httpx.AsyncClient | None = None
    if not settings.mock_external_services:
        outbound_http = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
        stt_http = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
    try:
        app.state.services = build_app_services(
            settings,
            outbound_http=outbound_http,
            stt_http=stt_http,
        )
        log.info(
            "MedBuddy started mock_external=%s locale=%s log_level=%s public_base_url=%s",
            settings.mock_external_services,
            settings.locale,
            settings.log_level,
            settings.public_base_url,
        )
        yield
    finally:
        if outbound_http is not None:
            await outbound_http.aclose()
        if stt_http is not None:
            await stt_http.aclose()


app = FastAPI(
    title="MedBuddy API",
    description=(
        "LINE Messaging API webhooks and HTTP for the standalone mobile app; "
        "shared services from container wiring (integrations, engine types)."
    ),
    lifespan=lifespan,
)

app.include_router(shared_router)
app.include_router(line_router)
app.include_router(mobile_router)
