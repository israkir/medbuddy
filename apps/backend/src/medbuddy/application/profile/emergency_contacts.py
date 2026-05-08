"""Shared normalization/parsing helpers for structured emergency contacts."""

from __future__ import annotations

import re

from medbuddy.core.i18n import t

_PHONE_RE = re.compile(r"(?:\+?\d[\d\-\s]{6,}\d)")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_LINE_RE = re.compile(r"(?:line|lineid|line id|LINE|LINE ID)[:\s@#-]*([A-Za-z0-9_.-]{2,})")
_WHATSAPP_RE = re.compile(r"(?:whatsapp|wa)[:\s@#-]*([A-Za-z0-9_.+\-]{3,})", re.IGNORECASE)
_REL_RE = re.compile(
    r"\b(son|daughter|wife|husband|spouse|mother|father|mom|dad|brother|sister|friend)\b|"
    r"(兒子|女兒|老公|老婆|先生|太太|母親|父親|爸|媽|兄|弟|姊|妹|朋友)",
    re.IGNORECASE,
)


def normalize_emergency_contacts(raw: object) -> list[dict[str, str | bool]]:
    """Normalize user/LLM provided emergency contacts into canonical dicts."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str | bool]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        channel_type = str(item.get("channel_type") or "").strip().lower()
        if channel_type not in {"phone", "email", "line", "whatsapp", "other"}:
            channel_type = "other"
        channel_value = str(item.get("channel_value") or "").strip()
        if not channel_value:
            continue
        one: dict[str, str | bool] = {
            "channel_type": channel_type,
            "channel_value": channel_value,
            "is_primary": bool(item.get("is_primary", i == 0)),
        }
        for key in ("contact_name", "relationship", "notes"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                one[key] = val.strip()
        out.append(one)
    return out


def extract_contacts_from_text(text: str) -> list[dict[str, str | bool]]:
    """Best-effort parser for fallback/migration paths."""
    src = " ".join((text or "").split())
    if not src:
        return []
    contacts: list[dict[str, str | bool]] = []
    m_rel = _REL_RE.search(src)
    relationship = m_rel.group(0) if m_rel else None
    for m in _PHONE_RE.finditer(src):
        raw = m.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 7:
            continue
        contacts.append(
            {
                "relationship": relationship or "",
                "channel_type": "phone",
                "channel_value": raw,
                "is_primary": len(contacts) == 0,
                "notes": src,
            }
        )
    for m in _EMAIL_RE.finditer(src):
        contacts.append(
            {
                "relationship": relationship or "",
                "channel_type": "email",
                "channel_value": m.group(0).strip(),
                "is_primary": len(contacts) == 0,
                "notes": src,
            }
        )
    for m in _LINE_RE.finditer(src):
        contacts.append(
            {
                "relationship": relationship or "",
                "channel_type": "line",
                "channel_value": m.group(1).strip(),
                "is_primary": len(contacts) == 0,
                "notes": src,
            }
        )
    for m in _WHATSAPP_RE.finditer(src):
        contacts.append(
            {
                "relationship": relationship or "",
                "channel_type": "whatsapp",
                "channel_value": m.group(1).strip(),
                "is_primary": len(contacts) == 0,
                "notes": src,
            }
        )
    return normalize_emergency_contacts(contacts)


def emergency_contact_hint(contacts: object) -> str:
    """Small human-readable emergency contact hint for prompts/replies."""
    normalized = normalize_emergency_contacts(contacts)
    if not normalized:
        return ""
    first = normalized[0]
    rel = str(first.get("relationship") or "").strip()
    val = str(first.get("channel_value") or "").strip()
    if rel and val:
        return f"{rel} {val}"
    return val


def _detail_suffix(value: str, *, locale: str) -> str:
    if not value:
        return ""
    if locale == "zh-TW":
        return f"（{value}）"
    return f" ({value})"


def _channel_word(channel_type: str, *, locale: str) -> str:
    ct = (channel_type or "other").strip().lower()
    key = {
        "phone": "profile.emergency_channel_phone",
        "email": "profile.emergency_channel_email",
        "line": "profile.emergency_channel_line",
        "whatsapp": "profile.emergency_channel_whatsapp",
    }.get(ct, "profile.emergency_channel_other")
    return t(key, locale=locale)


def _primary_contact_row(rows: list[dict[str, str | bool]]) -> dict[str, str | bool]:
    for row in rows:
        if row.get("is_primary"):
            return row
    return rows[0]


def emergency_contact_save_ack(rows: list[dict[str, str | bool]], *, locale: str) -> str:
    """Full sentence(s) acknowledging saved emergency contacts (normalized rows)."""
    if not rows:
        return ""
    primary = _primary_contact_row(rows)
    rel = str(primary.get("relationship") or "").strip()
    name = str(primary.get("contact_name") or "").strip()
    value = str(primary.get("channel_value") or "").strip()
    ch = _channel_word(str(primary.get("channel_type") or "other"), locale=locale)
    detail = _detail_suffix(value, locale=locale)
    if rel and name:
        clause = t(
            "profile.ack_emergency_clause_rel_name",
            locale=locale,
            relationship=rel,
            name=name,
            channel=ch,
            detail=detail,
        )
    elif rel:
        clause = t(
            "profile.ack_emergency_clause_rel",
            locale=locale,
            relationship=rel,
            channel=ch,
            detail=detail,
        )
    elif name:
        clause = t(
            "profile.ack_emergency_clause_name",
            locale=locale,
            name=name,
            channel=ch,
            detail=detail,
        )
    else:
        clause = t(
            "profile.ack_emergency_clause_fallback",
            locale=locale,
            channel=ch,
            detail=detail,
        )
    if len(rows) == 1:
        return t("profile.ack_emergency_single", locale=locale, clause=clause)
    return t(
        "profile.ack_emergency_multi",
        locale=locale,
        count=len(rows),
        clause=clause,
    )
