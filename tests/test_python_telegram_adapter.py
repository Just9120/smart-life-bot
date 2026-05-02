from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
pytest.importorskip("telegram")
from telegram import InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler

from smart_life_bot.bot import (
    CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX,
    CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX,
    CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX,
    CALLBACK_CASHBACK_ADD_START,
    CALLBACK_CASHBACK_SEARCH_HINT,
    CALLBACK_CASHBACK_EXPORT_CURRENT,
    CALLBACK_CASHBACK_EDIT_PERCENT_REQUEST_PREFIX,
    CALLBACK_CASHBACK_LIST_CURRENT,
    CALLBACK_CASHBACK_LIST_MONTH_PREFIX,
    CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX,
    CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX,
    CALLBACK_CASHBACK_TRANSITION_CANCEL,
    CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX,
    CALLBACK_CALENDAR_DATE_CANCEL,
    CALLBACK_CALENDAR_DATE_MONTH_PREFIX,
    CALLBACK_CALENDAR_DATE_SELECT_PREFIX,
    CALLBACK_CALENDAR_DATE_START,
    CALLBACK_CALENDAR_DATE_NOOP_PREFIX,
    CALLBACK_CANCEL,
    CALLBACK_CONFIRM,
    CALLBACK_DURATION,
    CALLBACK_EDIT,
    CALLBACK_REMINDERS,
    CALLBACK_REMINDERS_10,
    CALLBACK_REMINDERS_30,
    CALLBACK_REMINDERS_60,
    CALLBACK_REMINDERS_120,
    CALLBACK_SETTINGS_PARSER_AUTO,
    CALLBACK_SETTINGS_PARSER_LLM,
    CALLBACK_SETTINGS_PARSER_PYTHON,
    TelegramTransportResponse,
)
from smart_life_bot.bot.python_telegram_adapter import (
    _post_init_set_commands,
    TelegramSDKAdapter,
    build_telegram_application,
    transport_button_rows_to_inline_markup,
    transport_buttons_to_inline_markup,
    transport_reply_keyboard_to_markup,
)
from smart_life_bot.config.settings import Settings
from smart_life_bot.domain.enums import GoogleAuthMode
from smart_life_bot.runtime import build_runtime


class FakeMessage:
    def __init__(self, text: str | None = None, calls: list[str] | None = None) -> None:
        self.text = text
        self.calls = calls if calls is not None else []
        self.reply_calls: list[dict[str, object]] = []

    async def reply_text(self, text: str, reply_markup: object = None) -> None:
        self.calls.append("reply_text")
        self.reply_calls.append({"text": text, "reply_markup": reply_markup})


class FakeCallbackQuery:
    def __init__(self, data: str, user_id: int, message: FakeMessage, calls: list[str]) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=user_id)
        self.message = message
        self._calls = calls
        self.answered = False

    async def answer(self) -> None:
        self._calls.append("answer")
        self.answered = True


def _settings() -> Settings:
    return Settings(
        app_env="test",
        log_level="INFO",
        telegram_bot_token="test-token",
        google_auth_mode=GoogleAuthMode.OAUTH_USER_MODE,
        database_url="sqlite:///:memory:",
        default_timezone="UTC",
    )


