from __future__ import annotations

from dataclasses import dataclass

from medbuddy.config import Settings
from medbuddy.protocols.drug_caches import DrugCachesPort
from medbuddy.protocols.ports import (
    ConversationStorePort,
    DrugDataPort,
    LineAudioBlobStorePort,
    LineMessagingPort,
    LLMPort,
    SpeechToTextPort,
    TextToSpeechPort,
    UserDataPort,
)


@dataclass
class AppServices:
    line: LineMessagingPort
    stt: SpeechToTextPort
    llm: LLMPort
    drugs: DrugDataPort
    users: UserDataPort
    conversations: ConversationStorePort
    settings: Settings
    line_audio_blobs: LineAudioBlobStorePort
    tts: TextToSpeechPort | None
    drug_caches: DrugCachesPort | None = None
