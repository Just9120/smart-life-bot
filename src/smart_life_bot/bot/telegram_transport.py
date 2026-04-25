"""Minimal Telegram transport mapping for Phase 1 foundation."""

from __future__ import annotations

from dataclasses import dataclass

from smart_life_bot.application.dto import (
    CancelEventDraftInput,
    ConfirmEventDraftInput,
    EditEventDraftFieldInput,
    IncomingMessageInput,
)
from smart_life_bot.application.use_cases import (
    CancelEventDraftUseCase,
    ConfirmEventDraftUseCase,
    EditEventDraftFieldUseCase,
    GetUserSettingsUseCase,
    ProcessIncomingMessageUseCase,
    SetParserModeUseCase,
)
from smart_life_bot.domain.enums import ParserMode
from smart_life_bot.domain.models import EventDraft
from smart_life_bot.storage.interfaces import ConversationStateRepository, UsersRepository

CALLBACK_CONFIRM = "draft:confirm"
CALLBACK_CANCEL = "draft:cancel"
CALLBACK_EDIT = "draft:edit"
CALLBACK_SETTINGS_PARSER_PYTHON = "settings:parser:python"
CALLBACK_SETTINGS_PARSER_AUTO = "settings:parser:auto"
CALLBACK_SETTINGS_PARSER_LLM = "settings:parser:llm"


