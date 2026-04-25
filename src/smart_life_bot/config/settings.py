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
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None
    google_service_account_json: str | None = None
    google_shared_calendar_id: str | None = None


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value.strip()


def _optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


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
        google_oauth_client_id=_optional_env("GOOGLE_OAUTH_CLIENT_ID"),
        google_oauth_client_secret=_optional_env("GOOGLE_OAUTH_CLIENT_SECRET"),
        google_oauth_redirect_uri=_optional_env("GOOGLE_OAUTH_REDIRECT_URI"),
        google_service_account_json=google_service_account_json,
        google_shared_calendar_id=google_shared_calendar_id,
    )
