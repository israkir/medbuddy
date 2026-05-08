"""Shared normalization/parsing helpers for structured emergency contacts."""

from __future__ import annotations

import re

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
