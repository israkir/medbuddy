"""Logging filter that redacts known PHI keys from log record extra fields.

Install via ``logging.getLogger().addFilter(PhiRedactFilter())`` or by
configuring it in ``core/logging.py``.  The filter is purely additive —
it never drops records.

Covered field names come from the domain model and are intentionally
conservative: only fields that are direct identifiers or near-identifiers.
"""

from __future__ import annotations

import logging

from medbuddy.privacy.redact import redact_pii_text

_PHI_ATTRS: frozenset[str] = frozenset(
    {
        "preferred_name",
        "contact_name",
        "channel_value",
        "health_notes",
        "user_text",
        "safe_text",
        "display_name",
    }
)


class PhiRedactFilter(logging.Filter):
    """Mask PHI values in log-record extra attributes before they reach any handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        for attr in _PHI_ATTRS:
            val = getattr(record, attr, None)
            if isinstance(val, str):
                setattr(record, attr, redact_pii_text(val))
        return True
