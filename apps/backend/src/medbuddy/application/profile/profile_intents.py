"""Merge natural-language profile updates (name, age, contact, notes) from chat."""

from __future__ import annotations

from medbuddy.services import AppServices
from medbuddy.core.i18n import t
from medbuddy.protocols import ProfilePatch
from medbuddy.llm.prompts.persona import gender_option_label, normalized_profile_gender
from medbuddy.core.locale import effective_user_locale, normalize_locale_patch
from medbuddy.core.timezone import normalize_timezone_patch
from medbuddy.application.profile.emergency_contacts import (
    emergency_contact_save_ack,
    normalize_emergency_contacts,
)


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
    if "emergency_contacts" in patch:
        contacts = normalize_emergency_contacts(patch.get("emergency_contacts"))
        if contacts:
            parts.append(emergency_contact_save_ack(contacts, locale=locale))
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


def _normalize_profile_patch(patch: ProfilePatch) -> ProfilePatch:
    """Normalize locale/timezone fields; drop invalid entries."""
    out = dict(patch)
    if "locale" in out:
        norm_locale = normalize_locale_patch(out["locale"])
        if norm_locale is None:
            out.pop("locale", None)
        else:
            out["locale"] = norm_locale
    if "timezone" in out:
        if out["timezone"] is None:
            pass
        else:
            norm_tz = normalize_timezone_patch(out["timezone"])
            if norm_tz is None:
                out.pop("timezone", None)
            else:
                out["timezone"] = norm_tz
    if "emergency_contacts" in out:
        normalized_contacts = normalize_emergency_contacts(out["emergency_contacts"])
        if normalized_contacts:
            out["emergency_contacts"] = normalized_contacts
        else:
            out.pop("emergency_contacts", None)
    return out


async def apply_profile_update_from_extracted_patch(
    svc: AppServices,
    *,
    user_key: str,
    patch: ProfilePatch,
    baseline_locale: str,
) -> str:
    """Persist a profile patch (already extracted) and return the user-facing ack message."""
    patch = _normalize_profile_patch(patch)
    if not patch:
        return t("profile.update_unclear", locale=baseline_locale)
    await svc.users.patch_user_profile(user_key, patch)
    message_locale = effective_user_locale(patch.get("locale", baseline_locale))
    summary = _profile_ack_summary(patch, locale=message_locale)
    return t("profile.updated", locale=message_locale, summary=summary)
