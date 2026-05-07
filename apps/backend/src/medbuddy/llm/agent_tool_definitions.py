"""OpenAI-compatible tool definitions for the medication agent orchestrator."""

from __future__ import annotations

# Shared descriptions — models route English and Traditional Chinese user text using these.
AGENT_TOOLS_OPENAI: list[dict[str, object]] = [
    {
        "type": "function",
        "function": {
            "name": "list_medications",
            "description": (
                "Show the patient's saved medication list (inventory only, not clock schedule). "
                "Use when they ask what medicines they have, 藥清單, 我吃什麼藥."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_upcoming_doses",
            "description": (
                "Show scheduled doses from reminders — what to take next, today, soon. "
                "Use for timing questions: 接下來要吃什麼, what's due, today's doses."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_medication",
            "description": (
                "Parse and save a new medication from the user's message (name, dose, schedule, reminders). "
                "May run multiple times if the user adds several drugs in one message."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_medication",
            "description": (
                "Remove ONE medication by id from the catalog shown in system context. "
                "Use when they name one drug to delete/stop tracking."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "medication_id": {
                        "type": "string",
                        "description": "UUID from the medication catalog in system context.",
                    },
                },
                "required": ["medication_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_all_medications",
            "description": (
                "Delete every medication on file. Use for clear all meds / 清除全部藥 / wipe my list / reset medications."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_medication",
            "description": (
                "Change fields of one existing medication (dosage, schedule, instructions, rename). "
                "Uses the user's words plus catalog ids."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "disable_reminders",
            "description": (
                "Turn off scheduled dose reminders without deleting medication entries. "
                "Use for clear all reminders / 取消提醒 / stop nagging / silence alerts. "
                "scope=all affects every medication; scope=single needs medication_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["all", "single"],
                        "description": "Whether to disable reminders for every medication or one.",
                    },
                    "medication_id": {
                        "type": "string",
                        "description": "Required when scope is single — UUID from catalog.",
                    },
                },
                "required": ["scope"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_dose",
            "description": (
                "Record that the user took a dose and/or attach a short note to adherence (吃了, took it)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "record_pending_dose_as_taken": {
                        "type": "boolean",
                        "description": "True if they clearly completed the scheduled dose.",
                    },
                    "dose_adherence_note": {
                        "type": "string",
                        "description": "Optional short note for the dose record (symptom, reaction).",
                    },
                },
                "required": ["record_pending_dose_as_taken"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_missed_dose",
            "description": "Record that the user missed or skipped a scheduled dose.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "explain_medication",
            "description": (
                "Educational info about a drug (what it is for, how to take). Not for saving to the list."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_side_effects",
            "description": (
                "User is currently experiencing a symptom they attribute to a medication they take."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "interaction_check",
            "description": (
                "Combining drugs, alcohol, food, supplements — safety / interactions / 喝酒, 一起吃."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_vital",
            "description": "Extract and save blood pressure, glucose, weight, temperature, etc.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_health_summary",
            "description": (
                "Doctor-visit summary: meds, concerns, suggested questions (回診報告, 給醫生看)."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_health_journal",
            "description": (
                "Summarize recent dose notes, vital logs, and adherence-related history for the user or clinician."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "simulate_notify_emergency_contact",
            "description": (
                "User reports urgent symptoms that are not clearly immediate 911-level but warrant alerting "
                "their emergency contact (e.g. severe dizziness with vomiting). Server simulates notifying "
                "the stored contact — no real SMS/voice call."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Short reason for the simulated notification.",
                    },
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": (
                "Update durable profile fields from natural language (name, age, emergency/family contact "
                "with phone, allergies, locale). Use when they share who to call in an emergency — not add_medication."
            ),
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
]
