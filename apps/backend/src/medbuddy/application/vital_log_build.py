"""Validate LLM vital extraction and build persisted payload + localized summary."""

from __future__ import annotations

from typing import Any

from medbuddy.exceptions import VitalExtractionError
from medbuddy.i18n import t
from medbuddy.llm.schemas import VitalLogExtraction


def _norm_notes(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    return s[:500]


def _normalize_kind(raw: str) -> str:
    k = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases: dict[str, str] = {
        "bp": "blood_pressure",
        "bloodpressure": "blood_pressure",
        "glucose": "blood_glucose",
        "bloodsugar": "blood_glucose",
        "blood_sugar": "blood_glucose",
        "bs": "blood_glucose",
        "hr": "heart_rate",
        "pulse": "heart_rate",
        "temp": "temperature",
        "fever": "temperature",
        "o2": "spo2",
        "oxygen": "spo2",
        "saturation": "spo2",
        "sp_o2": "spo2",
    }
    if k in aliases:
        return aliases[k]
    allowed = frozenset(
        {
            "blood_pressure",
            "blood_glucose",
            "weight",
            "heart_rate",
            "temperature",
            "spo2",
            "other",
        }
    )
    if k in allowed:
        return k
    return "other"


def vital_payload_and_summary(
    extracted: VitalLogExtraction, *, locale: str
) -> tuple[str, str, dict[str, Any], str | None]:
    """Return ``(kind, display_summary, payload, notes)`` or raise :class:`VitalExtractionError`."""
    kind = _normalize_kind(extracted.kind)
    notes = _norm_notes(extracted.notes)
    payload: dict[str, Any] = {"kind": kind}

    if kind == "blood_pressure":
        sys_v, dia_v = extracted.systolic, extracted.diastolic
        if sys_v is None or dia_v is None:
            raise VitalExtractionError()
        if not (40 <= int(sys_v) <= 280 and 30 <= int(dia_v) <= 200):
            raise VitalExtractionError()
        payload["systolic"] = int(sys_v)
        payload["diastolic"] = int(dia_v)
        summary = t(
            "vital.summary_blood_pressure",
            locale=locale,
            systolic=sys_v,
            diastolic=dia_v,
        )
        return kind, summary, payload, notes

    if kind == "blood_glucose":
        v = extracted.blood_glucose_mg_dl
        if v is None or not (20.0 <= float(v) <= 800.0):
            raise VitalExtractionError()
        payload["blood_glucose_mg_dl"] = float(v)
        summary = t("vital.summary_blood_glucose", locale=locale, value=v)
        return kind, summary, payload, notes

    if kind == "weight":
        v = extracted.weight_kg
        if v is None or not (10.0 <= float(v) <= 400.0):
            raise VitalExtractionError()
        payload["weight_kg"] = float(v)
        summary = t("vital.summary_weight", locale=locale, value=v)
        return kind, summary, payload, notes

    if kind == "heart_rate":
        v = extracted.heart_rate_bpm
        if v is None or not (30 <= int(v) <= 240):
            raise VitalExtractionError()
        payload["heart_rate_bpm"] = int(v)
        summary = t("vital.summary_heart_rate", locale=locale, value=v)
        return kind, summary, payload, notes

    if kind == "temperature":
        v = extracted.temperature_celsius
        if v is None or not (30.0 <= float(v) <= 45.0):
            raise VitalExtractionError()
        payload["temperature_celsius"] = float(v)
        summary = t("vital.summary_temperature", locale=locale, value=v)
        return kind, summary, payload, notes

    if kind == "spo2":
        v = extracted.spo2_percent
        if v is None or not (50 <= int(v) <= 100):
            raise VitalExtractionError()
        payload["spo2_percent"] = int(v)
        summary = t("vital.summary_spo2", locale=locale, value=v)
        return kind, summary, payload, notes

    # other
    label = (extracted.other_label or "").strip() or t("vital.other_unknown_label", locale=locale)
    value = (extracted.other_value or "").strip()
    if not value:
        raise VitalExtractionError()
    payload["other_label"] = label
    payload["other_value"] = value[:200]
    summary = t("vital.summary_other", locale=locale, label=label, value=value[:200])
    return kind, summary, payload, notes
