"""Merge natural-language profile updates (name, age, contact, notes) from chat."""

from __future__ import annotations

from medbuddy.services import AppServices
from medbuddy.core.i18n import t
from medbuddy.models.domain import Intent
from medbuddy.protocols import LLMPort, ProfilePatch
from medbuddy.llm.prompts.persona import gender_option_label, normalized_profile_gender
from medbuddy.core.locale import effective_user_locale, normalize_locale_patch
from medbuddy.core.timezone import normalize_timezone_patch


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
    if "locale" in patch:
        normalized = normalize_locale_patch(patch.get("locale"))
        if normalized:
            label_key = "locale.label_en" if normalized == "en" else "locale.label_zh_tw"
            parts.append(t("profile.ack_locale", locale=locale, label=t(label_key, locale=locale)))
    if "timezone" in patch:
        tz_raw = patch.get("timezone")
        if tz_raw is None:
            parts.append(t("profile.ack_timezone_cleared", locale=locale))
        else:
            normalized_tz = normalize_timezone_patch(tz_raw)
            if normalized_tz:
                parts.append(t("profile.ack_timezone", locale=locale, timezone=normalized_tz))
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
    if "locale" in patch:
        norm_locale = normalize_locale_patch(patch["locale"])
        if norm_locale is None:
            patch.pop("locale", None)
        else:
            patch["locale"] = norm_locale
    if "timezone" in patch:
        if patch["timezone"] is None:
            pass
        else:
            norm_tz = normalize_timezone_patch(patch["timezone"])
            if norm_tz is None:
                patch.pop("timezone", None)
            else:
                patch["timezone"] = norm_tz
    if not patch:
        return t("profile.update_unclear", locale=locale)
    await svc.users.patch_user_profile(user_key, patch)
    message_locale = effective_user_locale(patch.get("locale", locale))
    summary = _profile_ack_summary(patch, locale=message_locale)
    return t("profile.updated", locale=message_locale, summary=summary)
