"""Format ``health_issue_events`` rows for doctor-summary LLM prompts."""

from __future__ import annotations

from typing import Sequence

from medbuddy.models.domain import HEALTH_ROUTING_INTENT_VITAL, HealthIssueEventRecord


def format_health_issue_events_for_summary(events: Sequence[HealthIssueEventRecord]) -> str:
    """Chronological bullet lines: timestamp, routing intent, excerpt or structured vital text."""
    if not events:
        return ""
    chronological = sorted(events, key=lambda r: r.created_at)
    lines: list[str] = []
    for ev in chronological:
        ts = ev.created_at.isoformat(timespec="minutes")
        if ev.routing_intent == HEALTH_ROUTING_INTENT_VITAL:
            parts: list[str] = []
            if ev.kind:
                parts.append(f"[{ev.kind}]")
            body = (ev.display_summary or "").strip()
            if not body:
                body = (ev.user_message or "").strip()
            if not body:
                body = "(vital)"
            parts.append(body)
            if ev.notes:
                parts.append(f"notes: {ev.notes.strip()}")
            detail = " ".join(parts)
        else:
            detail = ((ev.user_message or "").strip()) or "(no message)"
        lines.append(f"- {ts} | intent={ev.routing_intent} | {detail}")
    return "\n".join(lines)
