from __future__ import annotations

import socket

from smart_life_bot.bot import CALLBACK_CANCEL, CALLBACK_CONFIRM, CALLBACK_EDIT
from smart_life_bot.config.settings import Settings
from smart_life_bot.calendar.google_calendar import GoogleCalendarService
from smart_life_bot.domain.enums import GoogleAuthMode
from smart_life_bot.parsing.router import ParserModeRouter
from smart_life_bot.parsing.claude import ClaudeMessageParser
from smart_life_bot.runtime.fakes import DevFakeCalendarService
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
        assert {"users", "provider_credentials", "conversation_state", "events_log", "user_preferences"}.issubset(
            tables
        )
    finally:
        container.connection.close()


def test_build_runtime_wires_router_and_repositories() -> None:
    container = build_runtime(_settings())
    try:
        assert isinstance(container, RuntimeContainer)
        assert container.runtime.router.users_repo is container.users_repo
        assert container.runtime.router.get_user_settings.deps.user_preferences_repo is container.user_preferences_repo
        assert container.runtime.router.state_repo is container.state_repo
        assert container.runtime.router.default_timezone == "UTC"
    finally:
        container.connection.close()




def test_build_runtime_wires_parser_mode_router() -> None:
    container = build_runtime(_settings())
    try:
        assert isinstance(container.runtime.router.process_incoming_message.deps.parser, ParserModeRouter)
        parser = container.runtime.router.process_incoming_message.deps.parser
        assert parser.llm_parser is None
    finally:
        container.connection.close()


def test_build_runtime_wires_claude_parser_when_llm_is_configured() -> None:
    settings = Settings(
        app_env="dev",
        log_level="INFO",
        telegram_bot_token="token",
        google_auth_mode=GoogleAuthMode.OAUTH_USER_MODE,
        database_url="sqlite:///:memory:",
        default_timezone="UTC",
        llm_provider="anthropic",
        anthropic_api_key="test-key",
        llm_model="claude-haiku-4-5-20251001",
    )
    container = build_runtime(settings)
    try:
        parser = container.runtime.router.process_incoming_message.deps.parser
        assert isinstance(parser, ParserModeRouter)
        assert isinstance(parser.llm_parser, ClaudeMessageParser)
    finally:
        container.connection.close()

def test_runtime_on_text_returns_preview_response() -> None:
    container = build_runtime(_settings())
    try:
        response = container.runtime.on_text(telegram_user_id=1001, text="Team sync tomorrow at 10:00")

        assert "Проверь черновик события" in response.text
        assert any(label == "✅ Confirm" for label, _ in response.buttons)

        user = container.users_repo.get_by_telegram_id(telegram_user_id=1001)
        assert user is not None
        logs = container.events_log_repo.list_for_user(user.id)
        assert len(logs) == 1
        assert logs[0].parsed_payload is not None
        metadata = logs[0].parsed_payload.get("metadata")
        assert isinstance(metadata, dict)
        assert metadata["parser_mode"] == "python"
        assert metadata["parser_router"] == "python"
    finally:
        container.connection.close()




def test_runtime_uses_rule_based_parser_instead_of_fixed_fake_datetime() -> None:
    container = build_runtime(_settings())
    try:
        response = container.runtime.on_text(telegram_user_id=1007, text="завтра в 15:00 созвон")

        assert "2026-01-01T09:00:00+00:00" not in response.text
        assert "Дата и время:" in response.text
        assert "T15:00:00+00:00" in response.text
    finally:
        container.connection.close()
def test_runtime_callback_flow_confirm_cancel_and_edit_mapping() -> None:
    container = build_runtime(_settings())
    try:
        user_id = 1002
        container.runtime.on_text(telegram_user_id=user_id, text="First event 2026-04-26 09:00")

        edit_response = container.runtime.on_callback(telegram_user_id=user_id, callback_data=CALLBACK_EDIT)
        assert "/edit <field> <value>" in edit_response.text

        confirm_response = container.runtime.on_callback(telegram_user_id=user_id, callback_data=CALLBACK_CONFIRM)
        assert confirm_response.text == "Event created successfully"

        container.runtime.on_text(telegram_user_id=user_id, text="Second event 2026-04-26 10:00")
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
        assert "Проверь черновик события" in response.text
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


def test_runtime_edit_path_with_context_logger_kwargs_does_not_raise() -> None:
    container = build_runtime(_settings())
    try:
        container.runtime.on_text(telegram_user_id=1005, text="Edit logger check")
        response = container.runtime.on_text(telegram_user_id=1005, text="/edit title Updated")
        assert "Updated" in response.text
    finally:
        container.connection.close()


def test_runtime_uses_real_google_calendar_service_for_service_account_mode() -> None:
    settings = Settings(
        app_env="dev",
        log_level="INFO",
        telegram_bot_token="token",
        google_auth_mode=GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE,
        database_url="sqlite:///:memory:",
        default_timezone="UTC",
        google_service_account_json="/tmp/service-account.json",
        google_shared_calendar_id="calendar@example.com",
    )
    container = build_runtime(settings)
    try:
        assert isinstance(
            container.runtime.router.confirm_draft.deps.calendar_service,
            GoogleCalendarService,
        )
        assert container.runtime.router.supports_custom_reminders is False
    finally:
        container.connection.close()


def test_runtime_keeps_fake_calendar_service_for_oauth_mode() -> None:
    container = build_runtime(_settings())
    try:
        assert isinstance(
            container.runtime.router.confirm_draft.deps.calendar_service,
            DevFakeCalendarService,
        )
    finally:
        container.connection.close()


def test_runtime_confirm_failure_returns_graceful_response_when_calendar_fails(
    monkeypatch,
) -> None:
    def _raise_calendar_error(*args: object, **kwargs: object) -> object:
        raise RuntimeError("forced calendar failure")

    monkeypatch.setattr(DevFakeCalendarService, "create_event", _raise_calendar_error)

    container = build_runtime(_settings())
    try:
        container.runtime.on_text(telegram_user_id=1006, text="Force failure 2026-04-26 11:00")
        response = container.runtime.on_callback(telegram_user_id=1006, callback_data=CALLBACK_CONFIRM)
        assert response.text == "Event creation failed"
    finally:
        container.connection.close()