def test_build_telegram_application_registers_handlers_without_network_calls() -> None:
    container = build_runtime(_settings())
    try:
        application = build_telegram_application(_settings(), container.runtime)

        registered_handlers = [handler for handlers in application.handlers.values() for handler in handlers]
        command_handlers = [handler for handler in registered_handlers if isinstance(handler, CommandHandler)]
        assert len(command_handlers) == 2
        assert {command for handler in command_handlers for command in handler.commands} == {"start", "settings"}
        assert any(isinstance(handler, MessageHandler) for handler in registered_handlers)

        callback_handlers = [
            handler for handler in registered_handlers if isinstance(handler, CallbackQueryHandler)
        ]
        assert len(callback_handlers) == 1
        assert (
            callback_handlers[0].pattern.pattern
            == r"^(draft:confirm|draft:edit|draft:cancel|draft:duration|draft:reminders|draft:reminders:10|draft:reminders:30|draft:reminders:60|draft:reminders:120|settings:parser:python|settings:parser:auto|settings:parser:llm|calendar:mode:quick|calendar:mode:personal|calendar:date:start|calendar:date:month:[a-f0-9]{6}:\d{4}-\d{2}|calendar:date:select:[a-f0-9]{6}:\d{4}-\d{2}-\d{2}|calendar:date:noop:[a-f0-9]{6}:\d{4}-\d{2}|calendar:date:cancel|cashback:list:current|cashback:add:start|cashback:search:hint|cashback:export:current|cashback:list:month:\d{4}-\d{2}|cashback:list:owner:(?:\d+|all):month:\d{4}-\d{2}|cashback:list:owner-current:(?:\d+|all)|cashback:delete:request:\d+|cashback:delete:confirm:\d+|cashback:delete:cancel:\d+|cashback:edit-percent:request:\d+|cashback:transition:select:(?:[a-f0-9]{6}:)?\d{4}-\d{2}|cashback:transition:cancel)$"
        )
        assert tuple(application.bot_data["allowed_callback_data"]) == (
            CALLBACK_CONFIRM,
            CALLBACK_EDIT,
            CALLBACK_CANCEL,
            CALLBACK_DURATION,
            CALLBACK_REMINDERS,
                    CALLBACK_REMINDERS_10,
            CALLBACK_REMINDERS_30,
            CALLBACK_REMINDERS_60,
            CALLBACK_REMINDERS_120,
            CALLBACK_SETTINGS_PARSER_PYTHON,
            CALLBACK_SETTINGS_PARSER_AUTO,
            CALLBACK_SETTINGS_PARSER_LLM,
            "calendar:mode:quick",
            "calendar:mode:personal",
            CALLBACK_CASHBACK_LIST_CURRENT,
            CALLBACK_CASHBACK_ADD_START,
            CALLBACK_CASHBACK_SEARCH_HINT,
            CALLBACK_CASHBACK_EXPORT_CURRENT,
            CALLBACK_CASHBACK_TRANSITION_CANCEL,
            CALLBACK_CALENDAR_DATE_START,
            CALLBACK_CALENDAR_DATE_CANCEL,
        )
        assert tuple(application.bot_data["allowed_callback_prefixes"]) == (
            CALLBACK_CASHBACK_LIST_MONTH_PREFIX,
            CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX,
            CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX,
            CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX,
            CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX,
            CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX,
            CALLBACK_CASHBACK_EDIT_PERCENT_REQUEST_PREFIX,
            CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX,
            CALLBACK_CALENDAR_DATE_MONTH_PREFIX,
            CALLBACK_CALENDAR_DATE_SELECT_PREFIX,
            CALLBACK_CALENDAR_DATE_NOOP_PREFIX,
        )
    finally:
        container.connection.close()


def test_transport_response_buttons_convert_to_inline_keyboard_markup() -> None:
    markup = transport_buttons_to_inline_markup(
        (
            ("✅ Создать событие", CALLBACK_CONFIRM),
            ("✏️ Edit", CALLBACK_EDIT),
            ("❌ Cancel", CALLBACK_CANCEL),
        )
    )

    assert isinstance(markup, InlineKeyboardMarkup)
    assert [[button.text for button in row] for row in markup.inline_keyboard] == [
        ["✅ Создать событие"],
        ["✏️ Edit"],
        ["❌ Cancel"],
    ]
    assert [[button.callback_data for button in row] for row in markup.inline_keyboard] == [
        [CALLBACK_CONFIRM],
        [CALLBACK_EDIT],
        [CALLBACK_CANCEL],
    ]


