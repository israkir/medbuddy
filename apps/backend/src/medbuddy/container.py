"""Wire protocols to mock or real implementations based on settings."""

from __future__ import annotations

import httpx

from medbuddy.config import Settings
from medbuddy.core.errors import ConfigError
from medbuddy.integrations.caching_drugs import CachingDrugData
from medbuddy.integrations.drugs_http import HttpDrugData
from medbuddy.integrations.line_audio_blob_store import LineAudioBlobStore
from medbuddy.integrations.line_client import LineHttpClient
from medbuddy.integrations.llm.gemini_llm import GeminiLLM
from medbuddy.integrations.llm.openai_llm import OpenAILLM
from medbuddy.integrations.mocks import (
    InMemoryConversationStore,
    MockDrugData,
    MockLineClient,
    MockLLM,
    MockSpeechToText,
    MockUserData,
)
from medbuddy.integrations.mocks.tts import MockTextToSpeech
from medbuddy.integrations.persistence.supabase_drug_caches import SupabaseDrugCaches
from medbuddy.integrations.persistence.supabase_stores import (
    SupabaseConversationStore,
    SupabaseUserData,
    create_supabase_client,
)
from medbuddy.integrations.stt.stt_google import GoogleSpeechToText
from medbuddy.integrations.tts.tts_google import GoogleTextToSpeech
from medbuddy.protocols.llm import LLMPort
from medbuddy.protocols.speech import TextToSpeechPort
from medbuddy.services import AppServices


def _build_llm(settings: Settings) -> LLMPort:
    loc = settings.locale
    if settings.llm_provider.value == "openai":
        if not settings.openai_api_key:
            raise ConfigError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAILLM(api_key=settings.openai_api_key, locale=loc, model=settings.openai_model)
    if not settings.gemini_api_key:
        raise ConfigError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
    return GeminiLLM(
        api_key=settings.gemini_api_key,
        locale=settings.locale,
        intent_model=settings.gemini_model,
    )


def _build_stt_tts(
    settings: Settings,
) -> tuple[GoogleSpeechToText, TextToSpeechPort | None]:
    if not settings.google_speech_project_id:
        raise ConfigError(
            "GOOGLE_SPEECH_PROJECT_ID is required in production mode for speech-to-text"
        )
    stt = GoogleSpeechToText(
        project_id=settings.google_speech_project_id,
        location=settings.google_speech_location,
        language_code=settings.locale,
    )
    tts: TextToSpeechPort | None = (
        GoogleTextToSpeech() if settings.line_voice_replies != "off" else None
    )
    return stt, tts


def build_app_services(
    settings: Settings,
    *,
    outbound_http: httpx.AsyncClient | None = None,
) -> AppServices:
    line_audio_blobs = LineAudioBlobStore(public_base_url=settings.public_base_url)

    if settings.is_mock:
        loc = settings.locale
        return AppServices(
            line=MockLineClient(),
            stt=MockSpeechToText(locale=loc),
            llm=MockLLM(locale=loc),
            drugs=MockDrugData(locale=loc),
            users=MockUserData(settings),
            conversations=InMemoryConversationStore(),
            settings=settings,
            line_audio_blobs=line_audio_blobs,
            tts=MockTextToSpeech(),
            drug_caches=None,
        )

    # Production mode — every dep must be present; fail fast with ConfigError.
    if not settings.line_channel_access_token:
        raise ConfigError("LINE_CHANNEL_ACCESS_TOKEN is required in production mode")
    if not settings.supabase_url or not settings.supabase_service_key:
        raise ConfigError("SUPABASE_URL and SUPABASE_SERVICE_KEY are required in production mode")

    line = LineHttpClient(channel_access_token=settings.line_channel_access_token)
    llm = _build_llm(settings)
    stt, tts = _build_stt_tts(settings)

    if outbound_http is None:
        raise ConfigError(
            "outbound_http must be provided by the lifespan context in production mode — "
            "call build_app_services with the shared AsyncClient from main.py"
        )
    drugs_http = HttpDrugData(locale=settings.locale, http_client=outbound_http)

    sb_client = create_supabase_client(settings)
    user_data = SupabaseUserData(sb_client, settings)
    conversations_store = SupabaseConversationStore(sb_client, user_data)
    drug_caches = SupabaseDrugCaches(sb_client, settings)
    drugs_backend = CachingDrugData(drugs_http, drug_caches)

    return AppServices(
        line=line,
        stt=stt,
        llm=llm,
        drugs=drugs_backend,
        users=user_data,
        conversations=conversations_store,
        settings=settings,
        line_audio_blobs=line_audio_blobs,
        tts=tts,
        drug_caches=drug_caches,
    )
