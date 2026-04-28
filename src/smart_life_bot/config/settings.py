"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from smart_life_bot.domain.enums import GoogleAuthMode


class ConfigurationError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    log_level: str
    telegram_bot_token: str
    google_auth_mode: GoogleAuthMode
    database_url: str
    default_timezone: str
    llm_provider: str | None = None
    anthropic_api_key: str | None = None
    llm_model: str | None = None
    llm_timeout_seconds: int = 20
    llm_max_retries: int = 2
    llm_max_tokens: int = 1000
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None
    google_service_account_json: str | None = None
    google_shared_calendar_id: str | None = None


_DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value.strip()


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def _optional_positive_int(name: str, default: int, *, allow_zero: bool = False) -> int:
    raw = _optional_env(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc

    if value < 0 or (value == 0 and not allow_zero):
        comparator = "a non-negative integer" if allow_zero else "a positive integer"
        raise ConfigurationError(f"{name} must be {comparator}")
    return value


def _is_placeholder_secret(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"<anthropic_api_key>", "your_key_here"}


def load_settings() -> Settings:
    """Load and validate runtime settings from environment variables."""
    raw_auth_mode = _require_env("GOOGLE_AUTH_MODE")
    try:
        auth_mode = GoogleAuthMode(raw_auth_mode)
    except ValueError as exc:
        supported_modes = ", ".join(mode.value for mode in GoogleAuthMode)
        raise ConfigurationError(
            f"Invalid GOOGLE_AUTH_MODE={raw_auth_mode!r}. Supported values: {supported_modes}"
        ) from exc

    llm_provider = _optional_env("LLM_PROVIDER")
    if llm_provider is not None:
        llm_provider = llm_provider.lower()
    if llm_provider not in {None, "anthropic"}:
        raise ConfigurationError("Unsupported LLM_PROVIDER. Supported values: anthropic")

    anthropic_api_key = _optional_env("ANTHROPIC_API_KEY")
    llm_model = _optional_env("LLM_MODEL")
    if llm_provider == "anthropic":
        if anthropic_api_key is None:
            raise ConfigurationError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        if _is_placeholder_secret(anthropic_api_key):
            raise ConfigurationError("ANTHROPIC_API_KEY contains a placeholder value; set a real key")
        if llm_model is None:
            llm_model = _DEFAULT_ANTHROPIC_MODEL

    google_service_account_json = _optional_env("GOOGLE_SERVICE_ACCOUNT_JSON")
    google_shared_calendar_id = _optional_env("GOOGLE_SHARED_CALENDAR_ID")
    if auth_mode is GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE:
        if not google_service_account_json:
            raise ConfigurationError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is required for service_account_shared_calendar_mode"
            )
        if not google_shared_calendar_id:
            raise ConfigurationError(
                "GOOGLE_SHARED_CALENDAR_ID is required for service_account_shared_calendar_mode"
            )

    return Settings(
        app_env=os.environ.get("APP_ENV", "dev").strip() or "dev",
        log_level=os.environ.get("LOG_LEVEL", "INFO").strip() or "INFO",
        telegram_bot_token=_require_env("TELEGRAM_BOT_TOKEN"),
        google_auth_mode=auth_mode,
        database_url=_require_env("DATABASE_URL"),
        default_timezone=_require_env("DEFAULT_TIMEZONE"),
        llm_provider=llm_provider,
        anthropic_api_key=anthropic_api_key,
        llm_model=llm_model,
        llm_timeout_seconds=_optional_positive_int("LLM_TIMEOUT_SECONDS", 20),
        llm_max_retries=_optional_positive_int("LLM_MAX_RETRIES", 2, allow_zero=True),
        llm_max_tokens=_optional_positive_int("LLM_MAX_TOKENS", 1000),
        google_oauth_client_id=_optional_env("GOOGLE_OAUTH_CLIENT_ID"),
        google_oauth_client_secret=_optional_env("GOOGLE_OAUTH_CLIENT_SECRET"),
        google_oauth_redirect_uri=_optional_env("GOOGLE_OAUTH_REDIRECT_URI"),
        google_service_account_json=google_service_account_json,
        google_shared_calendar_id=google_shared_calendar_id,
    )