def test_transport_button_rows_render_as_real_inline_rows() -> None:
    markup = transport_button_rows_to_inline_markup(
        (
            (("⬅️", "calendar:date:month:abc123:2026-05"), ("2026-06", "calendar:date:month:abc123:2026-06"), ("➡️", "calendar:date:month:abc123:2026-07")),
            (("1", "calendar:date:select:abc123:2026-06-01"), ("2", "calendar:date:select:abc123:2026-06-02")),
            (("↩️ Отмена", "calendar:date:cancel"),),
        )
    )
    assert markup is not None
    assert len(markup.inline_keyboard) == 3
    assert [button.text for button in markup.inline_keyboard[0]] == ["⬅️", "2026-06", "➡️"]


def test_callback_pattern_accepts_owner_all_and_rejects_invalid_owner_token() -> None:
    container = build_runtime(_settings())
    try:
        application = build_telegram_application(_settings(), container.runtime)
        pattern = [
            handler for handlers in application.handlers.values() for handler in handlers if isinstance(handler, CallbackQueryHandler)
        ][0].pattern.pattern
        assert re.fullmatch(pattern, "cashback:list:owner:all:month:2026-05")
        assert re.fullmatch(pattern, "cashback:list:owner-current:all")
        assert re.fullmatch(pattern, CALLBACK_CASHBACK_ADD_START)
        assert re.fullmatch(pattern, CALLBACK_CASHBACK_SEARCH_HINT)
        assert re.fullmatch(pattern, "cashback:list:owner:foo:month:2026-05") is None
        assert re.fullmatch(pattern, "cashback:add") is None
        assert re.fullmatch(pattern, "cashback:add:start:extra") is None
        assert re.fullmatch(pattern, "cashback:search") is None
        assert re.fullmatch(pattern, "cashback:search:hint:extra") is None
    finally:
        container.connection.close()


def test_start_handler_delegates_to_runtime_on_start() -> None:
    runtime = Mock()
    runtime.on_start.return_value = TelegramTransportResponse(text="Welcome")
    adapter = TelegramSDKAdapter(runtime=runtime)
    message = FakeMessage()
    update = SimpleNamespace(message=message)

    asyncio.run(adapter.handle_start(update, context=None))

    runtime.on_start.assert_called_once_with()
    assert message.reply_calls[0]["text"] == "Welcome"


def test_reply_keyboard_is_mapped_separately_from_inline_markup() -> None:
    markup = transport_reply_keyboard_to_markup((("📅 Календарь",),))
    assert markup is not None
    assert [[button.text for button in row] for row in markup.keyboard] == [["📅 Календарь"]]


def test_post_init_registers_bot_commands() -> None:
    app = SimpleNamespace(bot=SimpleNamespace(set_my_commands=AsyncMock()))
    asyncio.run(_post_init_set_commands(app))
    app.bot.set_my_commands.assert_called_once()


def test_text_handler_delegates_to_runtime_on_text() -> None:
    runtime = Mock()
    runtime.on_text.return_value = TelegramTransportResponse(text="Preview")
    adapter = TelegramSDKAdapter(runtime=runtime)
    message = FakeMessage(text="Team sync at 10")
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=777))

    asyncio.run(adapter.handle_text_message(update, context=None))

    runtime.on_text.assert_called_once_with(telegram_user_id=777, text="Team sync at 10")
    assert message.reply_calls[0]["text"] == "Preview"


def test_settings_handler_delegates_to_runtime_on_text_settings() -> None:
    runtime = Mock()
    runtime.on_text.return_value = TelegramTransportResponse(text="Settings")
    adapter = TelegramSDKAdapter(runtime=runtime)
    message = FakeMessage(text="/settings")
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=778))

    asyncio.run(adapter.handle_settings(update, context=None))

    runtime.on_text.assert_called_once_with(telegram_user_id=778, text="/settings")
    assert message.reply_calls[0]["text"] == "Settings"


def test_callback_handler_delegates_and_answers_query() -> None:
    runtime = Mock()
    runtime.on_callback.return_value = TelegramTransportResponse(text="Handled callback")
    adapter = TelegramSDKAdapter(runtime=runtime)
    call_order: list[str] = []
    message = FakeMessage(calls=call_order)
    callback_query = FakeCallbackQuery(CALLBACK_CONFIRM, user_id=888, message=message, calls=call_order)
    update = SimpleNamespace(callback_query=callback_query)

    asyncio.run(adapter.handle_callback_query(update, context=None))

    runtime.on_callback.assert_called_once_with(telegram_user_id=888, callback_data=CALLBACK_CONFIRM)
    assert callback_query.answered is True
    assert call_order == ["answer", "reply_text"]


