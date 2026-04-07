"""Record adherence and dose-row notes from structured interpretation (no second-pass heuristics)."""

from __future__ import annotations

from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.engine.types import AppServices
from medbuddy.i18n import t


def _normalize_dose_note(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if len(s) > 500:
        return s[:500]
    return s


class ConfirmDoseTool:
    name = "confirm_dose"
    description = "Apply adherence slots from turn interpretation: record taken and/or dose note."

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_text: str,
        locale: str,
        record_pending_dose_as_taken: bool = False,
        dose_adherence_note: str | None = None,
        **_: Any,
    ) -> ToolResult:
        _ = user_text
        note = _normalize_dose_note(dose_adherence_note)
        n = 0
        if record_pending_dose_as_taken:
            n = await svc.users.mark_pending_doses_taken(user_key, notes=note)
        if n > 0:
            if note:
                return ToolResult(
                    reply=t(
                        "medication.confirm_dose_recorded_with_note",
                        locale=locale,
                        count=n,
                        note=note,
                    )
                )
            return ToolResult(reply=t("medication.confirm_dose_recorded", locale=locale, count=n))
        if note:
            appended = await svc.users.append_note_to_recent_taken_dose(user_key, notes=note)
            if appended > 0:
                return ToolResult(
                    reply=t(
                        "medication.confirm_dose_note_appended",
                        locale=locale,
                        note=note,
                    )
                )
        return ToolResult(reply=t("medication.confirm_dose_none", locale=locale))
