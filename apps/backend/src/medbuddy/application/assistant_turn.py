"""Assistant turn entry-point — thin bridge between channels and the agent layer.

Both LINE and mobile channels call ``run_assistant_text_turn()``.
All business logic lives in ``MedicationAgent``; this module exists only
to preserve the stable public API imported by the channel routes.
"""

from __future__ import annotations

from medbuddy.agents.medication_agent import MedicationAgent
from medbuddy.services import AppServices

_agent = MedicationAgent()


async def run_assistant_text_turn(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
) -> str:
    """Execute one full assistant turn and return the reply text.

    Args:
        svc: Wired ``AppServices`` container.
        user_key: Stable persistence key (LINE user id or app-scoped id).
        user_text: Raw user message.

    Returns:
        The assistant reply text for the channel to send.
    """
    return await _agent.run(svc, user_key=user_key, user_text=user_text)
