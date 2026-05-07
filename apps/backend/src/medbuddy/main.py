"""FastAPI entry: mounts LINE webhook, standalone app API, and shared infrastructure routes."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from medbuddy.channels.api.routes import router as api_router
from medbuddy.channels.internal.routes import router as internal_router
from medbuddy.channels.line.routes import router as line_router
from medbuddy.config import get_settings
from medbuddy.container import build_app_services
from medbuddy.core.logging import configure_logging

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    outbound_http: httpx.AsyncClient | None = None
    if not settings.is_mock:
        outbound_http = httpx.AsyncClient(timeout=httpx.Timeout(20.0))
    try:
        app.state.services = build_app_services(
            settings,
            outbound_http=outbound_http,
        )
        line_client_name = app.state.services.line.__class__.__name__
        log.info(
            "MedBuddy started mock_external=%s line_client=%s locale=%s log_level=%s public_base_url=%s",
            settings.is_mock,
            line_client_name,
            settings.locale,
            settings.log_level,
            settings.public_base_url,
        )
        yield
    finally:
        if outbound_http is not None:
            await outbound_http.aclose()


app = FastAPI(
    title="MedBuddy API",
    description=(
        "LINE Messaging API webhooks and HTTP for the standalone mobile app; "
        "shared services from container wiring (integrations, engine types)."
    ),
    lifespan=lifespan,
)

app.include_router(internal_router)
app.include_router(line_router)
app.include_router(api_router)
