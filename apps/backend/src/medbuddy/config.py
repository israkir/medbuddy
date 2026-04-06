import os
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/backend/.env — works when cwd is repo root or apps/backend
_BACKEND_ENV = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_BACKEND_ENV, Path(".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "MedBuddy"
    debug: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEBUG", "debug", "MEDBUDDY_DEBUG"),
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level for medbuddy.* and uvicorn.error (DEBUG, INFO, WARNING, …)",
        validation_alias=AliasChoices("LOG_LEVEL", "log_level"),
    )

    locale: str = Field(
        default="zh-TW",
        description="BCP 47 tag for user-facing strings (JSON under medbuddy/locales/)",
        validation_alias=AliasChoices("MEDBUDDY_LOCALE", "locale"),
    )

    line_channel_secret: str = Field(default="", description="LINE Messaging API channel secret")
    line_channel_access_token: str = Field(
        default="",
        description="LINE channel access token for reply/push API",
    )

    mock_external_services: bool = Field(
        default=False,
        description="Use in-memory mocks for LINE, STT, TTS, LLM, drugs, storage",
        validation_alias=AliasChoices("mock_external_services", "MOCK_EXTERNAL_SERVICES"),
    )

    medbuddy_integration: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "medbuddy_integration",
            "MEDBUDDY_INTEGRATION",
            "INTEGRATION_MODE",
        ),
        description=(
            "Quick switch: when set, overrides mock_external_services — "
            "mock | local | dev, or real | live | production"
        ),
    )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalize_llm_provider(cls, v: object) -> str:
        if v is None or v == "":
            return "gemini"
        s = str(v).lower().strip()
        if s not in ("gemini", "openai"):
            msg = f"Invalid LLM_PROVIDER {v!r}; use gemini or openai"
            raise ValueError(msg)
        return s

    @field_validator("medbuddy_integration", mode="before")
    @classmethod
    def _normalize_medbuddy_integration(cls, v: object) -> str | None:
        if v is None or v == "":
            return None
        s = str(v).lower().strip()
        if s in ("mock", "local", "dev", "default"):
            return "mock"
        if s in ("real", "live", "production"):
            return "real"
        msg = f"Invalid integration mode {v!r}; use mock or real (aliases: local, live, …)"
        raise ValueError(msg)

    public_base_url: str = Field(
        default="http://localhost:8000",
        description="Public HTTPS base URL for LINE-accessible audio (production)",
    )

    # Real integrations (optional when mock_external_services is False)
    gemini_api_key: str = ""
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description=(
            "Gemini model id for google-genai generate_content (e.g. gemini-2.5-flash). "
            "Override if Google deprecates the default."
        ),
        validation_alias=AliasChoices("GEMINI_MODEL", "gemini_model"),
    )
    llm_provider: str = Field(
        default="gemini",
        description=(
            "Which LLM adapter to use in real mode: gemini (GEMINI_API_KEY) or "
            "openai (OPENAI_API_KEY)."
        ),
        validation_alias=AliasChoices("LLM_PROVIDER", "llm_provider"),
    )
    openai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"),
    )
    openai_model: str = Field(
        default="gpt-4.1-mini",
        description="OpenAI chat model id when LLM_PROVIDER=openai.",
        validation_alias=AliasChoices("OPENAI_MODEL", "openai_model"),
    )
    supabase_url: str = ""
    supabase_publishable_key: str = Field(
        default="",
        description=(
            "Supabase publishable API key (sb_publishable_...) or legacy anon JWT — "
            "PostgREST uses the anon role; pair with RLS policies in supabase/schema.sql"
        ),
        validation_alias=AliasChoices(
            "SUPABASE_PUBLISHABLE_KEY",
            "supabase_publishable_key",
            "SUPABASE_ANON_KEY",
            "supabase_anon_key",
        ),
    )
    whisper_service_url: str = ""

    conversation_history_turns: int = 5
    audio_temp_ttl_seconds: int = 60

    drug_reference_cache_ttl_hours: int = Field(
        default=168,
        ge=0,
        description="TTL for drug_reference_cache expires_at; 0 = no expiry",
        validation_alias=AliasChoices(
            "MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS",
            "drug_reference_cache_ttl_hours",
        ),
    )
    drug_personalization_cache_ttl_hours: int = Field(
        default=72,
        ge=0,
        description="TTL for drug_personalization_cache expires_at; 0 = no expiry",
        validation_alias=AliasChoices(
            "MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS",
            "drug_personalization_cache_ttl_hours",
        ),
    )

    mobile_bearer_token: str = Field(
        default="",
        description=(
            "Bearer token for standalone app protected routes under /v1/app/*. "
            "If empty and mock_external_services is True, Bearer is not required (local dev only)."
        ),
        validation_alias=AliasChoices("MEDBUDDY_MOBILE_BEARER_TOKEN", "mobile_bearer_token"),
    )

    redis_url: str = Field(
        default="",
        description="Redis DSN for arq reminder jobs (e.g. redis://localhost:6379)",
        validation_alias=AliasChoices("REDIS_URL", "redis_url"),
    )

    cron_secret: str = Field(
        default="",
        description="Shared secret for POST /internal/reminders/reconcile (X-Cron-Secret header)",
        validation_alias=AliasChoices("MEDBUDDY_CRON_SECRET", "cron_secret"),
    )

    reminder_default_local_time: str = Field(
        default="09:00",
        description="Local clock time (HH:MM) for once-daily dose reminder instants",
        validation_alias=AliasChoices(
            "MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME",
            "reminder_default_local_time",
        ),
    )

    reminder_horizon_days: int = Field(
        default=14,
        ge=1,
        le=90,
        description="Calendar days ahead to materialize dose_events per medication",
        validation_alias=AliasChoices("MEDBUDDY_REMINDER_HORIZON_DAYS", "reminder_horizon_days"),
    )

    @model_validator(mode="after")
    def _apply_integration_switch(self) -> Self:
        """MEDBUDDY_INTEGRATION wins over MOCK_EXTERNAL_SERVICES when set."""
        if self.medbuddy_integration is None:
            return self
        use_mock = self.medbuddy_integration == "mock"
        object.__setattr__(self, "mock_external_services", use_mock)
        return self

    @model_validator(mode="after")
    def _render_host_production_defaults(self) -> Self:
        """Render sets ``RENDER=true`` on web services—always real integrations, never debug."""
        flag = os.environ.get("RENDER", "").strip().lower()
        if flag not in ("1", "true", "yes"):
            return self
        object.__setattr__(self, "mock_external_services", False)
        object.__setattr__(self, "debug", False)
        if self.medbuddy_integration == "mock":
            object.__setattr__(self, "medbuddy_integration", "real")
        return self

    @property
    def active_llm_model_id(self) -> str:
        """Model id used for cache provenance when the configured LLM generates text."""
        if self.llm_provider == "openai":
            return self.openai_model
        return self.gemini_model


@lru_cache
def get_settings() -> Settings:
    return Settings()
