"""Supabase client factory."""

from __future__ import annotations

from typing import Any

from medbuddy.config import Settings
from medbuddy.core.errors import ConfigError


def create_supabase_client(settings: Settings) -> Any:
    """Build the Supabase sync client.

    postgrest-py defaults to ``httpx.Client(..., http2=True)``. HTTP/2 can raise
    ``RemoteProtocolError`` / ``ConnectionTerminated`` against some hosts or proxies;
    we use HTTP/1.1 for the shared httpx client instead.

    Requires ``supabase_service_key`` — falling back to the publishable/anon key is
    never allowed because all tables deny the ``anon`` / ``authenticated`` roles.
    """
    if not settings.supabase_service_key:
        raise ConfigError(
            "SUPABASE_SERVICE_KEY is required to build the Supabase client. "
            "Falling back to the publishable key is not allowed — RLS blocks "
            "service operations for the anon/authenticated roles."
        )

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
