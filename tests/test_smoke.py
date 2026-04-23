from smart_life_bot.main import run


def test_run_returns_bootstrap_message() -> None:
    message = run()
    assert "bootstrap" in message.lower()
