"""Supabase client factory."""

from __future__ import annotations

from typing import Any

from medbuddy.config import Settings
from medbuddy.core.errors import ConfigError


def _assert_supabase_secret_service_key(service_key: str) -> None:
    """Require the Supabase Data API **Secret** key (``sb_secret_...`` prefix only)."""
    sk = service_key.strip()
    if sk.startswith("sb_secret_"):
        return
    if sk.startswith("sb_publishable_"):
        raise ConfigError(
            "SUPABASE_SERVICE_KEY must be the backend Secret key (sb_secret_...), "
            "not the publishable key (sb_publishable_...)."
        )
    raise ConfigError(
        "SUPABASE_SERVICE_KEY must be the Supabase Secret API key "
        "(Dashboard → Project Settings → Data API), prefix sb_secret_."
    )


def create_supabase_client(settings: Settings) -> Any:
    """Build the Supabase sync client.

    postgrest-py defaults to ``httpx.Client(..., http2=True)``. HTTP/2 can raise
    ``RemoteProtocolError`` / ``ConnectionTerminated`` against some hosts or proxies;
    we use HTTP/1.1 for the shared httpx client instead.

    Requires ``SUPABASE_SERVICE_KEY`` (``sb_secret_...`` only). Publishable keys and
    legacy JWT keys are rejected at startup.
    """
    if not settings.supabase_service_key:
        raise ConfigError(
            "SUPABASE_SERVICE_KEY is required to build the Supabase client. "
            "Use the Secret key from Supabase (sb_secret_...)."
        )
    _assert_supabase_secret_service_key(settings.supabase_service_key)

    import httpx
    from postgrest.constants import DEFAULT_POSTGREST_CLIENT_TIMEOUT
    from supabase import ClientOptions, create_client

    http_client = httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(DEFAULT_POSTGREST_CLIENT_TIMEOUT),
        http2=False,
    )
    options = ClientOptions(httpx_client=http_client)
    return create_client(settings.supabase_url, settings.supabase_service_key, options)
