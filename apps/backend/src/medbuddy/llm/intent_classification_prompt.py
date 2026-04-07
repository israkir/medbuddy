"""Shared instructions for structured ``IntentClassification`` (OpenAI + Gemini).

One source of truth so intent routing stays aligned with :class:`~medbuddy.agents.medication_agent.MedicationAgent`
tool dispatch — the model chooses exactly one intent; the agent maps that intent to a tool or ``compose_reply``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Body only — providers wrap with user text / recent conversation.
# ---------------------------------------------------------------------------

INTENT_CLASSIFICATION_INSTRUCTIONS = """You help route each user message to exactly one intent for MedBuddy — a friendly medication assistant for older adults.
Each intent selects a backend behavior (a tool) or a fallback reply path. Pick the single best intent so they get the right help without frustration.

## Intent → what happens next (choose the intent that matches the user’s goal)

- **add_medication** — User wants to save/track a drug, set up reminders, or register dose timing. Triggers: add drug to list, extract fields (name, dose, schedule, reminder timing), persist, sync scheduled dose reminders. Use when they name a medicine and want tracking or alerts — e.g. “add aspirin”, “set a reminder for metformin 500mg after dinner”, “remind me to take X in 5 minutes”, “put lipitor on my list”, “新增/加入 [藥名]”.
- **list_medications** — User asks what medications they have on file / their list / “what am I taking”.
- **remove_medication** — User wants to stop tracking or remove a drug from the list.
- **confirm_dose** — User reports they already took a dose (e.g. “I took it”, “吃了”, “took my morning pills”), **or** they add a side effect / note **for a dose they already took** in a follow-up message (e.g. “I had a headache after”, “note that for my doctor”) — that note belongs on the dose record, not the long-term profile.
- **explain_medication** — User wants information about a drug: what it’s for, how it works, how to take it, not “add it to my list”. E.g. “what is metformin for”, “why do I take this pill”, “explain aspirin”.
- **interaction_check** — Combining drugs, food, or supplements: safety, interactions, “can I take A with B”.
- **log_vital** — Logging blood pressure, blood sugar, weight, or similar vitals.
- **request_summary** — Summary for a doctor visit or health recap.
- **update_profile** — Only for durable profile fields: how to address the user, age, gender, emergency contact, allergies, long-term health notes on file. Not for one-off side effects tied to **today’s / recent** medication — use **confirm_dose** for those (including after they already said “I took it”).
- **update_locale** — Change the assistant’s reply language (English vs Traditional Chinese), not “translate this drug leaflet”.
- **off_topic** — No health, medication, or care angle (e.g. weather, sports, coding). Rare for this app.
- **general_question** — Health-related chat that does not fit a tool above: vague symptoms, general advice, or clarification — use only when no more specific intent applies.

## Disambiguation (critical)

- Prefer **add_medication** over **general_question** when the user combines a drug name (or clear reference) with tracking, reminders, schedule, dose amount, or “add/save/remind/schedule/list on my meds”.
- Prefer **explain_medication** over **add_medication** when they only ask what/why/how about a drug without asking to save or remind.
- Prefer **interaction_check** over **explain_medication** when the question is about taking two or more substances together.
- Prefer **confirm_dose** over **general_question** when the user ties a symptom or note to taking medication **recently**, including short follow-ups right after confirming a dose.
- **Short follow-ups** that answer the assistant’s prior question about dosing, reminders, or scheduling (e.g. “一次”, “三天”, “7”, “once”, “yes”, “ok”, “每天”) must **not** be **off_topic** — use **general_question** or the clinical intent that fits the prior turn.

## off_topic

Use **off_topic** only when the topic is clearly unrelated to medications, health, or care. If there is any care or medication angle, prefer **general_question** or the best matching intent above, not **off_topic**.
"""


def format_intent_classification_prompt(
    *,
    user_text: str,
    recent_context: str | None = None,
) -> str:
    """Full prompt for structured intent classification."""
    if recent_context:
        return (
            f"{INTENT_CLASSIFICATION_INSTRUCTIONS}\n\n"
            "Recent conversation (context only; classify only the latest user line below):\n"
            f"{recent_context}\n\n"
            f"Latest user message to classify:\n{user_text}"
        )
    return f"{INTENT_CLASSIFICATION_INSTRUCTIONS}\n\nUser message:\n{user_text}"
