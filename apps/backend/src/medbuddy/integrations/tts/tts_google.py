"""Google Cloud Text-to-Speech → m4a for LINE (ffmpeg wraps AAC in MP4)."""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from google.cloud import texttospeech

from medbuddy.protocols.ports import TextToSpeechPort

log = logging.getLogger(__name__)

_MAX_SYNTH_CHARS = 4500


def _tts_bcp47_language(locale_tag: str) -> str:
    raw = (locale_tag or "").strip().replace("_", "-")
    lower = raw.lower()
    if lower in ("zh-tw", "cmn-hant-tw", "zh-hant-tw"):
        return "cmn-TW"
    if lower == "zh-cn" or lower == "cmn-hans-cn":
        return "cmn-CN"
    if lower.startswith("en"):
        return "en-US"
    if "-" in raw:
        return raw
    if lower == "zh":
        return "cmn-TW"
    return raw or "en-US"


def _mp3_to_m4a_with_duration(mp3: bytes) -> tuple[bytes, int]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        msg = "ffmpeg and ffprobe are required on PATH to build LINE m4a from TTS output"
        raise RuntimeError(msg)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        mp3_path = base / "tts.mp3"
        m4a_path = base / "reply.m4a"
        mp3_path.write_bytes(mp3)
        subprocess.run(
            [
                str(ffmpeg),
                "-y",
                "-i",
                str(mp3_path),
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                str(m4a_path),
            ],
            check=True,
            capture_output=True,
        )
        out = m4a_path.read_bytes()
        pr = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(m4a_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        duration_s = float((pr.stdout or "0").strip())
        duration_ms = max(1, int(round(duration_s * 1000)))
        return out, duration_ms


class GoogleTextToSpeech(TextToSpeechPort):
    def __init__(self) -> None:
        # Uses Application Default Credentials (same pattern as other Google clients).
        pass

    def _synthesize_mp3_sync(self, text: str, *, language_code: str) -> bytes:
        lang = _tts_bcp47_language(language_code)
        client = texttospeech.TextToSpeechClient()
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(
                language_code=lang,
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
            ),
            audio_config=texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,
            ),
        )
        return bytes(response.audio_content)

    async def synthesize_m4a(self, text: str, *, language_code: str) -> tuple[bytes, int]:
        trimmed = text.strip()
        if not trimmed:
            raise ValueError("empty TTS text")
        if len(trimmed) > _MAX_SYNTH_CHARS:
            log.warning(
                "Google TTS: truncating text from %d to %d chars for synthesis",
                len(trimmed),
                _MAX_SYNTH_CHARS,
            )
            trimmed = trimmed[:_MAX_SYNTH_CHARS]
        mp3 = await asyncio.to_thread(
            self._synthesize_mp3_sync, trimmed, language_code=language_code
        )
        log.info("Google TTS: synthesized MP3 bytes=%d locale=%s", len(mp3), language_code)
        return await asyncio.to_thread(_mp3_to_m4a_with_duration, mp3)
