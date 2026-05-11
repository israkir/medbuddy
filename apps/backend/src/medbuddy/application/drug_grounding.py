"""Fetch TFDA/OpenFDA snippets and derive short education cues from grounding text."""

from __future__ import annotations

import asyncio
import logging
from medbuddy.core.i18n import t
from medbuddy.services import AppServices

log = logging.getLogger(__name__)


async def fetch_drug_grounding_text(svc: AppServices, drug_name: str) -> str | None:
    """Fetch combined TFDA + OpenFDA grounding text for a drug name (parallel fetch)."""
    q = drug_name.strip()
    if not q:
        return None

    async def _safe_tfda():
        try:
            return await svc.drugs.fetch_tfda_snippet(q)
        except Exception:
            log.debug("drug_grounding: TFDA lookup failed query_len=%d", len(q))
            return None

    async def _safe_ofda():
        try:
            return await svc.drugs.fetch_openfda_label_snippet(q)
        except Exception:
            log.debug("drug_grounding: OpenFDA lookup failed query_len=%d", len(q))
            return None

    tfda, ofda = await asyncio.gather(_safe_tfda(), _safe_ofda())
    parts: list[str] = []
    if tfda:
        parts.append(f"{tfda.source}: {tfda.title}\n{tfda.body_zh}")
    if ofda:
        parts.append(f"{ofda.source}: {ofda.title}\n{ofda.body_zh}")
    return "\n\n".join(parts) if parts else None


def purpose_from_grounding(grounding: str | None) -> str | None:
    """Best-effort one-liner from grounding text for quick education cues."""
    if not grounding:
        return None
    for raw in grounding.splitlines():
        line = raw.strip()
        if not line:
            continue
        lowered = line.lower()
        if lowered.startswith("tfda(") or lowered.startswith("openfda("):
            continue
        for sep in (":", "："):
            if sep in line:
                _, tail = line.split(sep, 1)
                line = tail.strip()
                break
        if not line:
            continue
        trimmed = line[:140].rstrip(".,;: ")
        return trimmed
    return None


def education_lines_for_medication(
    *,
    locale: str,
    medication_name: str,
    purpose: str | None,
) -> tuple[list[str], bool]:
    """Tail lines appended after i18n fallback post-add or material medication updates."""
    if purpose:
        lines = [
            t(
                "medication.education_purpose_line",
                locale=locale,
                name=medication_name,
                purpose=purpose,
            ),
            t("medication.education_deep_dive_cta", locale=locale),
            t("medication.education_boundary", locale=locale),
        ]
        return lines, True
    lines = [
        t("medication.education_uncertain_line", locale=locale, name=medication_name),
        t("medication.education_deep_dive_cta", locale=locale),
        t("medication.education_boundary", locale=locale),
    ]
    return lines, False
