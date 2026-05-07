"""Types for multi-step LLM tool calling."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChatToolCall:
    """One function call requested by the assistant."""

    id: str
    name: str
    arguments: str
