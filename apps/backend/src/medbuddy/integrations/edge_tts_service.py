"""edge-tts synthesizes speech; uploads via ObjectStoragePort."""

from __future__ import annotations

import tempfile
from pathlib import Path

from medbuddy.protocols.ports import ObjectStoragePort, TextToSpeechPort


def _edge_voice_for_language(language_code: str | None, *, default_voice: str) -> str:
    """Pick an edge-tts voice from a BCP-47-ish tag (e.g. user profile ``en`` / ``zh-TW``)."""
    if not language_code or not str(language_code).strip():
        return default_voice
    s = str(language_code).replace("_", "-").strip().lower()
    if s == "en" or s.startswith("en-"):
        return "en-US-JennyNeural"
    if s in ("zh-tw", "zh", "zh-hk", "zh-cn") or s.startswith("zh-"):
        return "zh-TW-HsiaoChenNeural"
    return default_voice


class EdgeTtsService(TextToSpeechPort):
    def __init__(self, *, storage: ObjectStoragePort, voice: str = "zh-TW-HsiaoChenNeural") -> None:
        try:
            import edge_tts  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "Install medbuddy-api with `tts` extra: pip install 'medbuddy-api[tts]'"
            ) from e
        self._storage = storage
        self._default_voice = voice

    async def synthesize_to_m4a_url(
        self,
        text: str,
        base_public_url: str,
        *,
        language_code: str | None = None,
    ) -> tuple[str, int]:
        import edge_tts

        _ = base_public_url
        voice = _edge_voice_for_language(language_code, default_voice=self._default_voice)
        with tempfile.TemporaryDirectory() as tmp:
            mp3_path = Path(tmp) / "out.mp3"
            communicate = edge_tts.Communicate(text, voice=voice, rate="-10%")
            await communicate.save(str(mp3_path))
            data = mp3_path.read_bytes()
        url = await self._storage.upload_temp_audio(
            data=data,
            content_type="audio/mpeg",
            suffix=".mp3",
        )
        duration_ms = max(1000, min(600_000, len(text) * 120))
        return url, duration_ms
