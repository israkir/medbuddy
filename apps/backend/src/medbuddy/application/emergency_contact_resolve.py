"""Persist emergency/family contact lines when classifiers misroute to medication tools."""

from __future__ import annotations

import re

from medbuddy.application.profile_intents import apply_profile_update_from_extracted_patch
from medbuddy.models.domain import ConversationTurn, Intent
from medbuddy.protocols import ProfilePatch
from medbuddy.services import AppServices

_TW_MOBILE = re.compile(r"\b09\d{8}\b")

# Relationship / contact wording — lines like "my son David, 0912..." are contacts, not drugs.
_CONTACT_RELATIONSHIP_CUES = re.compile(
    r"(?is)"
    r"\b(my\s+)?(son|daughter|wife|husband|spouse|mom|dad|mother|father|parent|child|children|kid|kids)\b|"
    r"\b(grandson|granddaughter|grandchild|sibling|brother|sister)\b|"
    r"(兒子|女兒|老公|老婆|先生|太太|母親|父親|爸|媽|緊急聯絡|聯絡人|家人|孫)"
)

_ASSISTANT_INVITED_SUBSTRINGS_EN = (
    "emergency contact",
    "name and phone",
    "save it for you",
    "provide me",
)

_ASSISTANT_INVITED_SUBSTRINGS_ZH = (
    "緊急聯絡",
    "聯絡方式",
    "姓名",
)

_MAX_CONTACT_LEN = 200


def _compact_contact_line(text: str) -> str:
    line = " ".join((text or "").split())
    if len(line) > _MAX_CONTACT_LEN:
        return line[:_MAX_CONTACT_LEN].rstrip()
    return line


def _has_tw_mobile(text: str) -> bool:
    return _TW_MOBILE.search(text or "") is not None


def _user_explicit_contact_offer(text: str) -> bool:
    if not _has_tw_mobile(text):
        return False
    return _CONTACT_RELATIONSHIP_CUES.search(text or "") is not None


def _assistant_invited_contact(history: list[ConversationTurn]) -> bool:
    for turn in reversed(history[-8:]):
        if turn.role != "assistant":
            continue
        raw = turn.content or ""
        lower = raw.lower()
        if any(s in lower for s in _ASSISTANT_INVITED_SUBSTRINGS_EN):
            return True
        if any(s in raw for s in _ASSISTANT_INVITED_SUBSTRINGS_ZH):
            return True
        if "緊急" in raw and ("聯絡" in raw or "電話" in raw):
            return True
    return False


def _strip_conflicting_fields_for_contact_line(patch: ProfilePatch, user_text: str) -> ProfilePatch:
    """Avoid storing 'David' as preferred_name when the user only listed a contact named David."""
    if not (_has_tw_mobile(user_text) and _user_explicit_contact_offer(user_text)):
        return patch
    out = dict(patch)
    out.pop("preferred_name", None)
    return out


async def try_resolve_emergency_contact_from_message(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
    history: list[ConversationTurn],
    locale: str,
    intent: Intent,
) -> str | None:
    """If this turn is clearly an emergency-contact update, persist and return ack; else None."""
    if not _has_tw_mobile(user_text):
        return None

    explicit = _user_explicit_contact_offer(user_text)
    invited = _assistant_invited_contact(history)

    eligible = False
    if explicit:
        eligible = intent in (
            Intent.UPDATE_PROFILE,
            Intent.GENERAL_QUESTION,
            Intent.ADD_MEDICATION,
        )
    elif invited:
        eligible = intent in (Intent.UPDATE_PROFILE, Intent.GENERAL_QUESTION)

    if not eligible:
        return None

    patch = await svc.llm.extract_profile_patch(user_text, locale=locale)
    patch = _strip_conflicting_fields_for_contact_line(patch, user_text)

    em = patch.get("emergency_contact") if isinstance(patch.get("emergency_contact"), str) else None
    if em and em.strip():
        merged = dict(patch)
        merged["emergency_contact"] = _compact_contact_line(em)
    else:
        merged = {"emergency_contact": _compact_contact_line(user_text)}

    return await apply_profile_update_from_extracted_patch(
        svc, user_key=user_key, patch=merged, baseline_locale=locale
    )
