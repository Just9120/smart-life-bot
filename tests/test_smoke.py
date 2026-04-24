from smart_life_bot.main import run


def test_run_returns_foundation_message(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("GOOGLE_AUTH_MODE", "oauth_user_mode")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp.db")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")

    message = run()
    assert "runtime composition" in message.lower()
