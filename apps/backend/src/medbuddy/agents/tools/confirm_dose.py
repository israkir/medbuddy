"""Mark pending scheduled doses as taken when the user confirms in chat."""

from __future__ import annotations

from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.engine.types import AppServices
from medbuddy.i18n import t


class ConfirmDoseTool:
    name = "confirm_dose"
    description = "User says they took their medication; record adherence on pending dose events."

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_text: str,
        locale: str,
        **_: Any,
    ) -> ToolResult:
        note = await svc.llm.extract_dose_confirmation_note(user_text, locale=locale)
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
