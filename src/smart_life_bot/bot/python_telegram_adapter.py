"""Telegram SDK adapter mapping python-telegram-bot updates to transport runtime."""

from __future__ import annotations

from dataclasses import dataclass

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from smart_life_bot.config.settings import Settings

from .runner import TelegramBotRuntime
from .telegram_transport import (
    CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX,
    CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX,
    CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX,
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
    CALLBACK_EDIT,
    CALLBACK_DURATION,
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


_ALLOWED_CALLBACKS = (
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
    CALLBACK_CASHBACK_TRANSITION_CANCEL,
    CALLBACK_CALENDAR_DATE_START,
    CALLBACK_CALENDAR_DATE_CANCEL,
)
_ALLOWED_CALLBACK_PREFIXES = (
    CALLBACK_CASHBACK_LIST_MONTH_PREFIX,
    CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX,
    CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX,
    CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX,
    CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX,
    CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX,
    CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX,
    CALLBACK_CALENDAR_DATE_MONTH_PREFIX,
    CALLBACK_CALENDAR_DATE_SELECT_PREFIX,
    CALLBACK_CALENDAR_DATE_NOOP_PREFIX,
)
_CALLBACK_PATTERN = (
    r"^(draft:confirm|draft:edit|draft:cancel|draft:duration|draft:reminders|"
    r"draft:reminders:10|draft:reminders:30|draft:reminders:60|draft:reminders:120|"
    r"settings:parser:python|settings:parser:auto|settings:parser:llm|"
    r"calendar:mode:quick|calendar:mode:personal|"
    r"calendar:date:start|calendar:date:month:[a-f0-9]{6}:\d{4}-\d{2}|calendar:date:select:[a-f0-9]{6}:\d{4}-\d{2}-\d{2}|calendar:date:noop:[a-f0-9]{6}:\d{4}-\d{2}|calendar:date:cancel|"
    r"cashback:list:current|cashback:list:month:\d{4}-\d{2}|"
    r"cashback:list:owner:\d+:month:\d{4}-\d{2}|cashback:list:owner-current:\d+|"
    r"cashback:delete:request:\d+|cashback:delete:confirm:\d+|cashback:delete:cancel:\d+|"
    r"cashback:transition:select:(?:[a-f0-9]{6}:)?\d{4}-\d{2}|cashback:transition:cancel)$"
)


@dataclass(slots=True)
class TelegramSDKAdapter:
    """Thin adapter that delegates SDK updates to :class:`TelegramBotRuntime`."""

    runtime: TelegramBotRuntime

    async def handle_start(self, update: Update, context: CallbackContext[Application]) -> None:
        del context
        if update.message is None:
            return
        response = self.runtime.on_start()
        await _reply_from_transport(update.message, response)

    async def handle_text_message(self, update: Update, context: CallbackContext[Application]) -> None:
        del context
        if update.message is None or update.message.text is None or update.effective_user is None:
            return

        response = self.runtime.on_text(
            telegram_user_id=update.effective_user.id,
            text=update.message.text,
        )
        await _reply_from_transport(update.message, response)

    async def handle_settings(self, update: Update, context: CallbackContext[Application]) -> None:
        del context
        if update.message is None or update.effective_user is None:
            return

        response = self.runtime.on_text(
            telegram_user_id=update.effective_user.id,
            text="/settings",
        )
        await _reply_from_transport(update.message, response)

    async def handle_callback_query(self, update: Update, context: CallbackContext[Application]) -> None:
        del context
        query = update.callback_query
        if query is None or query.from_user is None:
            return

        await query.answer()
        callback_data = query.data or ""
        response = self.runtime.on_callback(
            telegram_user_id=query.from_user.id,
            callback_data=callback_data,
        )

        if query.message is not None:
            await _reply_from_transport(query.message, response)


def transport_buttons_to_inline_markup(buttons: tuple[tuple[str, str], ...]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None

    keyboard = [[InlineKeyboardButton(text=label, callback_data=callback_data)] for label, callback_data in buttons]
    return InlineKeyboardMarkup(keyboard)


def transport_button_rows_to_inline_markup(button_rows: tuple[tuple[tuple[str, str], ...], ...]) -> InlineKeyboardMarkup | None:
    if not button_rows:
        return None
    keyboard = [
        [InlineKeyboardButton(text=label, callback_data=callback_data) for label, callback_data in row]
        for row in button_rows
    ]
    return InlineKeyboardMarkup(keyboard)


async def _reply_from_transport(message: Message, response: TelegramTransportResponse) -> None:
    reply_markup = transport_button_rows_to_inline_markup(response.button_rows)
    if reply_markup is None:
        reply_markup = transport_buttons_to_inline_markup(response.buttons)
    if reply_markup is None:
        reply_markup = transport_reply_keyboard_to_markup(response.reply_keyboard)
    await message.reply_text(
        text=response.text,
        reply_markup=reply_markup,
    )

def transport_reply_keyboard_to_markup(reply_keyboard: tuple[tuple[str, ...], ...]) -> ReplyKeyboardMarkup | None:
    if not reply_keyboard:
        return None
    return ReplyKeyboardMarkup([list(row) for row in reply_keyboard], resize_keyboard=True, is_persistent=True)


async def _post_init_set_commands(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand(command="start", description="start/open main menu"),
            BotCommand(command="settings", description="parser/settings"),
        ]
    )


def build_telegram_application(settings: Settings, runtime: TelegramBotRuntime) -> Application:
    """Build telegram.ext.Application and register deterministic handlers."""
    application = Application.builder().token(settings.telegram_bot_token).post_init(_post_init_set_commands).build()

    adapter = TelegramSDKAdapter(runtime=runtime)
    application.add_handler(CommandHandler("start", adapter.handle_start))
    application.add_handler(CommandHandler("settings", adapter.handle_settings))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, adapter.handle_text_message))
    application.add_handler(CallbackQueryHandler(adapter.handle_callback_query, pattern=_CALLBACK_PATTERN))

    application.bot_data["allowed_callback_data"] = _ALLOWED_CALLBACKS
    application.bot_data["allowed_callback_prefixes"] = _ALLOWED_CALLBACK_PREFIXES
    return application


__all__ = [
    "TelegramSDKAdapter",
    "build_telegram_application",
    "transport_buttons_to_inline_markup",
    "transport_reply_keyboard_to_markup",
    "_post_init_set_commands",
]
