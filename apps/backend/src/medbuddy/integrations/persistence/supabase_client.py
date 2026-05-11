"""Supabase client factory."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from medbuddy.config import Settings
from medbuddy.core.errors import ConfigError


def _jwt_payload_dict(token: str) -> dict[str, Any] | None:
    """Decode JWT payload (middle segment) without verifying the signature."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload_b64 = parts[1]
    pad = (-len(payload_b64)) % 4
    if pad:
        payload_b64 += "=" * pad
    try:
        raw = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        obj = json.loads(raw)
    except (ValueError, json.JSONDecodeError, binascii.Error):
        return None
    return obj if isinstance(obj, dict) else None


def _assert_supabase_service_jwt_role(service_key: str) -> None:
    """Fail fast if ``SUPABASE_SERVICE_KEY`` is not the service_role JWT.

    After ``revoke all on public.patients from anon, authenticated``, using the
    publishable key yields PostgREST ``42501 permission denied for table patients``.

    Keys with three JWT segments must decode and declare ``role`` exactly
    ``service_role``. Anything else (anon, authenticated, missing role, or
    undecodable payload) raises at startup instead of failing on first DB call.
    """
    parts = service_key.split(".")
    if len(parts) != 3:
        return
    payload = _jwt_payload_dict(service_key)
    if not payload:
        raise ConfigError(
            "SUPABASE_SERVICE_KEY looks like a JWT (three segments) but the payload "
            "could not be decoded. Check for truncation, whitespace, or copy/paste errors."
        )
    role = payload.get("role")
    if role != "service_role":
        raise ConfigError(
            "SUPABASE_SERVICE_KEY must be the service_role secret from Supabase "
            "(Dashboard → Project Settings → API), not the anon/publishable key or "
            f"another JWT role. Decoded JWT role is {role!r}; expected 'service_role'."
        )


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
    _assert_supabase_service_jwt_role(settings.supabase_service_key)

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
