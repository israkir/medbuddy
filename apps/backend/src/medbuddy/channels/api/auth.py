"""Bearer authentication and app user identity for ``/v1/app/*`` (not LINE)."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from fastapi import Header, HTTPException

from medbuddy.config import get_settings

_APP_USER_ID_RE = re.compile(r"^[a-zA-Z0-9:_.-]{4,128}$")


@dataclass(frozen=True)
class MobileAuthContext:
    """Resolved identity for a standalone-app request."""

    app_user_id: str


async def require_mobile_auth(
    authorization: str | None = Header(None),
    x_app_user_id: str | None = Header(None, alias="X-App-User-Id"),
) -> MobileAuthContext:
    """Verify optional Bearer token (required in production) and require ``X-App-User-Id``."""
    settings = get_settings()
    expected = (settings.mobile_bearer_token or "").strip()

    if expected:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "missing_bearer",
                    "message": "Authorization: Bearer <token> required",
                },
            )
        got = authorization.removeprefix("Bearer ").strip()
        if not secrets.compare_digest(got, expected):
            raise HTTPException(status_code=401, detail={"code": "invalid_bearer"})
    elif not settings.is_mock:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "mobile_bearer_not_configured",
                "message": "Set MEDBUDDY_MOBILE_BEARER_TOKEN for standalone app API access",
            },
        )

    uid = (x_app_user_id or "").strip()
    if not uid or not _APP_USER_ID_RE.fullmatch(uid):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_app_user_id",
                "message": "Header X-App-User-Id required (4–128 chars: [a-zA-Z0-9:_.-])",
            },
        )
    return MobileAuthContext(app_user_id=uid)
