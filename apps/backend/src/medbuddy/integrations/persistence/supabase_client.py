"""Supabase client factory."""

from __future__ import annotations

from typing import Any

from medbuddy.config import Settings


def create_supabase_client(settings: Settings) -> Any:
    """Build the Supabase sync client.

    postgrest-py defaults to ``httpx.Client(..., http2=True)``. HTTP/2 can raise
    ``RemoteProtocolError`` / ``ConnectionTerminated`` against some hosts or proxies;
    we use HTTP/1.1 for the shared httpx client instead.
    """
    import httpx
    from postgrest.constants import DEFAULT_POSTGREST_CLIENT_TIMEOUT
    from supabase import ClientOptions, create_client

    http_client = httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(DEFAULT_POSTGREST_CLIENT_TIMEOUT),
        http2=False,
    )
    options = ClientOptions(httpx_client=http_client)
    key = settings.supabase_service_key or settings.supabase_publishable_key
    return create_client(settings.supabase_url, key, options)
