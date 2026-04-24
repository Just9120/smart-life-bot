"""Application entry point for Smart Life Ops Bot runtime foundation stage."""

from smart_life_bot.config.settings import Settings, load_settings
from smart_life_bot.observability.logger import get_logger


def run() -> str:
    """Load settings and print foundation bootstrap message."""
    settings: Settings = load_settings()
    logger = get_logger()
    message = (
        "Smart Life Ops Bot runtime foundation is ready "
        f"(env={settings.app_env}, auth_mode={settings.google_auth_mode.value}). "
        "Runtime integrations are pending implementation."
    )
    logger.info(message)
    print(message)
    return message


if __name__ == "__main__":
    run()
