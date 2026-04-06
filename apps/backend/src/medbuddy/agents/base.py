"""Base types for the agents layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolResult:
    """Unified return type from every ``AgentTool.run()`` call.

    ``reply`` is always populated — it is the user-facing text response.
    ``structured`` holds an optional domain object (e.g. ``HealthSummary``,
    ``InteractionResult``) for callers that need the typed data too.
    ``consumed`` signals that the tool fully handled the turn (no further
    LLM composition needed).
    """

    reply: str
    structured: Any = None
    consumed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AgentTool(Protocol):
    """Protocol every tool must satisfy."""

    name: str
    description: str

    async def run(self, **kwargs: Any) -> ToolResult: ...
