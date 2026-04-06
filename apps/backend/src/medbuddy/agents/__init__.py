"""Agent layer — intent-driven tool dispatch for MedBuddy conversations.

Each ``AgentTool`` encapsulates one cohesive capability (medication CRUD,
drug lookup, interaction check, health summary). The ``MedicationAgent``
orchestrates tool selection and final reply composition.
"""
