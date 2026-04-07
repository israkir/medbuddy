"""Persist structured vital-sign readings from chat."""

from __future__ import annotations

import logging
from typing import Any

from medbuddy.agents.base import ToolResult
from medbuddy.application.vital_log_build import vital_payload_and_summary
from medbuddy.engine.types import AppServices
from medbuddy.exceptions import VitalExtractionError
from medbuddy.i18n import t
from medbuddy.privacy.redact import redact_pii_text

log = logging.getLogger(__name__)


class LogVitalTool:
    name = "log_vital"
    description = "Extract and save a vital sign measurement from the user message."

    async def run(
        self,
        *,
        svc: AppServices,
        user_key: str,
        user_text: str,
        locale: str,
        **_: Any,
    ) -> ToolResult:
        safe_text = redact_pii_text(user_text)
        extracted = await svc.llm.extract_vital_log(safe_text, locale=locale)
        if extracted is None:
            raise VitalExtractionError()
        kind, summary, payload, notes = vital_payload_and_summary(extracted, locale=locale)
        saved = await svc.users.add_vital_log(
            user_key,
            kind=kind,
            display_summary=summary,
            payload=payload,
            notes=notes,
        )
        log.info(
            "log_vital: user_key=%s id=%s kind=%s",
            user_key,
            saved.id,
            kind,
        )
        return ToolResult(
            reply=t("vital.logged", locale=locale, summary=summary),
            structured=saved,
        )
