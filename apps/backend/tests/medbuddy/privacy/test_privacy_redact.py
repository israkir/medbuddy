"""PII redaction before external LLM calls."""

from datetime import UTC, datetime

from medbuddy.models.domain import ConversationTurn
from medbuddy.privacy.redact import REDACTED, redact_conversation_turns_for_llm, redact_pii_text


def test_redact_email() -> None:
    s = "reach me user@example.com thanks"
    assert redact_pii_text(s) == f"reach me {REDACTED} thanks"


def test_redact_taiwan_mobile() -> None:
    assert REDACTED in redact_pii_text("打給我0912345678")
    assert REDACTED in redact_pii_text("電話 0912-345-678")


def test_redact_long_digit_run() -> None:
    assert REDACTED in redact_pii_text("id 1234567890123 end")


def test_redact_conversation_turns() -> None:
    at = datetime.now(UTC)
    turns = [
        ConversationTurn(role="user", content="hi 0912345678", at=at),
        ConversationTurn(role="assistant", content="ok", at=at),
    ]
    out = redact_conversation_turns_for_llm(turns)
    assert REDACTED in out[0].content
    assert out[0].role == "user"
    assert out[1].content == "ok"
