"""Use cases shared across delivery channels (LINE, standalone app).

LINE-specific UX (quick replies, reply tokens) stays in ``channels.line``; this package
holds workflow that both channels can call with the same ``AppServices`` wiring.
"""
