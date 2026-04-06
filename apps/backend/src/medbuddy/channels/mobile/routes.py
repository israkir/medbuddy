"""HTTP routes for the Expo/React Native client (not LINE webhooks)."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from fastapi import APIRouter, Depends

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.channels.mobile.auth import MobileAuthContext, require_mobile_auth
from medbuddy.channels.mobile.schemas import (
    MeResponse,
    MessageCreate,
    MessageReply,
    OnboardingSubmit,
)
from medbuddy.deps import get_services
from medbuddy.engine.types import AppServices

router = APIRouter(prefix="/v1/app", tags=["standalone-app"])


def _onboarding_ts_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        at = value if value.tzinfo else value.replace(tzinfo=UTC)
        return at.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


def _me_response(app_user_id: str, row: dict[str, Any]) -> MeResponse:
    g = row.get("gender")
    gender_str = g if isinstance(g, str) and g.strip() else None
    return MeResponse(
        app_user_id=app_user_id,
        preferred_name=row.get("preferred_name"),
        age_years=row.get("age_years"),
        gender=gender_str,
        emergency_contact=row.get("emergency_contact"),
        health_notes=row.get("health_notes"),
        onboarding_completed_at=_onboarding_ts_iso(row.get("onboarding_completed_at")),
    )


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
    row = await svc.users.get_or_create_user(ctx.app_user_id)
    return _me_response(ctx.app_user_id, row)


@router.post("/onboarding", response_model=MeResponse)
async def app_complete_onboarding(
    body: OnboardingSubmit,
    ctx: MobileAuthContext = Depends(require_mobile_auth),
    svc: AppServices = Depends(get_services),
) -> MeResponse:
    """Save first-run onboarding answers (name, age, gender, optional notes and family contact)."""
    row = await svc.users.save_onboarding_profile(
        ctx.app_user_id,
        preferred_name=body.preferred_name,
        age_years=body.age_years,
        gender=body.gender.value if body.gender is not None else None,
        emergency_contact=body.emergency_contact,
        health_notes=body.health_notes,
    )
    return _me_response(ctx.app_user_id, row)


@router.post("/messages", response_model=MessageReply)
async def app_post_message(
    body: MessageCreate,
    ctx: MobileAuthContext = Depends(require_mobile_auth),
    svc: AppServices = Depends(get_services),
) -> MessageReply:
    """Run one assistant turn (same core logic as LINE text messages)."""
    await svc.users.get_or_create_user(ctx.app_user_id)
    reply = await run_assistant_text_turn(
        svc,
        user_key=ctx.app_user_id,
        user_text=body.text,
    )
    return MessageReply(reply=reply)
