"""HTTP routes for the Expo/React Native client (not LINE webhooks)."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from medbuddy.agents.tools.health_summary import GenerateHealthSummaryTool
from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.channels.mobile.auth import MobileAuthContext, require_mobile_auth
from medbuddy.channels.mobile.schemas import (
    HealthSummaryResponse,
    MeResponse,
    MedicationSummaryItemResponse,
    MessageCreate,
    MessageReply,
    OnboardingSubmit,
)
from medbuddy.user_timezone import effective_user_timezone
from medbuddy.deps import get_services
from medbuddy.engine.types import AppServices
from medbuddy.exceptions import MedBuddyError

_summary_tool = GenerateHealthSummaryTool()

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
    tz_raw = row.get("timezone")
    tz_str = effective_user_timezone(tz_raw if isinstance(tz_raw, str) else None)
    return MeResponse(
        app_user_id=app_user_id,
        preferred_name=row.get("preferred_name"),
        age_years=row.get("age_years"),
        gender=gender_str,
        emergency_contact=row.get("emergency_contact"),
        health_notes=row.get("health_notes"),
        timezone=tz_str,
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
        timezone=body.timezone,
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


@router.get("/summary", response_model=HealthSummaryResponse)
async def app_get_health_summary(
    ctx: MobileAuthContext = Depends(require_mobile_auth),
    svc: AppServices = Depends(get_services),
) -> HealthSummaryResponse:
    """Generate a doctor-ready health summary for the current user.

    Aggregates the patient's medication list, anonymised profile signals,
    and recent conversation history to produce a structured summary
    suitable for sharing with a physician at the next appointment.
    """
    user_row = await svc.users.get_or_create_user(ctx.app_user_id)
    medications = await svc.users.list_medications(ctx.app_user_id)
    locale = svc.settings.locale

    try:
        result = await _summary_tool.run(
            svc=svc,
            user_key=ctx.app_user_id,
            user_row=user_row,
            medications=medications,
            locale=locale,
        )
    except MedBuddyError as exc:
        raise HTTPException(status_code=503, detail=exc.message) from exc

    summary = result.structured  # HealthSummary domain object
    r = summary.result

    med_responses = [
        MedicationSummaryItemResponse(
            name=item.name,
            dosage=item.dosage,
            schedule=item.schedule,
            purpose=item.purpose,
            notes=item.notes,
        )
        for item in summary.medications
    ]

    return HealthSummaryResponse(
        generated_at=summary.generated_at,
        summary_for_doctor=r.summary_for_doctor,
        medications=med_responses,
        key_concerns=r.key_concerns,
        reported_symptoms=r.reported_symptoms,
        medication_adherence_notes=r.medication_adherence_notes,
        recommended_questions=r.recommended_questions,
        plain_text=result.reply,
    )
