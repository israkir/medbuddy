import base64
import hashlib
import hmac


def verify_line_signature(
    *, body: bytes, channel_secret: str, signature_header: str | None
) -> bool:
    if not channel_secret or not signature_header:
        return False
    mac = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(mac).decode("ascii")
    return hmac.compare_digest(expected, signature_header)
