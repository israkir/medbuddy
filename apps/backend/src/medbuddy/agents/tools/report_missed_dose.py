"""Record that the latest pending dose window was missed (not taken)."""

from __future__ import annotations

from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.services import AppServices
from medbuddy.core.i18n import t


def _normalize_missed_note(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if len(s) > 500:
        return s[:500]
    return s


class ReportMissedDoseTool:
    name = "report_missed_dose"
    description = "Mark latest pending dose(s) as missed."

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_text: str,
        locale: str,
        **_: Any,
    ) -> ToolResult:
        note = _normalize_missed_note(user_text)
        n = await svc.users.mark_pending_doses_missed(user_key, notes=note)
        if n > 0:
            return ToolResult(reply=t("medication.missed_dose_recorded", locale=locale, count=n))
        return ToolResult(reply=t("medication.missed_dose_none", locale=locale))
