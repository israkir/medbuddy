"""Merge natural-language profile updates (name, age, contact, notes) from chat."""

from __future__ import annotations

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.models.domain import Intent
from medbuddy.privacy.profile_parse import parse_profile_patch_from_text
from medbuddy.protocols.ports import ProfilePatch
from medbuddy.prompts.persona import gender_option_label, normalized_profile_gender


def _profile_ack_summary(patch: ProfilePatch, *, locale: str) -> str:
    parts: list[str] = []
    if "preferred_name" in patch:
        name = patch["preferred_name"]
        if isinstance(name, str) and name.strip():
            parts.append(t("profile.ack_name", locale=locale, name=name.strip()))
    if "age_years" in patch:
        age = patch["age_years"]
        if isinstance(age, int):
            parts.append(t("profile.ack_age", locale=locale, age=age))
    if "emergency_contact" in patch:
        c = patch["emergency_contact"]
        if isinstance(c, str) and c.strip():
            parts.append(t("profile.ack_contact", locale=locale, contact=c.strip()))
    if "health_notes" in patch:
        n = patch["health_notes"]
        if isinstance(n, str) and n.strip():
            parts.append(t("profile.ack_notes", locale=locale, notes=n.strip()))
    if "gender" in patch:
        gk = normalized_profile_gender(patch.get("gender"))
        if gk:
            parts.append(
                t(
                    "profile.ack_gender",
                    locale=locale,
                    label=gender_option_label(gk, locale=locale),
                )
            )
    sep = t("profile.ack_sep", locale=locale)
    return sep.join(parts)


async def try_profile_intent_reply(
    svc: AppServices,
    *,
    user_key: str,
    intent: Intent,
    user_text: str,
    locale: str,
) -> str | None:
    if intent != Intent.UPDATE_PROFILE:
        return None
    raw_patch = parse_profile_patch_from_text(user_text)
    patch: ProfilePatch = {}
    allowed_gender = {"female", "male", "non_binary", "prefer_not_say", "other"}
    for key in ("preferred_name", "age_years", "gender", "emergency_contact", "health_notes"):
        if key not in raw_patch:
            continue
        val = raw_patch[key]
        if key == "age_years":
            if val is None:
                patch[key] = None
            elif isinstance(val, int) and 0 <= val <= 120:
                patch[key] = val
            elif isinstance(val, float) and val.is_integer():
                ai = int(val)
                if 0 <= ai <= 120:
                    patch[key] = ai
        elif key == "gender":
            if isinstance(val, str):
                g = val.strip().lower().replace("-", "_")
                if g == "nonbinary":
                    g = "non_binary"
                if g in allowed_gender:
                    patch[key] = g
        elif isinstance(val, str) and val.strip():
            patch[key] = val.strip()
    if not patch:
        return t("profile.update_unclear", locale=locale)
    await svc.users.patch_user_profile(user_key, patch)
    summary = _profile_ack_summary(patch, locale=locale)
    return t("profile.updated", locale=locale, summary=summary)
