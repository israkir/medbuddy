"""AppServices: the wired dependency graph passed through every request handler."""

from __future__ import annotations

from dataclasses import dataclass

from medbuddy.config import Settings
from medbuddy.protocols.drug_caches import DrugCachesPort
from medbuddy.protocols.conversation import ConversationStorePort
from medbuddy.protocols.drugs import DrugDataPort
from medbuddy.protocols.line import LineAudioBlobStorePort, LineMessagingPort
from medbuddy.protocols.llm import LLMPort
from medbuddy.protocols.speech import SpeechToTextPort, TextToSpeechPort
from medbuddy.protocols.user_data import UserDataPort


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
