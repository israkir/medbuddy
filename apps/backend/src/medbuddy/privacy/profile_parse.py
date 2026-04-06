"""Heuristic profile extraction from chat (no LLM — keeps PII off model APIs)."""

from __future__ import annotations

import re
import unicodedata

from medbuddy.protocols.ports import ProfilePatch


def _nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip()


def parse_profile_patch_from_text(user_text: str) -> ProfilePatch:
    """Parse preferred name, age, emergency contact, and health notes when clearly stated.

    Conservative: only fills fields with explicit patterns so we do not guess PII.
    """
    text = _nfkc(user_text)
    if not text:
        return {}
    out: ProfilePatch = {}

    m = re.search(r"我叫\s*([^，,。！？\s]{1,32})", text)
    if m:
        out["preferred_name"] = m.group(1).strip()
    m2 = re.search(r"叫我\s*([^，,。！？\s]{1,32})", text)
    if m2:
        out["preferred_name"] = m2.group(1).strip()
    m_en = re.search(r"(?:my name is|i'm|i am|call me)\s+([^.;,!?\n]{1,48})", text, re.I)
    if m_en:
        out["preferred_name"] = m_en.group(1).strip()

    m3 = re.search(r"(?:今年|我)\s*(\d{1,3})\s*歲|(\d{1,3})\s*歲", text)
    if m3:
        age_s = m3.group(1) or m3.group(2)
        if age_s:
            age = int(age_s)
            if 0 <= age <= 120:
                out["age_years"] = age
    m4 = re.search(r"(?:^|\s)(\d{1,3})\s*years old\b", text, re.I)
    if m4:
        age = int(m4.group(1))
        if 0 <= age <= 120:
            out["age_years"] = age

    m5 = re.search(
        r"(?:緊急聯絡|聯絡電話|聯絡方式|家屬電話|手機|電話)[:：]?\s*"
        r"([0-9０-９+\-\s()（）]{8,28})",
        text,
    )
    if m5:
        raw_c = re.sub(r"\s+", " ", m5.group(1).strip())
        ascii_c = raw_c.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        if len(re.sub(r"\D", "", ascii_c)) >= 8:
            out["emergency_contact"] = ascii_c

    m6 = re.search(
        r"(?:過敏|過敏史|健康備註|身體狀況|備註)[:：]?\s*([^。！？\n]{1,240})",
        text,
    )
    if m6:
        note = m6.group(1).strip()
        if len(note) >= 2:
            out["health_notes"] = note

    m7 = re.search(
        r"(?:emergency|family) (?:contact|phone)[:：]?\s*([0-9+\-\s()]{8,28})",
        text,
        re.I,
    )
    if m7 and "emergency_contact" not in out:
        raw_c = re.sub(r"\s+", " ", m7.group(1).strip())
        if len(re.sub(r"\D", "", raw_c)) >= 8:
            out["emergency_contact"] = raw_c

    m8 = re.search(
        r"(?:allerg(?:y|ies)|health notes?)[:：]?\s*([^.;!?\n]{1,240})",
        text,
        re.I,
    )
    if m8 and "health_notes" not in out:
        note = m8.group(1).strip()
        if len(note) >= 2:
            out["health_notes"] = note

    return out
