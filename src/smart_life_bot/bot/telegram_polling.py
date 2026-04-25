"""Explicit Telegram long-polling entrypoint."""

from __future__ import annotations

from smart_life_bot.config.settings import Settings, load_settings
from smart_life_bot.runtime import build_runtime

from .python_telegram_adapter import build_telegram_application


def run_telegram_polling(settings: Settings | None = None) -> None:
    """Run Telegram polling explicitly (not used by default bootstrap entrypoint)."""
    active_settings = settings or load_settings()
    container = build_runtime(active_settings)
    try:
        application = build_telegram_application(active_settings, container.runtime)
        application.run_polling()
    finally:
        container.connection.close()


if __name__ == "__main__":
    run_telegram_polling()
