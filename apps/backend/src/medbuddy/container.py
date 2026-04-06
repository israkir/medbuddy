"""Wire protocols to mock or real implementations based on settings."""

from __future__ import annotations

import logging

from medbuddy.config import Settings
from medbuddy.engine.types import AppServices
from medbuddy.integrations.mocks import (
    InMemoryConversationStore,
    MockDrugData,
    MockLineClient,
    MockLLM,
    MockObjectStorage,
    MockSpeechToText,
    MockTextToSpeech,
    MockUserData,
)
from medbuddy.integrations.drugs_http import HttpDrugData
from medbuddy.integrations.edge_tts_service import EdgeTtsService
from medbuddy.integrations.gemini_llm import GeminiLLM
from medbuddy.integrations.line_client import LineHttpClient
from medbuddy.integrations.local_public_storage import LocalPublicObjectStorage
from medbuddy.integrations.stt_whisper import WhisperHttpSTT

log = logging.getLogger(__name__)


def build_app_services(settings: Settings) -> AppServices:
    if settings.mock_external_services:
        storage = MockObjectStorage()
        tts = MockTextToSpeech(storage=storage)
        loc = settings.locale
        return AppServices(
            line=MockLineClient(),
            stt=MockSpeechToText(locale=loc),
            tts=tts,
            llm=MockLLM(locale=loc),
            drugs=MockDrugData(locale=loc),
            storage=storage,
            users=MockUserData(),
            conversations=InMemoryConversationStore(),
            settings=settings,
        )

    if not settings.line_channel_access_token:
        msg = "LINE channel access token is required when MOCK_EXTERNAL_SERVICES=false"
        raise ValueError(msg)

    line = LineHttpClient(channel_access_token=settings.line_channel_access_token)
    storage: LocalPublicObjectStorage | MockObjectStorage
    if settings.public_base_url:
        storage = LocalPublicObjectStorage(public_base_url=settings.public_base_url)
    else:
        log.warning("public_base_url empty; using mock storage (LINE audio URLs may be invalid)")
        storage = MockObjectStorage()

    try:
        tts = EdgeTtsService(storage=storage)
    except ImportError:
        log.warning("edge-tts not installed; using MockTextToSpeech for TTS")
        tts = MockTextToSpeech(storage=storage)

    if not settings.gemini_api_key:
        log.warning("GEMINI_API_KEY missing; using MockLLM")
        llm = MockLLM(locale=settings.locale)
    else:
        llm = GeminiLLM(
            api_key=settings.gemini_api_key,
            locale=settings.locale,
            intent_model=settings.gemini_model,
        )

    if settings.whisper_service_url:
        stt = WhisperHttpSTT(base_url=settings.whisper_service_url)
    else:
        log.warning("WHISPER_SERVICE_URL missing; using MockSpeechToText for STT")
        stt = MockSpeechToText(locale=settings.locale)

    if settings.supabase_url and settings.supabase_publishable_key:
        try:
            from medbuddy.integrations.supabase_stores import (
                SupabaseConversationStore,
                SupabaseUserData,
                create_supabase_client,
            )
        except ImportError:
            log.warning(
                "SUPABASE_URL and a publishable/anon key are set but the supabase "
                "package is not installed; install with pip install 'medbuddy-api[supabase]'. "
                "Using in-memory user and conversation stores.",
            )
            user_data = MockUserData()
            conversations_store = InMemoryConversationStore()
        else:
            sb_client = create_supabase_client(settings)
            user_data = SupabaseUserData(sb_client)
            conversations_store = SupabaseConversationStore(sb_client, user_data)
    else:
        log.warning(
            "Real mode without Supabase: user and conversation data stay in memory. "
            "Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY; run "
            "supabase/schema.sql for RLS) for Postgres-backed persistence.",
        )
        user_data = MockUserData()
        conversations_store = InMemoryConversationStore()

    return AppServices(
        line=line,
        stt=stt,
        tts=tts,
        llm=llm,
        drugs=HttpDrugData(locale=settings.locale),
        storage=storage,
        users=user_data,
        conversations=conversations_store,
        settings=settings,
    )
