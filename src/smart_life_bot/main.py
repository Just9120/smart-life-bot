"""Application entry point for Smart Life Ops Bot runtime foundation stage."""

from smart_life_bot.config.settings import Settings, load_settings
from smart_life_bot.observability.logger import get_logger
from smart_life_bot.runtime import RuntimeContainer, build_runtime


def run() -> str:
    """Load settings and build local/dev runtime composition graph."""
    settings: Settings = load_settings()
    container: RuntimeContainer = build_runtime(settings)

    logger = get_logger()
    message = (
        "Smart Life Ops Bot runtime composition is ready "
        f"(env={settings.app_env}, auth_mode={settings.google_auth_mode.value}, "
        f"database_url={settings.database_url}). "
        "Telegram runtime graph is built with SQLite + fake adapters; "
        "polling/webhook and external providers remain pending."
    )
    logger.info(message)
    print(message)

    container.connection.close()
    return message


if __name__ == "__main__":
    run()
