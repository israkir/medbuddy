"""Shared helpers used by both Gemini and OpenAI adapters."""

from __future__ import annotations

import re

_LANGUAGE_LOCK: dict[str, str] = {
    "en": (
        "LANGUAGE REQUIREMENT: You MUST reply in English only. "
        "Do not switch to any other language regardless of the language used in conversation history or user input."
    ),
    "zh-TW": (
        "語言規定：你的回覆必須使用繁體中文（台灣），"
        "無論對話歷史或使用者訊息使用何種語言，都不得切換語言。"
    ),
}


def language_lock(locale: str) -> str:
    return _LANGUAGE_LOCK.get(locale, _LANGUAGE_LOCK["zh-TW"])


def strip_json_fence(raw: str) -> str:
    """Strip ```json ... ``` fences from model output that ignores response_mime_type."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()
