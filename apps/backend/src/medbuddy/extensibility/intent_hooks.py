"""Register optional intent handlers without forking the LINE channel orchestrator."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from medbuddy.engine.types import AppServices
from medbuddy.models.domain import Intent

IntentHook = Callable[[Intent, AppServices, str], Awaitable[str | None]]

_hooks: list[IntentHook] = []


def register_intent_hook(fn: IntentHook) -> None:
    _hooks.append(fn)


def clear_intent_hooks() -> None:
    """Test helper — production code typically registers hooks at import time."""
    _hooks.clear()


async def try_intent_hooks(
    intent: Intent,
    svc: AppServices,
    user_text: str,
) -> str | None:
    for hook in _hooks:
        out = await hook(intent, svc, user_text)
        if out is not None:
            return out
    return None
