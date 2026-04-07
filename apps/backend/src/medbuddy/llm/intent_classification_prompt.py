"""Shared instructions for structured ``IntentClassification`` (OpenAI + Gemini).

One source of truth so routing stays aligned with :class:`~medbuddy.agents.medication_agent.MedicationAgent`:
the model returns one intent plus adherence slots; the agent maps those fields to tools or ``compose_reply``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Body only — providers wrap with user text / recent conversation.
# ---------------------------------------------------------------------------

INTENT_CLASSIFICATION_INSTRUCTIONS = """You help route each user message for MedBuddy — a friendly medication assistant for older adults.
Return one intent, your reasoning, and two adherence fields used mechanically by the server (no keyword rules on the server).

## Structured fields (always set explicitly)

- **record_pending_dose_as_taken** — True only if the user clearly states they **took/completed** the relevant scheduled dose (pill swallowed, injection done, 吃了, “I took it” about that reminder). False if they only describe symptoms, pain, thanks, or wellbeing; false if “yes/ok” is answering how they **feel** or a symptom question rather than “did you take it?”.
- **dose_adherence_note** — Non-null only for text that should be stored on the **dose record**: side effect or context when they are logging adherence, **or** a short follow-up after they already took a dose (e.g. “note dizziness for my doctor”). Null for general symptom chat, gratitude, or topics meant for conversational reply only.

## Intent → what happens next (choose the intent that matches the user’s goal)

- **add_medication** — User wants to save/track a drug, set up reminders, or register dose timing. Triggers: add drug to list, extract fields (name, dose, schedule, reminder timing), persist, sync scheduled dose reminders. Use when they name a medicine and want tracking or alerts — e.g. “add aspirin”, “set a reminder for metformin 500mg after dinner”, “remind me to take X in 5 minutes”, “put lipitor on my list”, “新增/加入 [藥名]”.
- **update_medication** — User wants to edit an existing medication entry (rename drug, change dosage, update schedule, add/change/remove instructions/notes) without deleting and re-adding it. Triggers: “change my aspirin to 81mg”, “update metformin schedule”, “add instruction to my aspirin”.
- **list_medications** — User asks what medications they have on file / their list / “what am I taking”.
- **remove_medication** — User wants to stop tracking or remove a drug from the list.
- **confirm_dose** — The user’s turn is **primarily about adherence logging**: they took a dose, or they are sending a follow-up **to add a note** on a dose already taken. Set **record_pending_dose_as_taken** and **dose_adherence_note** according to the structured rules above — not every symptom message is confirm_dose; ongoing pain without taking the dose is **general_question** with both adherence fields false/null.
- **report_missed_dose** — User explicitly says they **missed / skipped / forgot** a scheduled dose and wants that recorded as not taken. Examples: “I missed my morning pill”, “I forgot to take it”, “skip this dose”.
- **explain_medication** — User wants information about a drug: what it’s for, how it works, how to take it, not “add it to my list”. E.g. “what is metformin for”, “why do I take this pill”, “explain aspirin”.
- **interaction_check** — Combining drugs, food, or supplements: safety, interactions, “can I take A with B”.
- **log_vital** — Logging blood pressure, blood sugar, weight, or similar vitals.
- **request_summary** — Summary for a doctor visit or health recap.
- **update_profile** — Durable profile fields: how to address the user, age, gender, emergency contact, allergies, long-term health notes, and user preferences like reply language (`en`/`zh-TW`) or timezone. One-off symptoms **not** meant as a dose log belong here or **general_question**, not confirm_dose, unless they explicitly tie it to a dose log (then use confirm_dose + **dose_adherence_note**).
- **off_topic** — No health, medication, or care angle (e.g. weather, sports, coding). Rare for this app.
- **general_question** — Health-related chat that does not fit a tool above: vague symptoms, general advice, or clarification — use only when no more specific intent applies.

## Disambiguation (critical)

- Prefer **add_medication** over **general_question** when the user combines a drug name (or clear reference) with tracking, reminders, schedule, dose amount, or “add/save/remind/schedule/list on my meds”.
- Prefer **update_medication** over **add_medication** when the user clearly says to change an existing record (update/change/edit/modify current med details).
- Prefer **explain_medication** over **add_medication** when they only ask what/why/how about a drug without asking to save or remind.
- Prefer **interaction_check** over **explain_medication** when the question is about taking two or more substances together.
- Prefer **log_vital** over **general_question** when the user gives a concrete numeric reading (blood pressure, blood sugar/glucose, weight, pulse/heart rate, temperature, SpO2/oxygen).
- Prefer **report_missed_dose** over **general_question** when the user clearly reports a missed/forgotten/skipped scheduled dose.
- Do **not** choose **confirm_dose** from symptoms alone. If they report headache/pain/feeling unwell **without** clearly having taken the dose or logging a note for a dose already taken, use **general_question** and set **record_pending_dose_as_taken** false and **dose_adherence_note** null.
- **Short follow-ups** that answer the assistant’s prior question about dosing, reminders, or scheduling (e.g. “一次”, “三天”, “7”, “once”, “yes”, “ok”, “每天”) must **not** be **off_topic** — use **general_question** or the clinical intent that fits the prior turn; set adherence fields only when that prior turn was about **taking** a specific dose.
- If the user request is ambiguous, under-specified, or could refer to multiple medicines/times/records, prefer **general_question** so the assistant asks a clarification question before any irreversible action.
- For **add_medication**, if dose/schedule/instructions are not clearly present in the latest user message, still classify as **add_medication** when the user intent is to add/track — but do not assume missing details are user-confirmed facts. The assistant should confirm/clarify before final save when details are uncertain.

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