@dataclass(frozen=True, slots=True)
class TelegramTransportResponse:
    text: str
    buttons: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class TelegramTransportRouter:
    users_repo: UsersRepository
    state_repo: ConversationStateRepository
    process_incoming_message: ProcessIncomingMessageUseCase
    confirm_draft: ConfirmEventDraftUseCase
    cancel_draft: CancelEventDraftUseCase
    edit_draft_field: EditEventDraftFieldUseCase
    get_user_settings: GetUserSettingsUseCase
    set_parser_mode: SetParserModeUseCase
    default_timezone: str

    def handle_start(self) -> TelegramTransportResponse:
        return TelegramTransportResponse(
            text=(
                "Привет! Отправь текст события, и я подготовлю черновик для подтверждения.\n"
                "Команды: /start, /edit <field> <value>.\n"
                "Событие не будет создано, пока ты не нажмешь Confirm."
            )
        )

    def handle_text_message(self, telegram_user_id: int, text: str) -> TelegramTransportResponse:
        if not text.strip():
            return TelegramTransportResponse(text="Пустое сообщение. Отправьте текст события.")

        user = self.users_repo.get_or_create_by_telegram_id(
            telegram_user_id=telegram_user_id,
            timezone=self.default_timezone,
        )

        if text.startswith("/edit"):
            return self._handle_edit_command(user_id=user.id, command=text)
        if text.strip() == "/settings":
            return self._build_settings_response(user.id)

        normalized = text.strip()

        result = self.process_incoming_message.execute(IncomingMessageInput(user_id=user.id, text=normalized))
        if result.status != "preview_ready":
            return TelegramTransportResponse(text=result.message)

        draft = self._get_pending_draft_text(user.id)
        return TelegramTransportResponse(
            text=draft,
            buttons=(
                ("✅ Confirm", CALLBACK_CONFIRM),
                ("✏️ Edit", CALLBACK_EDIT),
                ("❌ Cancel", CALLBACK_CANCEL),
            ),
        )

    def handle_callback(self, telegram_user_id: int, callback_data: str) -> TelegramTransportResponse:
        user = self.users_repo.get_or_create_by_telegram_id(
            telegram_user_id=telegram_user_id,
            timezone=self.default_timezone,
        )

        if callback_data == CALLBACK_CONFIRM:
            result = self.confirm_draft.execute(ConfirmEventDraftInput(user_id=user.id))
            if result.status == "success" and result.provider_event_html_link:
                return TelegramTransportResponse(text=f"{result.message}\nGoogle Calendar: {result.provider_event_html_link}")
            return TelegramTransportResponse(text=result.message)

        if callback_data == CALLBACK_CANCEL:
            result = self.cancel_draft.execute(CancelEventDraftInput(user_id=user.id))
            return TelegramTransportResponse(text=result.message)

        if callback_data == CALLBACK_EDIT:
            return TelegramTransportResponse(
                text="Для редактирования используйте: /edit <field> <value>. Например: /edit title Sync update"
            )
        if callback_data == CALLBACK_SETTINGS_PARSER_PYTHON:
            result, _ = self.set_parser_mode.execute(user_id=user.id, parser_mode=ParserMode.PYTHON)
            settings_response = self._build_settings_response(user.id)
            return TelegramTransportResponse(text=f"{result.message}\n\n{settings_response.text}", buttons=settings_response.buttons)
        if callback_data == CALLBACK_SETTINGS_PARSER_AUTO:
            result, _ = self.set_parser_mode.execute(user_id=user.id, parser_mode=ParserMode.AUTO)
            settings_response = self._build_settings_response(user.id)
            return TelegramTransportResponse(text=f"{result.message}\n\n{settings_response.text}", buttons=settings_response.buttons)
        if callback_data == CALLBACK_SETTINGS_PARSER_LLM:
            result, _ = self.set_parser_mode.execute(user_id=user.id, parser_mode=ParserMode.LLM)
            settings_response = self._build_settings_response(user.id)
            return TelegramTransportResponse(text=f"{result.message}\n\n{settings_response.text}", buttons=settings_response.buttons)

        return TelegramTransportResponse(text="Неизвестное действие кнопки.")

    def _handle_edit_command(self, user_id: int, command: str) -> TelegramTransportResponse:
        parts = command.split(maxsplit=2)
        if len(parts) < 3:
            return TelegramTransportResponse(
                text="Формат: /edit <field> <value>. Поддерживаются поля: title, start_at, end_at, timezone, description, location."
            )

        _, field_name, field_value = parts
        normalized_value = field_value
        if field_name in {"description", "location"} and field_value.strip() == "--clear":
            normalized_value = ""
        result = self.edit_draft_field.execute(
            EditEventDraftFieldInput(user_id=user_id, field_name=field_name, field_value=normalized_value)
        )
        if result.status != "preview_ready":
            return TelegramTransportResponse(text=result.message)

        return TelegramTransportResponse(
            text=self._get_pending_draft_text(user_id),
            buttons=(
                ("✅ Confirm", CALLBACK_CONFIRM),
                ("✏️ Edit", CALLBACK_EDIT),
                ("❌ Cancel", CALLBACK_CANCEL),
            ),
        )

    def _get_pending_draft_text(self, user_id: int) -> str:
        snapshot = self.state_repo.get(user_id)
        if snapshot is None or snapshot.draft is None:
            return "Черновик не найден. Отправьте событие заново."
        return format_preview_message(snapshot.draft)

    def _build_settings_response(self, user_id: int) -> TelegramTransportResponse:
        settings = self.get_user_settings.execute(user_id=user_id)
        return TelegramTransportResponse(
            text=(
                "Settings\n\n"
                "Parser mode:\n"
                f"- Current: {self._human_parser_mode(settings.parser_mode)}\n\n"
                "Available:\n"
                "- 🐍 Python — active\n"
                "- ⚡ Auto — planned, currently falls back to Python\n"
                "- 🤖 LLM — planned, not available yet\n\n"
                "For now, Python is the only fully active parser implementation."
            ),
            buttons=(
                ("🐍 Python", CALLBACK_SETTINGS_PARSER_PYTHON),
                ("⚡ Auto", CALLBACK_SETTINGS_PARSER_AUTO),
                ("🤖 LLM", CALLBACK_SETTINGS_PARSER_LLM),
            ),
        )

    def _human_parser_mode(self, parser_mode: ParserMode) -> str:
        if parser_mode is ParserMode.PYTHON:
            return "Python / rule-based"
        if parser_mode is ParserMode.AUTO:
            return "Auto (currently Python fallback)"
        return "LLM (not implemented)"


def format_preview_message(draft: EventDraft) -> str:
    lines = [
        "Черновик события:",
        f"- title: {draft.title}",
        f"- start_at: {draft.start_at.isoformat() if draft.start_at else '—'}",
        f"- end_at: {draft.end_at.isoformat() if draft.end_at else '—'}",
        f"- timezone: {draft.timezone or '—'}",
    ]
    if draft.description:
        lines.append(f"- description: {draft.description}")
    if draft.location:
        lines.append(f"- location: {draft.location}")
    lines.append("Событие НЕ будет создано, пока вы явно не нажмёте Confirm.")
    return "\n".join(lines)
