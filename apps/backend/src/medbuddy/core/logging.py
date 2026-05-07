"""Application logging — levels tuned for hosted runs (e.g. Render log stream)."""

from __future__ import annotations

import logging
import sys


def configure_logging(level_name: str) -> None:
    """Apply consistent stdout logging for app and server loggers."""
    level = getattr(logging, level_name.upper(), None)
    if not isinstance(level, int):
        level = logging.INFO
    # Ensure logs reach container stdout even if no handlers were configured upstream.
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    for name in ("medbuddy", "uvicorn", "uvicorn.error", "uvicorn.access", "arq"):
        logging.getLogger(name).setLevel(level)
