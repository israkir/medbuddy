"""Merge natural-language profile updates (name, age, contact, notes) from chat."""

from __future__ import annotations

from medbuddy.engine.types import AppServices
from medbuddy.i18n import t
from medbuddy.models.domain import Intent
from medbuddy.protocols.ports import LLMPort, ProfilePatch
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
    llm: LLMPort,
) -> str | None:
    if intent != Intent.UPDATE_PROFILE:
        return None
    patch = await llm.extract_profile_patch(user_text, locale=locale)
    if not patch:
        return t("profile.update_unclear", locale=locale)
    await svc.users.patch_user_profile(user_key, patch)
    summary = _profile_ack_summary(patch, locale=locale)
    return t("profile.updated", locale=locale, summary=summary)