def test_callback_handler_preserves_existing_callback_data_values() -> None:
    runtime = Mock()
    runtime.on_callback.return_value = TelegramTransportResponse(text="ok")
    adapter = TelegramSDKAdapter(runtime=runtime)

    for callback_data in (CALLBACK_CONFIRM, CALLBACK_EDIT,
    CALLBACK_DURATION, CALLBACK_CANCEL):
        message = FakeMessage()
        callback_query = FakeCallbackQuery(callback_data, user_id=999, message=message, calls=[])
        update = SimpleNamespace(callback_query=callback_query)

        asyncio.run(adapter.handle_callback_query(update, context=None))

    assert [call.kwargs["callback_data"] for call in runtime.on_callback.call_args_list] == [
        CALLBACK_CONFIRM,
        CALLBACK_EDIT,
        CALLBACK_DURATION,
        CALLBACK_CANCEL,
    ]


def test_callback_pattern_accepts_supported_cashback_callbacks() -> None:
    container = build_runtime(_settings())
    try:
        application = build_telegram_application(_settings(), container.runtime)
        registered_handlers = [handler for handlers in application.handlers.values() for handler in handlers]
        callback_handler = next(handler for handler in registered_handlers if isinstance(handler, CallbackQueryHandler))
        pattern = callback_handler.pattern
        assert pattern is not None

        for callback_data in (
            CALLBACK_CASHBACK_LIST_CURRENT,
            f"{CALLBACK_CASHBACK_LIST_MONTH_PREFIX}2026-05",
            f"{CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX}1:month:2026-05",
            f"{CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX}1",
            f"{CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX}123",
            f"{CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX}123",
            f"{CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX}123",
            f"{CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX}abcdef:2026-05",
            f"{CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX}2026-05",
            CALLBACK_CASHBACK_TRANSITION_CANCEL,
        ):
            assert pattern.match(callback_data) is not None
    finally:
        container.connection.close()


def test_callback_pattern_rejects_unrelated_callback_data() -> None:
    container = build_runtime(_settings())
    try:
        application = build_telegram_application(_settings(), container.runtime)
        registered_handlers = [handler for handlers in application.handlers.values() for handler in handlers]
        callback_handler = next(handler for handler in registered_handlers if isinstance(handler, CallbackQueryHandler))
        pattern = callback_handler.pattern
        assert pattern is not None

        for callback_data in (
            "cashback:list:month:2026-5",
            "cashback:list:owner:abc:month:2026-05",
            "cashback:delete:request:abc",
            "cashback:transition:select:abcdef:26-05",
            "unknown:callback:data",
        ):
            assert pattern.match(callback_data) is None
    finally:
        container.connection.close()


def test_callback_handler_accepts_settings_callback_data_values() -> None:
    runtime = Mock()
    runtime.on_callback.return_value = TelegramTransportResponse(text="ok")
    adapter = TelegramSDKAdapter(runtime=runtime)

    for callback_data in (
        CALLBACK_SETTINGS_PARSER_PYTHON,
        CALLBACK_SETTINGS_PARSER_AUTO,
        CALLBACK_SETTINGS_PARSER_LLM,
    ):
        message = FakeMessage()
        callback_query = FakeCallbackQuery(callback_data, user_id=999, message=message, calls=[])
        update = SimpleNamespace(callback_query=callback_query)

        asyncio.run(adapter.handle_callback_query(update, context=None))

    assert [call.kwargs["callback_data"] for call in runtime.on_callback.call_args_list] == [
        CALLBACK_SETTINGS_PARSER_PYTHON,
        CALLBACK_SETTINGS_PARSER_AUTO,
        CALLBACK_SETTINGS_PARSER_LLM,
    ]
