import hashlib
import hmac
import base64

from medbuddy.channels.line.signature import verify_line_signature


def test_verify_line_signature_accepts_valid_mac():
    secret = "mysecret"
    body = b'{"events":[]}'
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    sig = base64.b64encode(mac).decode("ascii")
    assert verify_line_signature(body=body, channel_secret=secret, signature_header=sig) is True


def test_verify_line_signature_rejects_tamper():
    secret = "mysecret"
    body = b'{"events":[]}'
    bad = base64.b64encode(b"no").decode("ascii")
    assert verify_line_signature(body=body, channel_secret=secret, signature_header=bad) is False
