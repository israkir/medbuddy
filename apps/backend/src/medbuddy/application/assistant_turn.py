"""Assistant turn entry-point — thin bridge between channels and the agent layer."""

from __future__ import annotations

from medbuddy.agents.medication_agent import MedicationAgent
from medbuddy.models.domain import AgentTurnResult
from medbuddy.services import AppServices

_agent = MedicationAgent()


async def run_assistant_text_turn(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
) -> AgentTurnResult:
    """Execute one full assistant turn and return reply text plus optional metadata."""
    return await _agent.run(svc, user_key=user_key, user_text=user_text)
