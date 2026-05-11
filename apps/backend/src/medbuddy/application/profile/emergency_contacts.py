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


def _format_one_contact_hint(row: dict[str, object]) -> str:
    rel = str(row.get("relationship") or "").strip()
    val = str(row.get("channel_value") or "").strip()
    if rel and val:
        return f"{rel} {val}"
    return val


def emergency_contact_hint(contacts: object) -> str:
    """Small human-readable hint for the *primary* (or first) emergency contact.

    Kept for callers that only show one contact (e.g. profile signal lines).
    """
    normalized = normalize_emergency_contacts(contacts)
    if not normalized:
        return ""
    return _format_one_contact_hint(normalized[0])


def emergency_contacts_redacted_hint(
    contacts: object, *, locale: str = "en"
) -> tuple[str, dict[str, str]]:
    """Return a tokenised hint block for the LLM system prompt and a substitution map.

    The hint block names each contact by a bracketed token (e.g. ``[EMERGENCY_CONTACT_1]``)
    and exposes only low-sensitivity metadata (relationship, channel type, primary flag).
    The real channel values are kept in the returned substitution map so the server can
    replace tokens in the LLM reply before showing it to the patient — PII never leaves.

    Returns:
        (hint_block, token_map)
        hint_block  — multi-line string for the system prompt; empty string when no contacts.
        token_map   — ``{"[EMERGENCY_CONTACT_1]": "son 0912-345-678", …}``
    """
    normalized = normalize_emergency_contacts(contacts)
    if not normalized:
        return "", {}
    token_map: dict[str, str] = {}
    lines: list[str] = []
    count = len(normalized)
    intro = t(
        "prompts.llm_signal_emergency_contacts_redacted_intro",
        locale=locale,
        count=count,
    )
    lines.append(intro)
    for i, row in enumerate(normalized, start=1):
        token = f"[EMERGENCY_CONTACT_{i}]"
        token_map[token] = _format_one_contact_hint(row)
        is_primary = bool(row.get("is_primary"))
        primary_tag = (
            t("prompts.llm_signal_emergency_contact_primary_tag", locale=locale)
            if is_primary
            else ""
        )
        relationship = str(row.get("relationship") or "").strip()
        channel = str(row.get("channel_type") or "other").strip().lower()
        line = t(
            "prompts.llm_signal_emergency_contact_token_line",
            locale=locale,
            token=token,
            primary_tag=primary_tag,
            relationship=relationship,
            channel=channel,
        )
        lines.append(line)
    return "\n".join(lines), token_map


def emergency_contacts_hint_all(contacts: object, *, locale: str = "en") -> str:
    """Human-readable hint listing **all** stored emergency contacts.

    Used by the simulated emergency notify path so the message reflects every
    contact on file (not just the primary). Primary first, then the rest in the
    order returned by the store. Joined with a locale-appropriate separator.
    """
    normalized = normalize_emergency_contacts(contacts)
    if not normalized:
        return ""
    parts = [p for p in (_format_one_contact_hint(r) for r in normalized) if p]
    if not parts:
        return ""
    sep = "；" if locale == "zh-TW" else "; "
    return sep.join(parts)


def merge_emergency_contacts(existing: object, new_inputs: object) -> list[dict[str, str | bool]]:
    """Merge ``new_inputs`` into ``existing`` and mark only the most recent as primary.

    Semantics:
    - Contacts are addressable by ``(channel_type, channel_value)``.
    - A new entry that matches an existing one updates that entry's fields and
      counts as "most recent" again.
    - New entries that don't match are added (most recent last in input wins).
    - After merging, ``is_primary`` is ``True`` on exactly one entry — the
      most-recently-touched contact — and ``False`` on every other entry,
      regardless of any input flags.

    The returned list is ordered for display: the primary (most recent) first,
    then the remaining contacts in their original chronological order
    (oldest-first). This matches the read order Supabase returns
    (``is_primary desc, created_at asc``).
    """
    base = normalize_emergency_contacts(existing)
    incoming = normalize_emergency_contacts(new_inputs)
    by_key: dict[tuple[str, str], dict[str, str | bool]] = {}
    chrono: list[tuple[str, str]] = []
    for row in base:
        key = (str(row.get("channel_type") or ""), str(row.get("channel_value") or ""))
        by_key[key] = dict(row)
        chrono.append(key)
    most_recent: tuple[str, str] | None = chrono[-1] if chrono else None
    for row in incoming:
        key = (str(row.get("channel_type") or ""), str(row.get("channel_value") or ""))
        if key in by_key:
            merged = dict(by_key[key])
            for k, v in row.items():
                if k == "is_primary":
                    continue
                if v is None or v == "":
                    continue
                merged[k] = v
            by_key[key] = merged
        else:
            by_key[key] = dict(row)
            chrono.append(key)
        most_recent = key
    if most_recent is None:
        return []
    out: list[dict[str, str | bool]] = []
    primary = dict(by_key[most_recent])
    primary["is_primary"] = True
    out.append(primary)
    for key in chrono:
        if key == most_recent:
            continue
        item = dict(by_key[key])
        item["is_primary"] = False
        out.append(item)
    return out


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
        return t("profile.ack_emergency_profile_single", locale=locale, clause=clause)
    return t(
        "profile.ack_emergency_profile_multi",
        locale=locale,
        count=len(rows),
        clause=clause,
    )
