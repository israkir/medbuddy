"""FastAPI entry: mounts LINE webhook, standalone app API, and shared infrastructure routes."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from medbuddy.channels.api.routes import router as api_router
from medbuddy.channels.internal.routes import router as internal_router
from medbuddy.channels.line.routes import router as line_router
from medbuddy.config import get_settings
from medbuddy.container import build_app_services
from medbuddy.core.logging import configure_logging

log = logging.getLogger(__name__)

# Per-request correlation ID — set by RequestIdMiddleware, read by the exception handler.
_request_id: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        rid = str(uuid.uuid4())
        _request_id.set(rid)
        response = await call_next(request)
        response.headers["X-Request-Id"] = rid
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    outbound_http: httpx.AsyncClient | None = None
    if not settings.is_mock:
        outbound_http = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )
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

app.add_middleware(RequestIdMiddleware)

_settings = get_settings()
if _settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_settings.cors_allowed_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-App-User-Id", "X-MedBuddy-Locale"],
        allow_credentials=False,
    )

app.include_router(internal_router)
app.include_router(line_router)
app.include_router(api_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    rid = _request_id.get("")
    log.exception("Unhandled exception request_id=%s path=%s", rid, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": "internal_error", "request_id": rid},
    )
