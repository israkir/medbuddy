"""Use cases shared across delivery channels (LINE, standalone app).

LINE-specific UX (quick replies, reply tokens) stays in ``channels.line``; this package
holds workflow that both channels can call with the same ``AppServices`` wiring.

Module layout:

- **Top level:** ``assistant_turn`` (channel entry), ``patient_llm_context``,
  ``vital_log_build``.
- **``pending/``:** early-turn handlers — ``try_resolve_*`` flows and ``locale_intents``.
- **``health_events/``:** classifier / vital timeline policy and LLM formatting for
  ``health_issue_events``.
- **``profile/``:** profile patches from chat, completion nudges, emergency-contact capture.
"""
