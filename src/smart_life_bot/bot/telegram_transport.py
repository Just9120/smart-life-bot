"""Minimal Telegram transport mapping for Phase 1 foundation."""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    llm_available: bool = False

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
            buttons=self._build_draft_buttons_from_state(user.id),
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
            buttons=self._build_draft_buttons_from_state(user_id),
        )

    def _get_pending_draft_text(self, user_id: int) -> str:
        snapshot = self.state_repo.get(user_id)
        if snapshot is None or snapshot.draft is None:
            return "Черновик не найден. Отправьте событие заново."
        return format_preview_message(snapshot.draft)

    def _build_draft_buttons_from_state(self, user_id: int) -> tuple[tuple[str, str], ...]:
        snapshot = self.state_repo.get(user_id)
        if snapshot is None or snapshot.draft is None:
            return ()
        return _build_draft_buttons(snapshot.draft)

    def _build_settings_response(self, user_id: int) -> TelegramTransportResponse:
        settings = self.get_user_settings.execute(user_id=user_id)
        return TelegramTransportResponse(
            text=(
                "Settings\n\n"
                "Parser mode:\n"
                f"- Current: {self._human_parser_mode(settings.parser_mode)}\n\n"
                "Available:\n"
                "- 🐍 Python — active\n"
                f"- ⚡ Auto — {self._auto_availability_text()}\n"
                f"- 🤖 LLM — {self._llm_availability_text()}\n\n"
                "Python parser remains available as deterministic baseline."
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
            if self.llm_available:
                return "Auto (Python first, Claude fallback)"
            return "Auto (currently Python fallback)"
        if self.llm_available:
            return "LLM (Claude)"
        return "LLM (not available)"

    def _llm_availability_text(self) -> str:
        if self.llm_available:
            return "available via Claude"
        return "not available (configure Anthropic API key)"

    def _auto_availability_text(self) -> str:
        if self.llm_available:
            return "Python first, Claude fallback"
        return "Python fallback only (LLM not configured)"


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
    lines.extend(_format_parser_diagnostics(draft.metadata))
    validation_hint = _non_confirmable_draft_hint(draft)
    if validation_hint is not None:
        lines.append(validation_hint)
    lines.append("Событие НЕ будет создано, пока вы явно не нажмёте Confirm.")
    return "\n".join(lines)


def _build_draft_buttons(draft: EventDraft) -> tuple[tuple[str, str], ...]:
    if not _is_draft_confirmable(draft):
        return (
            ("✏️ Edit", CALLBACK_EDIT),
            ("❌ Cancel", CALLBACK_CANCEL),
        )
    return (
        ("✅ Confirm", CALLBACK_CONFIRM),
        ("✏️ Edit", CALLBACK_EDIT),
        ("❌ Cancel", CALLBACK_CANCEL),
    )


def _is_valid_iana_timezone(value: str | None) -> bool:
    if value is None:
        return False
    normalized = value.strip()
    if not normalized:
        return False
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError:
        return False
    return True


def _is_draft_confirmable(draft: EventDraft) -> bool:
    if draft.start_at is None:
        return False
    if not _is_valid_iana_timezone(draft.timezone):
        return False
    if draft.end_at is not None and draft.end_at <= draft.start_at:
        return False
    return True


def _non_confirmable_draft_hint(draft: EventDraft) -> str | None:
    if draft.start_at is None:
        return "Нужно указать start_at перед созданием события. Используйте /edit start_at <ISO-8601 datetime>."
    if not _is_valid_iana_timezone(draft.timezone):
        return "Нужно исправить timezone перед созданием события. Используйте /edit timezone Europe/Amsterdam."
    if draft.end_at is not None and draft.end_at <= draft.start_at:
        return "Нужно исправить время: end_at должен быть позже start_at."
    return None


def _format_parser_diagnostics(metadata: dict[str, str]) -> list[str]:
    lines = ["", "Парсинг:"]
    lines.append(f"- mode: {metadata.get('parser_mode', '—')}")
    lines.append(f"- route: {_human_parser_route(metadata.get('parser_router'))}")
    lines.append(f"- source: {_human_parser_source(metadata.get('source'))}")
    confidence = metadata.get("parser_confidence")
    lines.append(f"- confidence: {confidence if confidence else '—'}")
    issues = metadata.get("parser_issues")
    if issues:
        lines.append(f"- issues: {issues}")
    return lines


def _human_parser_source(value: str | None) -> str:
    mapping = {
        "rule-based-parser": "Python",
        "claude-parser": "Claude",
    }
    if value is None:
        return "—"
    return mapping.get(value, value)


def _human_parser_route(value: str | None) -> str:
    mapping = {
        "python": "Python",
        "llm_fallback": "Claude fallback",
        "python_fallback_llm_not_configured": "Python fallback, LLM not configured",
    }
    if value is None:
        return "—"
    return mapping.get(value, value)
