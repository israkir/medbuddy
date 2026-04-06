"""Strip or mask direct identifiers before text is sent to third-party LLM APIs."""

from __future__ import annotations

import re

from medbuddy.models.domain import ConversationTurn

# Short, language-neutral placeholder (model must not echo verbatim PII).
REDACTED = "[…]"

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    re.IGNORECASE,
)

# Taiwan / international-ish phone shapes (conservative; avoids 3–4 digit doses like "500").
# Do not use ``\\b`` before ``09`` — it fails when the number follows CJK without whitespace.
_PHONE_RES = [
    re.compile(r"\+886[\s\-]?9\d{8}(?![0-9])"),
    re.compile(r"886[\s\-]?9\d{8}(?![0-9])"),
    re.compile(r"(?<![0-9])09\d{2}[\s\-]?\d{3}[\s\-]?\d{3}(?![0-9])"),
    re.compile(r"(?<![0-9])09\d{8}(?![0-9])"),
    re.compile(r"\(\d{2,4}\)\s*\d{3,4}[\s\-]?\d{4}\b"),
    re.compile(
        r"\b\+?\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{4}\b",
    ),
]

# Runs of digits that often encode government IDs, account numbers, etc.
_LONG_DIGITS_RE = re.compile(r"\b\d{10,}\b")


def redact_pii_text(text: str) -> str:
    """Return a copy of ``text`` with emails, typical phone patterns, and long digit runs masked."""
    if not text:
        return text
    out = _EMAIL_RE.sub(REDACTED, text)
    for rx in _PHONE_RES:
        out = rx.sub(REDACTED, out)
    out = _LONG_DIGITS_RE.sub(REDACTED, out)
    return out


def redact_conversation_turns_for_llm(turns: list[ConversationTurn]) -> list[ConversationTurn]:
    """Return new turns with message text passed through :func:`redact_pii_text`."""
    return [
        ConversationTurn(role=t.role, content=redact_pii_text(t.content), at=t.at) for t in turns
    ]
