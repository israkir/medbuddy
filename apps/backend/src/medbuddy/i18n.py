"""Load translated strings from JSON locale files (BCP 47 tags, e.g. zh-TW, en)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"

_FALLBACK = "zh-TW"


def clear_i18n_cache() -> None:
    """Clear cached locale bundles (e.g. after tests change files)."""
    _bundle.cache_clear()


@lru_cache
def _bundle(locale: str) -> dict[str, Any]:
    path = _LOCALES_DIR / f"{locale}.json"
    if not path.is_file():
        path = _LOCALES_DIR / f"{_FALLBACK}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _walk(data: dict[str, Any], parts: list[str]) -> Any:
    node: Any = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            raise KeyError(".".join(parts))
        node = node[part]
    return node


def _lookup_string(key: str, locale: str) -> str:
    parts = key.split(".")
    node = _walk(_bundle(locale), parts)
    if not isinstance(node, str):
        msg = f"i18n key {key!r} is not a string"
        raise KeyError(msg)
    return node


def t(key: str, *, locale: str | None = None, **kwargs: Any) -> str:
    """Return a translated string. Keys use dotted paths, e.g. ``orchestrator.consent_accepted``."""
    from medbuddy.config import get_settings

    loc = locale if locale is not None else get_settings().locale
    try:
        s = _lookup_string(key, loc)
    except KeyError:
        s = _lookup_string(key, _FALLBACK)
    return s.format(**kwargs) if kwargs else s
