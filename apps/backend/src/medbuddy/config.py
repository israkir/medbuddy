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
    debug: bool = False

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
        default=True,
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

    mobile_bearer_token: str = Field(
        default="",
        description=(
            "Bearer token for standalone app protected routes under /v1/app/*. "
            "If empty and mock_external_services is True, Bearer is not required (local dev only)."
        ),
        validation_alias=AliasChoices("MEDBUDDY_MOBILE_BEARER_TOKEN", "mobile_bearer_token"),
    )

    @model_validator(mode="after")
    def _apply_integration_switch(self) -> Self:
        """MEDBUDDY_INTEGRATION wins over MOCK_EXTERNAL_SERVICES when set."""
        if self.medbuddy_integration is None:
            return self
        use_mock = self.medbuddy_integration == "mock"
        object.__setattr__(self, "mock_external_services", use_mock)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
