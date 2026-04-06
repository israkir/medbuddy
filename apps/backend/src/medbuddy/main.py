"""FastAPI entry: mounts LINE webhook, standalone app API, and shared infrastructure routes."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from medbuddy.channels.line.routes import router as line_router
from medbuddy.channels.mobile.routes import router as mobile_router
from medbuddy.config import get_settings
from medbuddy.container import build_app_services
from medbuddy.http.shared_routes import router as shared_router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.services = build_app_services(settings)
    log.info("MedBuddy started mock_external=%s", settings.mock_external_services)
    yield


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
