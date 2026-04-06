"""Application logging — levels tuned for hosted runs (e.g. Render log stream)."""

from __future__ import annotations

import logging


def configure_logging(level_name: str) -> None:
    """Apply ``level_name`` to ``medbuddy.*`` and uvicorn error stream."""
    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        level = logging.INFO
    for name in ("medbuddy", "uvicorn.error"):
        logging.getLogger(name).setLevel(level)
