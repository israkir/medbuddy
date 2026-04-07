from __future__ import annotations

from dataclasses import dataclass

from medbuddy.config import Settings
from medbuddy.protocols.drug_caches import DrugCachesPort
from medbuddy.protocols.ports import (
    ConversationStorePort,
    DrugDataPort,
    LineMessagingPort,
    LLMPort,
    SpeechToTextPort,
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
    drug_caches: DrugCachesPort | None = None
