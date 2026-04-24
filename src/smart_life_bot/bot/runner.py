"""Minimal bot runtime abstraction for transport wiring."""

from __future__ import annotations

from dataclasses import dataclass

from .telegram_transport import TelegramTransportResponse, TelegramTransportRouter


@dataclass(slots=True)
class TelegramBotRuntime:
    router: TelegramTransportRouter

    def on_start(self) -> TelegramTransportResponse:
        return self.router.handle_start()

    def on_text(self, telegram_user_id: int, text: str) -> TelegramTransportResponse:
        return self.router.handle_text_message(telegram_user_id=telegram_user_id, text=text)

    def on_callback(self, telegram_user_id: int, callback_data: str) -> TelegramTransportResponse:
        return self.router.handle_callback(telegram_user_id=telegram_user_id, callback_data=callback_data)
