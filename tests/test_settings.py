import pytest

from smart_life_bot.config.settings import ConfigurationError, load_settings


@pytest.fixture
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("GOOGLE_AUTH_MODE", "oauth_user_mode")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp.db")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")


def test_load_settings_success(base_env: None) -> None:
    settings = load_settings()
    assert settings.google_auth_mode.value == "oauth_user_mode"
    assert settings.app_env == "dev"
    assert settings.log_level == "INFO"
    assert settings.google_shared_calendar_id is None


def test_load_settings_fails_on_missing_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("GOOGLE_AUTH_MODE", "oauth_user_mode")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp.db")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")

    with pytest.raises(ConfigurationError):
        load_settings()


def test_load_settings_fails_on_invalid_auth_mode(base_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_AUTH_MODE", "invalid")

    with pytest.raises(ConfigurationError):
        load_settings()


def test_load_settings_requires_service_account_fields_for_service_account_mode(
    base_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_AUTH_MODE", "service_account_shared_calendar_mode")
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SHARED_CALENDAR_ID", raising=False)

    with pytest.raises(ConfigurationError, match="GOOGLE_SERVICE_ACCOUNT_JSON"):
        load_settings()

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "/tmp/service-account.json")
    with pytest.raises(ConfigurationError, match="GOOGLE_SHARED_CALENDAR_ID"):
        load_settings()


def test_load_settings_accepts_service_account_fields_for_service_account_mode(
    base_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_AUTH_MODE", "service_account_shared_calendar_mode")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "/tmp/service-account.json")
    monkeypatch.setenv("GOOGLE_SHARED_CALENDAR_ID", "calendar-id@example.com")

    settings = load_settings()
    assert settings.google_auth_mode.value == "service_account_shared_calendar_mode"
    assert settings.google_service_account_json == "/tmp/service-account.json"
    assert settings.google_shared_calendar_id == "calendar-id@example.com"


def test_load_settings_keeps_llm_disabled_when_provider_is_absent(base_env: None) -> None:
    settings = load_settings()
    assert settings.llm_provider is None
    assert settings.anthropic_api_key is None


def test_load_settings_requires_anthropic_key_when_provider_is_set(
    base_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        load_settings()


def test_load_settings_sets_default_model_for_anthropic_provider(
    base_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.delenv("LLM_MODEL", raising=False)

    settings = load_settings()
    assert settings.llm_provider == "anthropic"
    assert settings.llm_model == "claude-haiku-4-5-20251001"
