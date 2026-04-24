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
    ProcessIncomingMessageUseCase,
)
from smart_life_bot.domain.models import EventDraft
from smart_life_bot.storage.interfaces import UsersRepository

CALLBACK_CONFIRM = "draft:confirm"
CALLBACK_CANCEL = "draft:cancel"
CALLBACK_EDIT = "draft:edit"


@dataclass(frozen=True, slots=True)
class TelegramTransportResponse:
    text: str
    buttons: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class TelegramTransportRouter:
    users_repo: UsersRepository
    process_incoming_message: ProcessIncomingMessageUseCase
    confirm_draft: ConfirmEventDraftUseCase
    cancel_draft: CancelEventDraftUseCase
    edit_draft_field: EditEventDraftFieldUseCase
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
        normalized = text.strip()
        if not normalized:
            return TelegramTransportResponse(text="Пустое сообщение. Отправьте текст события.")

        user = self.users_repo.get_or_create_by_telegram_id(
            telegram_user_id=telegram_user_id,
            timezone=self.default_timezone,
        )

        if normalized.startswith("/edit"):
            return self._handle_edit_command(user_id=user.id, command=normalized)

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
            return TelegramTransportResponse(text=result.message)

        if callback_data == CALLBACK_CANCEL:
            result = self.cancel_draft.execute(CancelEventDraftInput(user_id=user.id))
            return TelegramTransportResponse(text=result.message)

        if callback_data == CALLBACK_EDIT:
            return TelegramTransportResponse(
                text="Для редактирования используйте: /edit <field> <value>. Например: /edit title Sync update"
            )

        return TelegramTransportResponse(text="Неизвестное действие кнопки.")

    def _handle_edit_command(self, user_id: int, command: str) -> TelegramTransportResponse:
        parts = command.split(maxsplit=2)
        if len(parts) < 3:
            return TelegramTransportResponse(
                text="Формат: /edit <field> <value>. Поддерживаются поля: title, start_at, end_at, timezone, description, location."
            )

        _, field_name, field_value = parts
        result = self.edit_draft_field.execute(
            EditEventDraftFieldInput(user_id=user_id, field_name=field_name, field_value=field_value)
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
        snapshot = self.process_incoming_message.deps.state_repo.get(user_id)
        if snapshot is None or snapshot.draft is None:
            return "Черновик не найден. Отправьте событие заново."
        return format_preview_message(snapshot.draft)


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
