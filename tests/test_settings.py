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
