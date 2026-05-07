"""Map structured LLM extraction to :class:`~medbuddy.models.domain.MedicationDraft`."""

from __future__ import annotations

import re

from medbuddy.llm.schemas import MedicationExtraction
from medbuddy.models.domain import MedicationDraft
from medbuddy.reminders.dose_schedule import parse_hhmm

# Normalized tokens meaning “unknown” for dose / schedule (plus locale-specific label).
_PLACEHOLDER_TOKENS = frozenset(
    {
        "",
        "unspecified",
        "unstated",
        "n/a",
        "na",
        "none",
        "unknown",
        "not specified",
        "-",
        "—",
        "...",
        "未指定",
        "未註明",
        "不明",
        "不詳",
    }
)

_DOSE_EVIDENCE = re.compile(
    r"(?ix)\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|ug|ml|cc|units?|iu|tablets?|caps?(?:ule)?s?)\b|"
    r"(?:\d+\s*(?:顆|粒|錠|片|包|毫克|公克|毫升|單位))|"
    r"(?:[一二兩三四五六七八九十百]\s*(?:顆|粒|錠|片|包|毫克|公克|毫升|單位|瓶|支|粉包))"
)
_SCHEDULE_EVIDENCE = re.compile(
    r"(?ix)\b(?:daily|once|twice|three\s+times|qid|tid|bid|qd|qhs|q\d+h|every)\b|"
    r"(?:每(?:天|日|晚|週|周|早|午|餐|隔日)|早晚|飯前|飯後|睡前|一天[一二兩2三3四4]次|早上|晚上)"
)


def _validated_hhmm_list(
    *,
    multi: list[str] | None,
    single: str | None,
) -> list[str]:
    out: list[str] = []
    if multi:
        for raw in multi:
            if not raw or not str(raw).strip():
                continue
            s = str(raw).strip()
            try:
                parse_hhmm(s)
            except ValueError:
                continue
            if s not in out:
                out.append(s)
    if not out and single and single.strip():
        try:
            s = single.strip()
            parse_hhmm(s)
            out.append(s)
        except ValueError:
            pass
    if not out:
        return []
    return sorted(out, key=lambda t: (parse_hhmm(t)[0], parse_hhmm(t)[1]))


def _is_placeholder_dose_or_schedule(value: str, *, unspecified_label: str) -> bool:
    x = (value or "").strip().lower()
    if not x:
        return True
    un = (unspecified_label or "").strip().lower()
    if un and x == un:
        return True
    return x in _PLACEHOLDER_TOKENS


def is_placeholder_field(value: str | None) -> bool:
    """True when *value* is an empty or recognised unknown-placeholder token (locale-agnostic)."""
    return (value or "").strip().lower() in _PLACEHOLDER_TOKENS


def dose_or_schedule_display(value: str | None, *, unspecified_label: str) -> str:
    """Map stored English/empty placeholders to the user's locale label for UI copy."""
    raw = (value or "").strip()
    if _is_placeholder_dose_or_schedule(raw, unspecified_label=unspecified_label):
        return unspecified_label
    return raw


def medication_draft_fields_complete(draft: MedicationDraft, *, unspecified_label: str) -> bool:
    """True when dosage and schedule are both non-placeholder values.

    One-time reminders (first_reminder_in_minutes set, materialize_daily_reminders=False)
    do not require a recurring schedule — 'unspecified' schedule is correct there.
    """
    is_one_time_only = (
        draft.first_reminder_in_minutes is not None and not draft.materialize_daily_reminders
    )
    dose_ok = not _is_placeholder_dose_or_schedule(
        draft.dosage, unspecified_label=unspecified_label
    )
    sched_ok = is_one_time_only or not _is_placeholder_dose_or_schedule(
        draft.schedule, unspecified_label=unspecified_label
    )
    return dose_ok and sched_ok


def medication_draft_needs_add_confirmation(
    draft: MedicationDraft, *, unspecified_label: str, user_text: str
) -> bool:
    """True when dose or schedule is missing/unclear — ask the user before saving.

    Instructions are intentionally NOT required: they are optional, and requiring
    them for every add creates needless friction for elderly users who omit them.
    Confirmation fires when:
      - dose or schedule field is a placeholder/unspecified, OR
      - the raw user message lacks clear numeric dose or schedule signals (guardrail
        against silently accepting LLM-inferred values the user never stated).

    Exception: for pure one-time reminders (first_reminder_in_minutes set,
    materialize_daily_reminders=False), a recurring schedule is not required —
    "未指定" schedule is correct and expected in that case.
    """
    if not medication_draft_fields_complete(draft, unspecified_label=unspecified_label):
        return True
    # Guardrail: if user didn't provide clear dose/schedule signals, do not auto-save inferred values.
    is_one_time_only = (
        draft.first_reminder_in_minutes is not None and not draft.materialize_daily_reminders
    )
    src = (user_text or "").strip()
    if not src:
        return True
    has_dose_signal = bool(_DOSE_EVIDENCE.search(src))
    # For one-time reminders the "schedule signal" is the first_reminder_in_minutes itself.
    has_schedule_signal = is_one_time_only or bool(_SCHEDULE_EVIDENCE.search(src))
    return not (has_dose_signal and has_schedule_signal)


def medication_draft_from_extraction(
    extracted: MedicationExtraction, *, unspecified: str
) -> MedicationDraft | None:
    name = extracted.name.strip()
    if not name or _is_placeholder_dose_or_schedule(name, unspecified_label=unspecified):
        return None
    hd = extracted.reminder_horizon_days
    if hd is not None:
        hd = max(1, min(90, int(hd)))
    times = _validated_hhmm_list(
        multi=extracted.daily_reminder_local_hhmm_list,
        single=extracted.daily_reminder_local_hhmm,
    )
    daily_single: str | None = None
    daily_list: list[str] | None = None
    if len(times) == 1:
        daily_single = times[0]
    elif len(times) > 1:
        daily_list = times
    fm = extracted.first_reminder_in_minutes
    if fm is not None:
        fm = int(fm)
        if fm <= 0:
            fm = None
    return MedicationDraft(
        name=name,
        dosage=extracted.dosage.strip() or unspecified,
        schedule=extracted.schedule.strip() or unspecified,
        instructions=extracted.instructions,
        first_reminder_in_minutes=fm,
        materialize_daily_reminders=extracted.materialize_daily_reminders,
        reminder_horizon_days=hd,
        needs_horizon_confirmation=extracted.needs_horizon_confirmation,
        daily_reminder_local_hhmm=daily_single,
        daily_reminder_local_hhmm_list=daily_list,
    )
