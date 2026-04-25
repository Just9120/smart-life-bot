"""Telegram SDK adapter mapping python-telegram-bot updates to transport runtime."""

from __future__ import annotations

from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
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
    CALLBACK_CANCEL,
    CALLBACK_CONFIRM,
    CALLBACK_EDIT,
    TelegramTransportResponse,
)


_ALLOWED_CALLBACKS = (CALLBACK_CONFIRM, CALLBACK_EDIT, CALLBACK_CANCEL)
_CALLBACK_PATTERN = r"^(draft:confirm|draft:edit|draft:cancel)$"


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


async def _reply_from_transport(message: Message, response: TelegramTransportResponse) -> None:
    await message.reply_text(
        text=response.text,
        reply_markup=transport_buttons_to_inline_markup(response.buttons),
    )


def build_telegram_application(settings: Settings, runtime: TelegramBotRuntime) -> Application:
    """Build telegram.ext.Application and register deterministic handlers."""
    application = Application.builder().token(settings.telegram_bot_token).build()

    adapter = TelegramSDKAdapter(runtime=runtime)
    application.add_handler(CommandHandler("start", adapter.handle_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, adapter.handle_text_message))
    application.add_handler(CallbackQueryHandler(adapter.handle_callback_query, pattern=_CALLBACK_PATTERN))

    application.bot_data["allowed_callback_data"] = _ALLOWED_CALLBACKS
    return application


__all__ = ["TelegramSDKAdapter", "build_telegram_application", "transport_buttons_to_inline_markup"]
