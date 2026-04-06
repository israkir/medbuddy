"""HTTP routes for the Expo/React Native client (not LINE webhooks)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Depends, HTTPException, Response

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.channels.mobile.auth import MobileAuthContext, require_mobile_auth
from medbuddy.channels.mobile.schemas import ConsentBody, MeResponse, MessageCreate, MessageReply
from medbuddy.deps import get_services
from medbuddy.engine.types import AppServices

router = APIRouter(prefix="/v1/app", tags=["standalone-app"])


def _package_version() -> str:
    try:
        return version("medbuddy-api")
    except PackageNotFoundError:
        return "unknown"


@router.get("/health")
async def app_health() -> dict[str, str]:
    """JSON health for mobile clients and load checks (distinct from plain ``GET /health``)."""
    return {"status": "ok", "channel": "standalone"}


@router.get("/info")
async def app_info() -> dict[str, str]:
    """Capability metadata for the standalone app channel."""
    return {
        "channel": "standalone",
        "api_version": _package_version(),
    }


@router.get("/me", response_model=MeResponse)
async def app_me(
    ctx: MobileAuthContext = Depends(require_mobile_auth),
    svc: AppServices = Depends(get_services),
) -> MeResponse:
    """Current app user profile (backed by the same user store key as LINE ``userId``-style ids)."""
    u = await svc.users.get_or_create_user(ctx.app_user_id)
    return MeResponse(
        app_user_id=ctx.app_user_id,
        consent_accepted=bool(u.get("consent_accepted")),
    )


@router.post("/consent", status_code=204)
async def app_consent(
    body: ConsentBody,
    ctx: MobileAuthContext = Depends(require_mobile_auth),
    svc: AppServices = Depends(get_services),
) -> Response:
    """Record consent for this app user (required before ``POST /messages``)."""
    await svc.users.set_consent(ctx.app_user_id, body.accepted)
    return Response(status_code=204)


@router.post("/messages", response_model=MessageReply)
async def app_post_message(
    body: MessageCreate,
    ctx: MobileAuthContext = Depends(require_mobile_auth),
    svc: AppServices = Depends(get_services),
) -> MessageReply:
    """Run one assistant turn (same core logic as LINE text messages)."""
    u = await svc.users.get_or_create_user(ctx.app_user_id)
    if not u.get("consent_accepted"):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "consent_required",
                "message": "Accept consent via POST /v1/app/consent first",
            },
        )
    reply = await run_assistant_text_turn(
        svc,
        user_key=ctx.app_user_id,
        user_text=body.text,
    )
    return MessageReply(reply=reply)
