"""Wire protocols to mock or real implementations based on settings."""

from __future__ import annotations

import logging

import httpx

from medbuddy.config import Settings
from medbuddy.engine.types import AppServices
from medbuddy.protocols.ports import LLMPort, ObjectStoragePort
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
from medbuddy.integrations.caching_drugs import CachingDrugData
from medbuddy.integrations.drugs_http import HttpDrugData
from medbuddy.integrations.edge_tts_service import EdgeTtsService
from medbuddy.integrations.tts.tts_google import GoogleTextToSpeech
from medbuddy.integrations.llm.gemini_llm import GeminiLLM
from medbuddy.integrations.llm.openai_llm import OpenAILLM
from medbuddy.integrations.line_client import LineHttpClient
from medbuddy.integrations.local_public_storage import LocalPublicObjectStorage
from medbuddy.integrations.stt.stt_google import GoogleSpeechToText

log = logging.getLogger(__name__)


def _build_tts(settings: Settings, storage: ObjectStoragePort):
    if settings.tts_provider == "google":
        try:
            import google.cloud.texttospeech_v1  # noqa: F401
        except ImportError:
            log.warning(
                "TTS_PROVIDER=google but google-cloud-texttospeech is not installed; "
                "falling back to Edge TTS or mock"
            )
        else:
            pin = settings.google_tts_language_code.strip() or None
            voice_raw = settings.google_tts_voice_name.strip()
            voice_name = voice_raw or None
            tts_creds = settings.google_tts_application_credentials.strip() or None
            return GoogleTextToSpeech(
                storage=storage,
                pinned_language_code=pin,
                fallback_locale=settings.locale,
                voice_name=voice_name,
                credentials_path=tts_creds,
            )
    try:
        ev = settings.locale.replace("_", "-").strip().lower()
        default_voice = (
            "en-US-JennyNeural" if ev == "en" or ev.startswith("en-") else "zh-TW-HsiaoChenNeural"
        )
        return EdgeTtsService(storage=storage, voice=default_voice)
    except ImportError:
        log.warning("edge-tts not installed; using MockTextToSpeech for TTS")
        return MockTextToSpeech(storage=storage)


def _build_llm(settings: Settings) -> LLMPort:
    loc = settings.locale
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            log.warning("OPENAI_API_KEY missing (LLM_PROVIDER=openai); using MockLLM")
            return MockLLM(locale=loc)
        return OpenAILLM(
            api_key=settings.openai_api_key,
            locale=loc,
            model=settings.openai_model,
        )
    if not settings.gemini_api_key:
        log.warning("GEMINI_API_KEY missing; using MockLLM")
        return MockLLM(locale=loc)
    return GeminiLLM(
        api_key=settings.gemini_api_key,
        locale=settings.locale,
        intent_model=settings.gemini_model,
    )


def build_app_services(
    settings: Settings,
    *,
    outbound_http: httpx.AsyncClient | None = None,
) -> AppServices:
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
            users=MockUserData(settings),
            conversations=InMemoryConversationStore(),
            settings=settings,
            drug_caches=None,
            internal_media=None,
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

    tts = _build_tts(settings, storage)

    llm = _build_llm(settings)

    if settings.google_speech_project_id:
        stt = GoogleSpeechToText(
            project_id=settings.google_speech_project_id,
            location=settings.google_speech_location,
            language_code=settings.locale,
        )
    else:
        log.warning("GOOGLE_SPEECH_PROJECT_ID missing; using MockSpeechToText for STT")
        stt = MockSpeechToText(locale=settings.locale)

    drug_caches = None
    drugs_backend: HttpDrugData | CachingDrugData = HttpDrugData(
        locale=settings.locale,
        http_client=outbound_http,
    )

    if settings.supabase_url and settings.supabase_publishable_key:
        try:
            from medbuddy.integrations.persistence.supabase_drug_caches import SupabaseDrugCaches
            from medbuddy.integrations.persistence.supabase_stores import (
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
            user_data = MockUserData(settings)
            conversations_store = InMemoryConversationStore()
        else:
            sb_client = create_supabase_client(settings)
            user_data = SupabaseUserData(sb_client, settings)
            conversations_store = SupabaseConversationStore(sb_client, user_data)
            drug_caches = SupabaseDrugCaches(sb_client, settings)
            drugs_backend = CachingDrugData(
                HttpDrugData(locale=settings.locale, http_client=outbound_http),
                drug_caches,
            )
    else:
        log.warning(
            "Real mode without Supabase: user and conversation data stay in memory. "
            "Set SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY (or SUPABASE_ANON_KEY; run "
            "supabase/schema.sql for RLS) for Postgres-backed persistence.",
        )
        user_data = MockUserData(settings)
        conversations_store = InMemoryConversationStore()

    internal_media = storage if isinstance(storage, LocalPublicObjectStorage) else None

    return AppServices(
        line=line,
        stt=stt,
        tts=tts,
        llm=llm,
        drugs=drugs_backend,
        storage=storage,
        users=user_data,
        conversations=conversations_store,
        settings=settings,
        drug_caches=drug_caches,
        internal_media=internal_media,
    )
