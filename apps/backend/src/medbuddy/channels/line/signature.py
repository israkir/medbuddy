"""LINE webhook signature validation — delegates to ``line-bot-sdk``."""

from __future__ import annotations

from linebot.v3 import SignatureValidator


def verify_line_signature(
    *, body: bytes, channel_secret: str, signature_header: str | None
) -> bool:
    if not channel_secret or not signature_header:
        return False
    validator = SignatureValidator(channel_secret)
    return bool(validator.validate(body.decode("utf-8"), signature_header))
