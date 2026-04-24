from __future__ import annotations

import socket

from smart_life_bot.bot import CALLBACK_CANCEL, CALLBACK_CONFIRM, CALLBACK_EDIT
from smart_life_bot.config.settings import Settings
from smart_life_bot.domain.enums import GoogleAuthMode
from smart_life_bot.runtime import RuntimeContainer, build_runtime


def _settings(database_url: str = "sqlite:///:memory:") -> Settings:
    return Settings(
        app_env="dev",
        log_level="INFO",
        telegram_bot_token="token",
        google_auth_mode=GoogleAuthMode.OAUTH_USER_MODE,
        database_url=database_url,
        default_timezone="UTC",
    )


def test_build_runtime_initializes_sqlite_schema() -> None:
    container = build_runtime(_settings())
    try:
        tables = {
            row[0]
            for row in container.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"users", "provider_credentials", "conversation_state", "events_log"}.issubset(tables)
    finally:
        container.connection.close()


def test_build_runtime_wires_router_and_repositories() -> None:
    container = build_runtime(_settings())
    try:
        assert isinstance(container, RuntimeContainer)
        assert container.runtime.router.users_repo is container.users_repo
        assert container.runtime.router.state_repo is container.state_repo
        assert container.runtime.router.default_timezone == "UTC"
    finally:
        container.connection.close()


def test_runtime_on_text_returns_preview_response() -> None:
    container = build_runtime(_settings())
    try:
        response = container.runtime.on_text(telegram_user_id=1001, text="Team sync tomorrow")

        assert "Черновик события" in response.text
        assert any(label == "✅ Confirm" for label, _ in response.buttons)
    finally:
        container.connection.close()


def test_runtime_callback_flow_confirm_cancel_and_edit_mapping() -> None:
    container = build_runtime(_settings())
    try:
        user_id = 1002
        container.runtime.on_text(telegram_user_id=user_id, text="First event")

        edit_response = container.runtime.on_callback(telegram_user_id=user_id, callback_data=CALLBACK_EDIT)
        assert "/edit <field> <value>" in edit_response.text

        confirm_response = container.runtime.on_callback(telegram_user_id=user_id, callback_data=CALLBACK_CONFIRM)
        assert confirm_response.text == "Event created successfully"

        container.runtime.on_text(telegram_user_id=user_id, text="Second event")
        cancel_response = container.runtime.on_callback(telegram_user_id=user_id, callback_data=CALLBACK_CANCEL)
        assert cancel_response.text == "Draft cancelled and state reset to IDLE"
    finally:
        container.connection.close()


def test_runtime_composition_makes_no_network_calls(monkeypatch) -> None:
    def _deny_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("network access is not allowed in runtime composition tests")

    monkeypatch.setattr(socket, "create_connection", _deny_network)

    container = build_runtime(_settings())
    try:
        response = container.runtime.on_text(telegram_user_id=1003, text="No network please")
        assert "Черновик события" in response.text
    finally:
        container.connection.close()


def test_runtime_supports_in_memory_sqlite_database_url() -> None:
    container = build_runtime(_settings("sqlite:///:memory:"))
    try:
        container.runtime.on_text(telegram_user_id=1004, text="Memory DB event")
        user = container.users_repo.get_by_telegram_id(telegram_user_id=1004)
        assert user is not None
        logs = container.events_log_repo.list_for_user(user.id)
        assert len(logs) == 1
    finally:
        container.connection.close()
