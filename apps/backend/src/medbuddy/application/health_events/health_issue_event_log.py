"""Policy and helpers for ``health_issue_events`` rows used in doctor-summary prompts."""

from __future__ import annotations

import logging

from medbuddy.config import Settings
from medbuddy.models.domain import HealthIssueEventRecord, Intent
from medbuddy.services import AppServices

log = logging.getLogger(__name__)

# Sentinel for MEDBUDDY_HEALTH_ISSUE_LOG_INTENTS=all_non_off_topic
_HEALTH_ISSUE_LOG_ALL_NON_OFF_TOPIC = "all_non_off_topic"

# Default: wellness/issue-focused; excludes med CRUD, scheduling-only, profile, off-topic.
# ``LOG_VITAL`` is excluded here — ``LogVitalTool`` writes a structured ``log_vital`` row.
_DEFAULT_LOG_INTENTS: frozenset[Intent] = frozenset(
    {
        Intent.EMERGENCY,
        Intent.REPORT_SIDE_EFFECTS,
        Intent.GENERAL_QUESTION,
        Intent.REPORT_MISSED_DOSE,
        Intent.CONFIRM_DOSE,
        Intent.INTERACTION_CHECK,
        Intent.EXPLAIN_MEDICATION,
        Intent.REQUEST_SUMMARY,
    }
)


def should_log_routing_intent_health_issue(intent: Intent, settings: Settings) -> bool:
    """Whether to persist a classifier-intent row for this turn (not structured vitals)."""
    cfg = settings.health_issue_log_intents
    if cfg is None:
        return intent in _DEFAULT_LOG_INTENTS
    if len(cfg) == 1 and cfg[0] == _HEALTH_ISSUE_LOG_ALL_NON_OFF_TOPIC:
        return intent != Intent.OFF_TOPIC
    allowed = frozenset(cfg)
    return intent.value in allowed


def truncate_for_display(text: str, *, max_len: int = 4000) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def format_health_issue_events_for_summary_prompt(events: list[HealthIssueEventRecord]) -> str:
    """Lines-only block for ``generate_health_summary`` (chronological within the batch)."""
    if not events:
        return ""
    lines: list[str] = []
    for ev in sorted(events, key=lambda e: e.created_at):
        ts = ev.created_at.isoformat()
        excerpt = (ev.user_message or "").strip()
        if not excerpt:
            excerpt = (ev.display_summary or "").strip()
        if not excerpt and ev.payload:
            excerpt = str(ev.payload)[:500]
        lines.append(f"- {ts} | {ev.routing_intent} | {excerpt}")
    return "\n".join(lines)


async def maybe_record_health_issue_turn(
    svc: AppServices,
    *,
    user_key: str,
    user_text: str,
    locale: str,
    intent: Intent,
) -> None:
    """Persist a routing-intent row when policy allows; never raises."""
    try:
        if not should_log_routing_intent_health_issue(intent, svc.settings):
            return
        await svc.users.record_health_issue_event(
            user_key,
            routing_intent=intent.value,
            user_message=truncate_for_display(user_text),
            locale=locale,
        )
    except Exception:
        log.warning(
            "maybe_record_health_issue_turn failed user_key=%s intent=%s",
            user_key,
            intent.value,
            exc_info=True,
        )
