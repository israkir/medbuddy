"""Ephemeral HTTPS-served blobs for LINE audio messages (LINE fetches ``originalContentUrl``)."""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field


@dataclass
class LineAudioBlobStore:
    """In-memory audio payloads with TTL (suitable for single-instance web workers)."""

    public_base_url: str
    ttl_seconds: float = 900.0
    _blobs: dict[str, tuple[float, bytes]] = field(default_factory=dict)

    def _prune_locked(self, now: float) -> None:
        dead = [k for k, (exp, _) in self._blobs.items() if exp <= now]
        for k in dead:
            del self._blobs[k]

    def put(self, data: bytes) -> str:
        now = time.monotonic()
        self._prune_locked(now)
        oid = secrets.token_urlsafe(16)
        self._blobs[oid] = (now + self.ttl_seconds, data)
        return oid

    def get(self, audio_id: str) -> bytes | None:
        now = time.monotonic()
        self._prune_locked(now)
        row = self._blobs.get(audio_id)
        if row is None:
            return None
        exp, data = row
        if exp <= now:
            del self._blobs[audio_id]
            return None
        return data

    def public_url(self, audio_id: str) -> str:
        base = self.public_base_url.rstrip("/")
        return f"{base}/v1/line/media/audio/{audio_id}"
