"""Minimal Telegram transport mapping for Phase 1 foundation."""

from __future__ import annotations

from dataclasses import dataclass

from smart_life_bot.application.draft_validation import detect_draft_validation_issue
from smart_life_bot.application.dto import (
    CancelEventDraftInput,
    ConfirmEventDraftInput,
    EditEventDraftFieldInput,
    IncomingMessageInput,
)
from smart_life_bot.application.cashback_use_cases import (
    AddCashbackCategoryUseCase,
    ListActiveCashbackCategoriesUseCase,
    QueryCashbackCategoryUseCase,
    parse_year_month,
    shift_year_month,
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
CALLBACK_DURATION = "draft:duration"
CALLBACK_REMINDERS = "draft:reminders"
CALLBACK_REMINDERS_10 = "draft:reminders:10"
CALLBACK_REMINDERS_30 = "draft:reminders:30"
CALLBACK_REMINDERS_60 = "draft:reminders:60"
CALLBACK_REMINDERS_120 = "draft:reminders:120"
CALLBACK_SETTINGS_PARSER_PYTHON = "settings:parser:python"
CALLBACK_SETTINGS_PARSER_AUTO = "settings:parser:auto"
CALLBACK_SETTINGS_PARSER_LLM = "settings:parser:llm"
CALLBACK_CASHBACK_LIST_CURRENT = "cashback:list:current"
CALLBACK_CASHBACK_LIST_MONTH_PREFIX = "cashback:list:month:"


@dataclass(frozen=True, slots=True)
class TelegramTransportResponse:
    text: str
    buttons: tuple[tuple[str, str], ...] = ()
    reply_keyboard: tuple[tuple[str, ...], ...] = ()


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
    supports_custom_reminders: bool = True
    add_cashback_category: AddCashbackCategoryUseCase | None = None
    query_cashback_category: QueryCashbackCategoryUseCase | None = None
    list_active_cashback_categories: ListActiveCashbackCategoriesUseCase | None = None

    def handle_start(self) -> TelegramTransportResponse:
        return TelegramTransportResponse(
            text=(
                "Привет! Можно сразу отправить текст события (например: Тест завтра в 15:00), и я покажу черновик.\n"
                "Раздел календаря доступен через меню внизу: 📅 Календарь.\n"
                "Событие не будет создано, пока ты не нажмешь Confirm."
            ),
            reply_keyboard=(("📅 Календарь", "💳 Кэшбек"),),
        )

    def handle_text_message(self, telegram_user_id: int, text: str) -> TelegramTransportResponse:
        if not text.strip():
            return TelegramTransportResponse(text="Пустое сообщение. Отправьте текст события.")

        user = self.users_repo.get_or_create_by_telegram_id(
            telegram_user_id=telegram_user_id,
            timezone=self.default_timezone,
        )

        normalized = text.strip()
        if self._is_transport_conflict(normalized):
            return TelegramTransportResponse(text="Похоже, здесь несколько вариантов. Что сделать?")

        if normalized == "📅 Календарь":
            return TelegramTransportResponse(
                text="Выберите режим календаря:",
                buttons=(("⚡ Быстрый режим", "calendar:mode:quick"), ("🔐 Личный Google Calendar", "calendar:mode:personal")),
                reply_keyboard=(("📅 Календарь", "💳 Кэшбек"),),
            )

        if normalized == "💳 Кэшбек":
            return TelegramTransportResponse(
                text=(
                    "💳 Кэшбек\n\n"
                    "Что можно сделать:\n\n"
                    "* добавить категорию: Альфа, Владимир, май, Супермаркеты, 5%\n"
                    "* быстро найти: Супермаркеты\n"
                    "* посмотреть всё за месяц: 📋 Активные категории\n\n"
                    "Владельцы: Виктор, Владимир, Елена."
                ),
                buttons=(("📋 Активные категории", CALLBACK_CASHBACK_LIST_CURRENT),),
            )

        if normalized == "📋 Активные категории" and self.list_active_cashback_categories is not None:
            result = self.list_active_cashback_categories.execute()
            return TelegramTransportResponse(text=result.text, buttons=self._build_cashback_month_nav_buttons(result.target_month))

        if self.add_cashback_category is not None:
            add_result = self.add_cashback_category.execute(normalized)
            if add_result is not None:
                return TelegramTransportResponse(text=add_result.text)


        if text.startswith("/edit"):
            return self._handle_edit_command(user_id=user.id, command=text)
        if text.strip() == "/settings":
            return self._build_settings_response(user.id)
        snapshot = self.state_repo.get(user.id)
        if snapshot is not None and snapshot.editing_field == "duration_minutes":
            result = self.edit_draft_field.execute(
                EditEventDraftFieldInput(user_id=user.id, field_name="duration_minutes", field_value=text.strip())
            )
            if result.status != "preview_ready":
                return TelegramTransportResponse(text="Введите положительное целое число минут, например: 20")
            updated = self.state_repo.get(user.id)
            if updated is not None:
                self.state_repo.set(updated.__class__(user_id=updated.user_id, state=updated.state, draft=updated.draft, editing_field=None))
            return TelegramTransportResponse(text=self._get_pending_draft_text(user.id), buttons=self._build_draft_buttons_from_state(user.id))

        if self.query_cashback_category is not None and "," not in normalized and normalized and normalized != "/start":
            cashback = self.query_cashback_category.execute(normalized)
            if "ничего не найдено" not in cashback.text:
                return TelegramTransportResponse(text=cashback.text)

        result = self.process_incoming_message.execute(IncomingMessageInput(user_id=user.id, text=normalized))
        if result.status != "preview_ready":
            return TelegramTransportResponse(text=result.message)

        draft = self._get_pending_draft_text(user.id)
        return TelegramTransportResponse(
            text=draft,
            buttons=self._build_draft_buttons_from_state(user.id),
        )

    def _is_transport_conflict(self, text: str) -> bool:
        lower = text.lower()
        has_calendar_marker = any(marker in lower for marker in ("завтра", "напомни", "в "))
        has_cashback_marker = ("кэшбек" in lower) or ("," in text and len([p for p in text.split(",") if p.strip()]) >= 4)
        return has_calendar_marker and has_cashback_marker

    def handle_callback(self, telegram_user_id: int, callback_data: str) -> TelegramTransportResponse:
        user = self.users_repo.get_or_create_by_telegram_id(
            telegram_user_id=telegram_user_id,
            timezone=self.default_timezone,
        )

        if callback_data == CALLBACK_CONFIRM:
            snapshot = self.state_repo.get(user.id)
            if snapshot is not None and snapshot.editing_field == "duration_minutes":
                return TelegramTransportResponse(text="Введите длительность в минутах, например: 20")
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
        if callback_data == "calendar:mode:quick":
            return TelegramTransportResponse(text="⚡ Быстрый режим: события создаются в подключенном общем календаре. Просто отправьте текст события. Уведомления в этом режиме настраиваются в Google Calendar; кастомные уведомления через бота пока недоступны.")
        if callback_data == "calendar:mode:personal":
            return TelegramTransportResponse(text="🔐 Личный Google Calendar (OAuth) пока недоступен. Мы планируем добавить подключение личного календаря позже; после реализации и проверки это даст более гибкое персональное управление, включая кастомные уведомления.")

        if callback_data == CALLBACK_DURATION:
            snapshot = self.state_repo.get(user.id)
            if snapshot is None or snapshot.draft is None:
                return TelegramTransportResponse(text="Нет черновика для редактирования длительности.")
            self.state_repo.set(snapshot.__class__(user_id=snapshot.user_id, state=snapshot.state, draft=snapshot.draft, editing_field="duration_minutes"))
            return TelegramTransportResponse(text="Введите длительность в минутах, например: 20")
        if callback_data == CALLBACK_REMINDERS and not self.supports_custom_reminders:
            return TelegramTransportResponse(text="Настройка уведомлений пока недоступна в быстром режиме календаря. Уведомления можно настроить в Google Calendar.")
        if callback_data == CALLBACK_REMINDERS:
            snapshot = self.state_repo.get(user.id)
            if snapshot is None or snapshot.draft is None:
                return TelegramTransportResponse(text="Нет черновика для редактирования уведомлений.")
            return TelegramTransportResponse(
                text="Выберите уведомления для события:",
                buttons=(
                    ("10 минут", CALLBACK_REMINDERS_10),
                    ("30 минут", CALLBACK_REMINDERS_30),
                    ("1 час", CALLBACK_REMINDERS_60),
                    ("2 часа", CALLBACK_REMINDERS_120),
                ),
            )
        reminder_callback_mapping = {
            CALLBACK_REMINDERS_10: "10",
            CALLBACK_REMINDERS_30: "30",
            CALLBACK_REMINDERS_60: "60",
            CALLBACK_REMINDERS_120: "120",
        }
        if callback_data in reminder_callback_mapping and not self.supports_custom_reminders:
            return TelegramTransportResponse(text="Настройка уведомлений пока недоступна в быстром режиме календаря. Уведомления можно настроить в Google Calendar.")
        if callback_data in reminder_callback_mapping:
            snapshot = self.state_repo.get(user.id)
            if snapshot is None or snapshot.draft is None:
                return TelegramTransportResponse(text="Черновик устарел. Отправьте событие заново.")
            reminder_value = reminder_callback_mapping[callback_data]
            result = self.edit_draft_field.execute(
                EditEventDraftFieldInput(user_id=user.id, field_name="reminder_minutes", field_value="" if reminder_value is None else reminder_value)
            )
            if result.status != "preview_ready":
                return TelegramTransportResponse(text="Не удалось обновить уведомления. Попробуйте снова.")
            return TelegramTransportResponse(text=self._get_pending_draft_text(user.id), buttons=self._build_draft_buttons_from_state(user.id))
        if callback_data == CALLBACK_SETTINGS_PARSER_PYTHON:
            result, _ = self.set_parser_mode.execute(user_id=user.id, parser_mode=ParserMode.PYTHON)
            settings_response = self._build_settings_response(user.id)
            return TelegramTransportResponse(text=f"{result.message}\n\n{settings_response.text}", buttons=settings_response.buttons)
        if callback_data == CALLBACK_SETTINGS_PARSER_AUTO:
            result, _ = self.set_parser_mode.execute(user_id=user.id, parser_mode=ParserMode.AUTO)
            settings_response = self._build_settings_response(user.id)
            return TelegramTransportResponse(text=f"{result.message}\n\n{settings_response.text}", buttons=settings_response.buttons)
        if callback_data == CALLBACK_CASHBACK_LIST_CURRENT and self.list_active_cashback_categories is not None:
            result = self.list_active_cashback_categories.execute()
            return TelegramTransportResponse(text=result.text, buttons=self._build_cashback_month_nav_buttons(result.target_month))
        if callback_data.startswith(CALLBACK_CASHBACK_LIST_MONTH_PREFIX) and self.list_active_cashback_categories is not None:
            selected_month = callback_data.removeprefix(CALLBACK_CASHBACK_LIST_MONTH_PREFIX)
            if parse_year_month(selected_month) is None:
                return TelegramTransportResponse(
                    text=(
                        "Не удалось открыть месяц из кнопки.\n"
                        "Попробуйте снова через «📋 Активные категории»."
                    )
                )
            result = self.list_active_cashback_categories.execute(month=selected_month)
            return TelegramTransportResponse(text=result.text, buttons=self._build_cashback_month_nav_buttons(result.target_month))

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
        return _build_draft_buttons(snapshot.draft, supports_custom_reminders=self.supports_custom_reminders)

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

    def _build_cashback_month_nav_buttons(self, target_month: str | None) -> tuple[tuple[str, str], ...]:
        if target_month is None:
            return ()
        if parse_year_month(target_month) is None:
            return ()
        prev_month = shift_year_month(target_month, delta=-1)
        next_month = shift_year_month(target_month, delta=1)
        if prev_month is None or next_month is None:
            return ()
        return (
            ("⬅️ Предыдущий", f"{CALLBACK_CASHBACK_LIST_MONTH_PREFIX}{prev_month}"),
            ("Текущий", CALLBACK_CASHBACK_LIST_CURRENT),
            ("Следующий ➡️", f"{CALLBACK_CASHBACK_LIST_MONTH_PREFIX}{next_month}"),
        )


def format_preview_message(draft: EventDraft) -> str:
    validation_issue = detect_draft_validation_issue(draft, require_start_at=True)
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
    if draft.reminder_minutes:
        rendered = ", ".join(f"popup {minutes} min" for minutes in draft.reminder_minutes)
        lines.append(f"- reminders: {rendered}")
    else:
        lines.append("- reminders: default popup 60 min, popup 30 min")
    lines.extend(_format_parser_diagnostics(draft.metadata))
    if validation_issue is not None:
        lines.append(validation_issue.preview_hint)
    lines.append("Событие НЕ будет создано, пока вы явно не нажмёте Confirm.")
    return "\n".join(lines)


def _build_draft_buttons(draft: EventDraft, *, supports_custom_reminders: bool = True) -> tuple[tuple[str, str], ...]:
    if detect_draft_validation_issue(draft, require_start_at=True) is not None:
        return (
            ("✏️ Edit", CALLBACK_EDIT),
            ("❌ Cancel", CALLBACK_CANCEL),
        )
    buttons = [("✅ Confirm", CALLBACK_CONFIRM), ("⏱ Длительность", CALLBACK_DURATION)]
    if supports_custom_reminders:
        buttons.append(("🔔 Уведомления", CALLBACK_REMINDERS))
    buttons.extend([("✏️ Edit", CALLBACK_EDIT), ("❌ Cancel", CALLBACK_CANCEL)])
    return tuple(buttons)


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
