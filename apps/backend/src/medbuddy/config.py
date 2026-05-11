"""Application configuration — load from environment variables.

Use ``load_settings()`` at startup; ``get_settings()`` for cached access.
Each env-var name is canonical (one name per setting, no aliases).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

from medbuddy.core.errors import ConfigError

# Load .env when developing locally (no-op in production where vars are injected).
_BACKEND_ENV = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_BACKEND_ENV, override=False)
load_dotenv(Path(".env"), override=False)


# ---------------------------------------------------------------------------
# Enums — constrain the three multi-valued settings at the type level
# ---------------------------------------------------------------------------


class IntegrationMode(str, Enum):
    MOCK = "mock"
    PRODUCTION = "production"


class LlmProvider(str, Enum):
    GEMINI = "gemini"
    OPENAI = "openai"


class Locale(str, Enum):
    ZH_TW = "zh-TW"
    EN = "en"


# ---------------------------------------------------------------------------
# Settings dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    integration_mode: IntegrationMode
    locale: str  # BCP-47 tag; validated via Locale enum in load_settings
    log_level: str
    debug: bool

    line_channel_secret: str
    line_channel_access_token: str
    line_voice_replies: str  # "off" | "audio_inbound" | "always"

    public_base_url: str

    llm_provider: LlmProvider
    gemini_api_key: str
    gemini_model: str
    openai_api_key: str
    openai_model: str

    supabase_url: str
    supabase_service_key: str

    google_speech_project_id: str
    google_speech_location: str

    conversation_history_turns: int
    agent_orchestrator_history_turns: int
    dose_clarification_ttl_seconds: int
    drug_reference_cache_ttl_hours: int
    drug_personalization_cache_ttl_hours: int

    mobile_bearer_token: str
    redis_url: str
    cron_secret: str

    reminder_default_local_time: str
    reminder_horizon_days: int
    profile_completion_nudge_every_n_user_turns: int
    reminder_education_cta_every_n_days: int
    # Optional comma-separated allowlist; ``None`` = built-in defaults; ``all_non_off_topic`` alone = capture mode.
    health_issue_log_intents: tuple[str, ...] | None
    health_issue_summary_events_limit: int

    conversation_retention_days: int

    cors_allowed_origins: tuple[str, ...] = field(default_factory=tuple)
    reminder_nudge_intervals_minutes: tuple[int, ...] = field(default_factory=tuple)

    @property
    def is_mock(self) -> bool:
        return self.integration_mode == IntegrationMode.MOCK


# ---------------------------------------------------------------------------
# Loader — reads canonical env-var names, raises ConfigError on bad values
# ---------------------------------------------------------------------------


def _require(env: Mapping[str, str], key: str) -> str:
    val = env.get(key, "").strip()
    if not val:
        msg = f"Required env var {key!r} is not set"
        raise ConfigError(msg)
    return val


def _str(env: Mapping[str, str], key: str, default: str = "") -> str:
    return env.get(key, default).strip()


def _bool(env: Mapping[str, str], key: str, *, default: bool = False) -> bool:
    raw = env.get(key, "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no", ""):
        return default
    msg = f"Env var {key!r} must be a boolean (true/false); got {raw!r}"
    raise ConfigError(msg)


def _int(
    env: Mapping[str, str], key: str, *, default: int, ge: int | None = None, le: int | None = None
) -> int:
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        msg = f"Env var {key!r} must be an integer; got {raw!r}"
        raise ConfigError(msg)
    if ge is not None and val < ge:
        msg = f"Env var {key!r} must be >= {ge}; got {val}"
        raise ConfigError(msg)
    if le is not None and val > le:
        msg = f"Env var {key!r} must be <= {le}; got {val}"
        raise ConfigError(msg)
    return val


def _optional_health_issue_log_intents(env: Mapping[str, str]) -> tuple[str, ...] | None:
    raw = env.get("MEDBUDDY_HEALTH_ISSUE_LOG_INTENTS", "").strip()
    if not raw:
        return None
    if raw.lower() == "all_non_off_topic":
        return ("all_non_off_topic",)
    parts = tuple(p.strip() for p in raw.split(",") if p.strip())
    return parts if parts else None


def _cors_origins(env: Mapping[str, str]) -> tuple[str, ...]:
    raw = env.get("CORS_ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ()
    return tuple(o.strip() for o in raw.split(",") if o.strip())


def _nudge_intervals(env: Mapping[str, str], key: str) -> tuple[int, ...]:
    raw = env.get(key, "").strip()
    if not raw:
        return ()
    parts: list[int] = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        try:
            parts.append(max(1, int(p)))
        except ValueError:
            msg = f"Env var {key!r}: each value must be an integer; got {p!r}"
            raise ConfigError(msg)
    return tuple(parts)


def _integration_mode(env: Mapping[str, str]) -> IntegrationMode:
    raw = env.get("MEDBUDDY_INTEGRATION", "").strip().lower()
    if raw in ("", "mock"):
        return IntegrationMode.MOCK
    if raw == "production":
        return IntegrationMode.PRODUCTION
    msg = f"MEDBUDDY_INTEGRATION must be 'mock' or 'production'; got {raw!r}"
    raise ConfigError(msg)


def _locale(env: Mapping[str, str]) -> str:
    raw = env.get("MEDBUDDY_LOCALE", "zh-TW").strip()
    try:
        return Locale(raw).value
    except ValueError:
        allowed = ", ".join(m.value for m in Locale)
        msg = f"MEDBUDDY_LOCALE must be one of {allowed}; got {raw!r}"
        raise ConfigError(msg)


def _llm_provider(env: Mapping[str, str]) -> LlmProvider:
    raw = env.get("LLM_PROVIDER", "gemini").strip().lower()
    try:
        return LlmProvider(raw)
    except ValueError:
        allowed = ", ".join(m.value for m in LlmProvider)
        msg = f"LLM_PROVIDER must be one of {allowed}; got {raw!r}"
        raise ConfigError(msg)


def _line_voice_replies(env: Mapping[str, str]) -> str:
    raw = env.get("MEDBUDDY_LINE_VOICE_REPLIES", "").strip().lower()
    if not raw or raw in ("audio_inbound", "voice_in", "inbound", "inbound_audio"):
        return "audio_inbound"
    if raw in ("off", "false", "0", "no"):
        return "off"
    if raw in ("always", "all", "true", "1", "yes"):
        return "always"
    msg = f"MEDBUDDY_LINE_VOICE_REPLIES must be 'off', 'audio_inbound', or 'always'; got {raw!r}"
    raise ConfigError(msg)


def _reminder_local_time(env: Mapping[str, str]) -> str:
    raw = _str(env, "MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME", "09:00")
    if not re.fullmatch(r"\d{2}:\d{2}", raw):
        msg = f"MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME must be HH:MM (24-hour, zero-padded); got {raw!r}"
        raise ConfigError(msg)
    hour, minute = int(raw[:2]), int(raw[3:])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        msg = f"MEDBUDDY_REMINDER_DEFAULT_LOCAL_TIME must be a valid time 00:00–23:59; got {raw!r}"
        raise ConfigError(msg)
    return raw


def _assert_production_mode_secrets(env: Mapping[str, str], llm_provider: LlmProvider) -> None:
    """Raise ConfigError at startup if any secret required in production mode is absent."""
    required: list[tuple[str, str]] = [
        ("MEDBUDDY_MOBILE_BEARER_TOKEN", "mobile bearer token for /v1/app/* auth"),
        ("LINE_CHANNEL_SECRET", "LINE webhook signature verification"),
        ("LINE_CHANNEL_ACCESS_TOKEN", "LINE messaging API"),
        ("SUPABASE_URL", "Supabase project URL"),
        ("SUPABASE_SERVICE_KEY", "Supabase Secret API key (sb_secret_...)"),
        ("MEDBUDDY_CRON_SECRET", "cron reconcile endpoint auth"),
    ]
    llm_key = "GEMINI_API_KEY" if llm_provider == LlmProvider.GEMINI else "OPENAI_API_KEY"
    required.append((llm_key, f"LLM API key for provider={llm_provider.value}"))

    missing = [desc for var, desc in required if not env.get(var, "").strip()]
    if missing:
        joined = "; ".join(missing)
        msg = f"Missing required secrets for production mode: {joined}"
        raise ConfigError(msg)

    voice_replies = _line_voice_replies(env)
    public_base_url = _str(env, "PUBLIC_BASE_URL", "http://localhost:8000")
    if voice_replies != "off" and not public_base_url.lower().startswith("https:"):
        msg = (
            f"PUBLIC_BASE_URL must be HTTPS when MEDBUDDY_LINE_VOICE_REPLIES={voice_replies!r}. "
            "LINE requires HTTPS for audio content URLs. "
            f"Got PUBLIC_BASE_URL={public_base_url!r}."
        )
        raise ConfigError(msg)


def load_settings(env: Mapping[str, str] = os.environ) -> Settings:
    """Build Settings from environment variables. Raises ConfigError on invalid values."""
    integration_mode = _integration_mode(env)
    llm_provider = _llm_provider(env)
    if integration_mode == IntegrationMode.PRODUCTION:
        _assert_production_mode_secrets(env, llm_provider)
    return Settings(
        integration_mode=integration_mode,
        locale=_locale(env),
        log_level=_str(env, "LOG_LEVEL", "INFO"),
        debug=_bool(env, "DEBUG"),
        line_channel_secret=_str(env, "LINE_CHANNEL_SECRET"),
        line_channel_access_token=_str(env, "LINE_CHANNEL_ACCESS_TOKEN"),
        line_voice_replies=_line_voice_replies(env),
        public_base_url=_str(env, "PUBLIC_BASE_URL", "http://localhost:8000"),
        llm_provider=llm_provider,
        gemini_api_key=_str(env, "GEMINI_API_KEY"),
        gemini_model=_str(env, "GEMINI_MODEL", "gemini-2.5-flash"),
        openai_api_key=_str(env, "OPENAI_API_KEY"),
        openai_model=_str(env, "OPENAI_MODEL", "gpt-4.1-mini"),
        supabase_url=_str(env, "SUPABASE_URL"),
        supabase_service_key=_str(env, "SUPABASE_SERVICE_KEY"),
        google_speech_project_id=_str(env, "GOOGLE_SPEECH_PROJECT_ID"),
        google_speech_location=_str(env, "GOOGLE_SPEECH_LOCATION", "global"),
        conversation_history_turns=_int(env, "CONVERSATION_HISTORY_TURNS", default=5),
        agent_orchestrator_history_turns=_int(
            env, "MEDBUDDY_AGENT_ORCHESTRATOR_HISTORY_TURNS", default=12, ge=0, le=50
        ),
        dose_clarification_ttl_seconds=_int(
            env, "MEDBUDDY_DOSE_CLARIFICATION_TTL_SECONDS", default=900, ge=60, le=86400
        ),
        drug_reference_cache_ttl_hours=_int(
            env, "MEDBUDDY_DRUG_REFERENCE_CACHE_TTL_HOURS", default=168, ge=0
        ),
        drug_personalization_cache_ttl_hours=_int(
            env, "MEDBUDDY_DRUG_PERSONALIZATION_CACHE_TTL_HOURS", default=72, ge=0
        ),
        mobile_bearer_token=_str(env, "MEDBUDDY_MOBILE_BEARER_TOKEN"),
        redis_url=_str(env, "REDIS_URL"),
        cron_secret=_str(env, "MEDBUDDY_CRON_SECRET"),
        reminder_default_local_time=_reminder_local_time(env),
        reminder_horizon_days=_int(env, "MEDBUDDY_REMINDER_HORIZON_DAYS", default=14, ge=1, le=90),
        profile_completion_nudge_every_n_user_turns=_int(
            env,
            "MEDBUDDY_PROFILE_COMPLETION_NUDGE_EVERY_N_USER_TURNS",
            default=12,
            ge=0,
            le=500,
        ),
        reminder_education_cta_every_n_days=_int(
            env,
            "MEDBUDDY_REMINDER_EDUCATION_CTA_EVERY_N_DAYS",
            default=5,
            ge=0,
            le=30,
        ),
        health_issue_log_intents=_optional_health_issue_log_intents(env),
        health_issue_summary_events_limit=_int(
            env,
            "MEDBUDDY_HEALTH_ISSUE_SUMMARY_EVENTS_LIMIT",
            default=60,
            ge=1,
            le=200,
        ),
        reminder_nudge_intervals_minutes=_nudge_intervals(
            env, "MEDBUDDY_REMINDER_NUDGE_INTERVALS_MINUTES"
        ),
        conversation_retention_days=_int(
            env, "MEDBUDDY_CONVERSATION_RETENTION_DAYS", default=90, ge=1, le=3650
        ),
        cors_allowed_origins=_cors_origins(env),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
