from __future__ import annotations

from dataclasses import dataclass

from medbuddy.config import Settings
from medbuddy.protocols.drug_caches import DrugCachesPort
from medbuddy.protocols.ports import (
    ConversationStorePort,
    DrugDataPort,
    LineMessagingPort,
    LLMPort,
    ObjectStoragePort,
    SpeechToTextPort,
    TextToSpeechPort,
    UserDataPort,
)


@dataclass
class AppServices:
    line: LineMessagingPort
    stt: SpeechToTextPort
    tts: TextToSpeechPort
    llm: LLMPort
    drugs: DrugDataPort
    storage: ObjectStoragePort
    users: UserDataPort
    conversations: ConversationStorePort
    settings: Settings
    drug_caches: DrugCachesPort | None = None
