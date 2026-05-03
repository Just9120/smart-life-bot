"""Minimal Telegram transport mapping for Phase 1 foundation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import re
import secrets
from zoneinfo import ZoneInfo

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
    RequestDeleteCashbackCategoryUseCase,
    RequestEditCashbackCategoryPercentUseCase,
    SoftDeleteCashbackCategoryUseCase,
    CompleteTransitionCashbackCategoryUseCase,
    UpdateCashbackCategoryPercentUseCase,
    format_month_label,
    current_year_month,
    parse_year_month,
    shift_year_month,
)
from smart_life_bot.application.cashback_export import ExportCashbackCategoriesUseCase
from smart_life_bot.cashback.models import ALLOWED_OWNERS
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
CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX = "cashback:delete:request:"
CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX = "cashback:delete:confirm:"
CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX = "cashback:delete:cancel:"
CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX = "cashback:list:owner:"
CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX = "cashback:list:owner-current:"
CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX = "cashback:transition:select:"
CALLBACK_CASHBACK_TRANSITION_CANCEL = "cashback:transition:cancel"
CALLBACK_CASHBACK_ADD_START = "cashback:add:start"
CALLBACK_CASHBACK_SEARCH_HINT = "cashback:search:hint"
CALLBACK_CASHBACK_EXPORT_CURRENT = "cashback:export:current"
CALLBACK_CASHBACK_EXPORT_PICKER_PREFIX = "cashback:export:picker:"
CALLBACK_CASHBACK_EXPORT_SELECT_PREFIX = "cashback:export:select:"
CALLBACK_CASHBACK_EXPORT_CANCEL = "cashback:export:cancel"
CALLBACK_CASHBACK_EDIT_PERCENT_REQUEST_PREFIX = "cashback:edit-percent:request:"
LABEL_CASHBACK_ADD = "➕ Добавить категорию"
LABEL_CASHBACK_SEARCH = "🔎 Найти категорию"
CALLBACK_CALENDAR_DATE_START = "calendar:date:start"
CALLBACK_CALENDAR_DATE_MONTH_PREFIX = "calendar:date:month:"
CALLBACK_CALENDAR_DATE_SELECT_PREFIX = "calendar:date:select:"
CALLBACK_CALENDAR_DATE_CANCEL = "calendar:date:cancel"
CALLBACK_CALENDAR_DATE_NOOP_PREFIX = "calendar:date:noop:"


@dataclass(frozen=True, slots=True)
class PendingCashbackTransition:
    session_token: str
    add_input: object
    candidate_months: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PendingCalendarDateRecovery:
    session_token: str
    draft_fingerprint: str
    selected_date: str


@dataclass(frozen=True, slots=True)
class PendingCashbackPercentEdit:
    record_id: int
    target_month: str


@dataclass(frozen=True, slots=True)
class TelegramTransportResponse:
    text: str
    buttons: tuple[tuple[str, str], ...] = ()
    button_rows: tuple[tuple[tuple[str, str], ...], ...] = ()
    reply_keyboard: tuple[tuple[str, ...], ...] = ()
    document_name: str | None = None
    document_bytes: bytes | None = None


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
    request_delete_cashback_category: RequestDeleteCashbackCategoryUseCase | None = None
    request_edit_cashback_category_percent: RequestEditCashbackCategoryPercentUseCase | None = None
    soft_delete_cashback_category: SoftDeleteCashbackCategoryUseCase | None = None
    complete_transition_cashback_category: CompleteTransitionCashbackCategoryUseCase | None = None
    update_cashback_category_percent: UpdateCashbackCategoryPercentUseCase | None = None
    export_cashback_categories: ExportCashbackCategoriesUseCase | None = None
    pending_cashback_transitions: dict[int, PendingCashbackTransition] = field(default_factory=dict)
    pending_calendar_recovery: dict[int, PendingCalendarDateRecovery] = field(default_factory=dict)
    active_feature_context: dict[int, str] = field(default_factory=dict)
    pending_cashback_percent_edit: dict[int, PendingCashbackPercentEdit] = field(default_factory=dict)
    pending_cashback_add: dict[int, bool] = field(default_factory=dict)

    @staticmethod
    def _owner_filter_index(owner_name: str | None) -> str:
        if owner_name is None:
            return "all"
        return str(ALLOWED_OWNERS.index(owner_name))

    @staticmethod
    def _decode_owner_filter(owner_token: str) -> str | None:
        if owner_token == "all":
            return None
        if not owner_token.isdigit():
            return None
        index = int(owner_token)
        if index < 0 or index >= len(ALLOWED_OWNERS):
            return None
        return ALLOWED_OWNERS[index]

    def handle_start(self) -> TelegramTransportResponse:
        return TelegramTransportResponse(
            text=(
                "Привет! Выбери, с чем работаем сейчас:\n\n"
                "📅 Календарь — создать событие через черновик и подтверждение.\n"
                "💳 Кэшбек — добавить, найти или изменить кэшбек-категории."
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
            self.pending_cashback_transitions.pop(user.id, None)
            self.pending_cashback_percent_edit.pop(user.id, None)
            self.pending_cashback_add.pop(user.id, None)
            self.active_feature_context[user.id] = "calendar"
            return TelegramTransportResponse(
                text=(
                    "Текущий режим: 📅 Календарь\n\n"
                    "Отправь текст события, а я покажу черновик. "
                    "Событие не создастся, пока ты не нажмёшь подтверждение."
                ),
                buttons=(("⚡ Быстрый режим", "calendar:mode:quick"), ("🔐 Личный Google Calendar", "calendar:mode:personal")),
                reply_keyboard=(("📅 Календарь", "💳 Кэшбек"),),
            )

        if normalized == "💳 Кэшбек":
            self.pending_calendar_recovery.pop(user.id, None)
            self.active_feature_context[user.id] = "cashback"
            return TelegramTransportResponse(
                text=(
                    "Текущий режим: 💳 Кэшбек\n\n"
                    "📋 Активные категории — посмотреть и изменить текущие категории.\n"
                    "Одна категория: Альфа, Владимир, май, Аптеки, 5%.\n"
                    "Несколько категорий: Владимир, Т-Банк, май, Супермаркеты 5%, Аптеки 5%.\n"
                    "Быстро без запятых: Владимир Т-Банк Супермаркеты 5% Аптеки 5%.\n"
                    "Напиши категорию, например: Аптеки."
                ),
                buttons=(
                    ("📋 Активные категории", CALLBACK_CASHBACK_LIST_CURRENT),
                    (LABEL_CASHBACK_ADD, CALLBACK_CASHBACK_ADD_START),
                    (LABEL_CASHBACK_SEARCH, CALLBACK_CASHBACK_SEARCH_HINT),
                    ("📤 Экспорт XLSX", CALLBACK_CASHBACK_EXPORT_CURRENT),
                ),
            )
        if normalized == LABEL_CASHBACK_ADD:
            self.pending_cashback_add[user.id] = True
            self.active_feature_context[user.id] = "cashback"
            return TelegramTransportResponse(text="Одна категория: Альфа, Владимир, май, Аптеки, 5%\nНесколько категорий: Владимир, Т-Банк, май, Супермаркеты 5%, Аптеки 5%\nБыстро без запятых: Владимир Т-Банк Супермаркеты 5% Аптеки 5%")
        if normalized == LABEL_CASHBACK_SEARCH:
            self.active_feature_context[user.id] = "cashback"
            return TelegramTransportResponse(text="Напиши категорию, например: Аптеки.")

        if normalized == "📋 Активные категории" and self.list_active_cashback_categories is not None:
            self.active_feature_context[user.id] = "cashback"
            result = self.list_active_cashback_categories.execute()
            return TelegramTransportResponse(text=result.text, button_rows=self._build_cashback_action_button_rows(result))

        pending_edit = self.pending_cashback_percent_edit.get(user.id)
        if pending_edit is not None and self.update_cashback_category_percent is not None:
            if normalized.lower() == "cancel":
                self.pending_cashback_percent_edit.pop(user.id, None)
                return TelegramTransportResponse(text="Изменение процента отменено. Запись не изменена.")
            result = self.update_cashback_category_percent.execute(str(pending_edit.record_id), normalized)
            if result.status == "edit_percent_invalid":
                return TelegramTransportResponse(text=result.text)
            self.pending_cashback_percent_edit.pop(user.id, None)
            if result.target_month and self.list_active_cashback_categories is not None:
                listing = self.list_active_cashback_categories.execute(month=result.target_month)
                return TelegramTransportResponse(text=f"{result.text}\n\n{listing.text}", button_rows=self._build_cashback_action_button_rows(listing))
            return TelegramTransportResponse(text=result.text)

        if normalized.lower() == "cancel" and user.id in self.pending_cashback_add:
            self.pending_cashback_add.pop(user.id, None)
            return TelegramTransportResponse(text="Добавление кэшбека отменено. Запись не изменена.")

        if user.id in self.pending_cashback_add and self.add_cashback_category is not None:
            add_result = self.add_cashback_category.execute(normalized)
            if add_result is None:
                return TelegramTransportResponse(
                    text="Не понял формат кэшбека.\nФормат: Альфа, Владимир, май, Супермаркеты, 5%"
                )
            if add_result.status == "transition_month_required" and add_result.pending_add is not None:
                self.active_feature_context[user.id] = "cashback"
                transition_token = secrets.token_hex(3)
                self.pending_cashback_transitions[user.id] = PendingCashbackTransition(
                    session_token=transition_token,
                    add_input=add_result.pending_add,
                    candidate_months=add_result.candidate_months,
                )
                buttons = tuple(
                    (format_month_label(month), f"{CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX}{transition_token}:{month}")
                    for month in add_result.candidate_months
                ) + (("↩️ Отмена", CALLBACK_CASHBACK_TRANSITION_CANCEL),)
                return TelegramTransportResponse(text=add_result.text, buttons=buttons)
            if add_result.status == "invalid_format":
                return TelegramTransportResponse(text=f"{add_result.text}\n\nПример: Альфа, Владимир, май, Супермаркеты, 5%")
            self.pending_cashback_add.pop(user.id, None)
            self.active_feature_context[user.id] = "cashback"
            return TelegramTransportResponse(text=add_result.text)

        if self.add_cashback_category is not None:
            add_result = self.add_cashback_category.execute(normalized)
            if add_result is not None:
                if add_result.status == "transition_month_required" and add_result.pending_add is not None:
                    self.active_feature_context[user.id] = "cashback"
                    transition_token = secrets.token_hex(3)
                    self.pending_cashback_transitions[user.id] = PendingCashbackTransition(
                        session_token=transition_token,
                        add_input=add_result.pending_add,
                        candidate_months=add_result.candidate_months,
                    )
                    buttons = tuple(
                        (format_month_label(month), f"{CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX}{transition_token}:{month}")
                        for month in add_result.candidate_months
                    ) + (("↩️ Отмена", CALLBACK_CASHBACK_TRANSITION_CANCEL),)
                    return TelegramTransportResponse(text=add_result.text, buttons=buttons)
                self.active_feature_context[user.id] = "cashback"
                return TelegramTransportResponse(text=add_result.text)


        if normalized.startswith("/edit"):
            self.pending_calendar_recovery.pop(user.id, None)
            return self._handle_edit_command(user_id=user.id, command=text)
        if text.strip() == "/settings":
            return self._build_settings_response(user.id)
        snapshot = self.state_repo.get(user.id)
        pending_calendar = self.pending_calendar_recovery.get(user.id)
        if pending_calendar is not None:
            if normalized.lower() == "cancel":
                self.pending_calendar_recovery.pop(user.id, None)
                return TelegramTransportResponse(text="Ок, выбор даты и времени отменён.")
            minutes = _parse_hh_mm_to_minutes(normalized)
            if minutes is None:
                return TelegramTransportResponse(text="Не получилось распознать время.\nНапиши в формате HH:MM, например: 09:30.")
            snapshot = self.state_repo.get(user.id)
            if snapshot is None or snapshot.draft is None:
                self.pending_calendar_recovery.pop(user.id, None)
                return TelegramTransportResponse(text="Черновик уже изменился. Нажми «📅 Выбрать дату» ещё раз.")
            if not _recovery_draft_matches(snapshot.draft, pending_calendar.draft_fingerprint):
                self.pending_calendar_recovery.pop(user.id, None)
                return TelegramTransportResponse(text="Черновик изменился. Нажми «📅 Выбрать дату» ещё раз.")
            if snapshot.draft.start_at is not None:
                self.pending_calendar_recovery.pop(user.id, None)
                return TelegramTransportResponse(text="Дата и время уже выбраны. Если хочешь изменить, нажми «📅 Выбрать дату» ещё раз.")
            draft = snapshot.draft
            draft_tz = _resolve_draft_timezone(draft.timezone)
            if draft_tz is None:
                self.pending_calendar_recovery.pop(user.id, None)
                return TelegramTransportResponse(text="Не удалось применить timezone черновика. Используйте /edit timezone Europe/Amsterdam.")
            start_at = _combine_date_and_minutes(pending_calendar.selected_date, minutes, draft_tz)
            if start_at is None:
                return TelegramTransportResponse(text="Не удалось прочитать дату с кнопки. Нажми «📅 Выбрать дату» ещё раз.")
            result = self.edit_draft_field.execute(
                EditEventDraftFieldInput(user_id=user.id, field_name="start_at", field_value=start_at.isoformat())
            )
            if result.status != "preview_ready":
                return TelegramTransportResponse(text=result.message)
            self.pending_calendar_recovery.pop(user.id, None)
            return TelegramTransportResponse(text=self._get_pending_draft_text(user.id), buttons=self._build_draft_buttons_from_state(user.id))

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

        active_mode = self.active_feature_context.get(user.id)
        if active_mode == "cashback":
            if self.query_cashback_category is not None:
                cashback = self.query_cashback_category.execute(normalized)
                if cashback.status in {"query_found", "query_not_found"}:
                    self.active_feature_context[user.id] = "cashback"
                    return TelegramTransportResponse(text=cashback.text)
            return TelegramTransportResponse(
                text=(
                    "В режиме 💳 Кэшбек я ищу категории или добавляю их через «➕ Добавить категорию».\n"
                    "Для календаря выбери 📅 Календарь."
                )
            )

        if active_mode is None and self._requires_mode_selection_when_unset(normalized):
            return TelegramTransportResponse(
                text="Выбери режим: 📅 Календарь или 💳 Кэшбек.",
                reply_keyboard=(("📅 Календарь", "💳 Кэшбек"),),
            )

        result = self.process_incoming_message.execute(IncomingMessageInput(user_id=user.id, text=normalized))
        self.active_feature_context[user.id] = "calendar"
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

    def _looks_like_cashback_query(self, text: str) -> bool:
        normalized = text.strip()
        if not normalized or "," in normalized or normalized == "/start":
            return False
        tokens = normalized.split()
        if len(tokens) not in (1, 2):
            return False
        if any(ch.isdigit() for ch in normalized):
            return False
        lower_tokens = [token.lower() for token in tokens]
        if any(token in {"купить", "без", "даты", "напомни", "завтра", "сегодня"} for token in lower_tokens):
            return False
        return all(re.fullmatch(r"[А-Яа-яЁё\-]{2,}", token) is not None for token in tokens)

    def _is_cashback_query_in_context(self, user_id: int, text: str) -> bool:
        if self.active_feature_context.get(user_id) != "cashback":
            return False
        return self._looks_like_cashback_query(text)

    def _requires_mode_selection_when_unset(self, text: str) -> bool:
        normalized = text.strip()
        if self._looks_like_cashback_query(normalized):
            return True
        if any(ch.isdigit() for ch in normalized) or "," in normalized:
            return False
        tokens = normalized.split()
        if len(tokens) == 0 or len(tokens) > 3:
            return False
        if any(re.fullmatch(r"[А-Яа-яЁё\-]{2,}", token) is None for token in tokens):
            return False
        lowered = " ".join(token.lower() for token in tokens)
        if any(marker in lowered for marker in ("завтра", "сегодня", "послезавтра", "напомни")):
            return False
        return True

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
            self.pending_calendar_recovery.pop(user.id, None)
            self.pending_cashback_percent_edit.pop(user.id, None)
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
        if callback_data == CALLBACK_CALENDAR_DATE_START:
            snapshot = self.state_repo.get(user.id)
            if snapshot is None or snapshot.draft is None:
                return TelegramTransportResponse(text="Нет черновика для выбора даты.")
            token = secrets.token_hex(3)
            self.pending_calendar_recovery[user.id] = PendingCalendarDateRecovery(
                session_token=token,
                draft_fingerprint=_draft_fingerprint(snapshot.draft),
                selected_date="",
            )
            return TelegramTransportResponse(
                text="Выбери дату для события.",
                button_rows=_build_month_grid_rows(_resolve_month_for_picker(snapshot.draft), token),
            )
        if callback_data.startswith(CALLBACK_CALENDAR_DATE_MONTH_PREFIX):
            payload = callback_data.removeprefix(CALLBACK_CALENDAR_DATE_MONTH_PREFIX)
            token, _, month_raw = payload.partition(":")
            pending = self.pending_calendar_recovery.get(user.id)
            if pending is None or not token or token != pending.session_token:
                return TelegramTransportResponse(text="Кнопка устарела. Нажми «📅 Выбрать дату» ещё раз.")
            parsed_month = _parse_year_month(month_raw)
            if parsed_month is None:
                return TelegramTransportResponse(text="Кнопка устарела. Нажми «📅 Выбрать дату» ещё раз.")
            snapshot = self.state_repo.get(user.id)
            if snapshot is None or snapshot.draft is None or not _recovery_draft_matches(snapshot.draft, pending.draft_fingerprint):
                self.pending_calendar_recovery.pop(user.id, None)
                return TelegramTransportResponse(text="Черновик изменился. Нажми «📅 Выбрать дату» ещё раз.")
            return TelegramTransportResponse(text="Выбери дату для события.", button_rows=_build_month_grid_rows(parsed_month, pending.session_token))
        if callback_data.startswith(CALLBACK_CALENDAR_DATE_SELECT_PREFIX):
            payload = callback_data.removeprefix(CALLBACK_CALENDAR_DATE_SELECT_PREFIX)
            token, _, selected_date = payload.partition(":")
            pending = self.pending_calendar_recovery.get(user.id)
            if pending is None or not token or token != pending.session_token:
                return TelegramTransportResponse(text="Кнопка устарела. Нажми «📅 Выбрать дату» ещё раз.")
            if _parse_iso_date(selected_date) is None:
                return TelegramTransportResponse(text="Кнопка устарела. Нажми «📅 Выбрать дату» ещё раз.")
            snapshot = self.state_repo.get(user.id)
            if snapshot is None or snapshot.draft is None:
                return TelegramTransportResponse(text="Кнопка устарела. Нажми «📅 Выбрать дату» ещё раз.")
            if not _recovery_draft_matches(snapshot.draft, pending.draft_fingerprint) or snapshot.draft.start_at is not None:
                self.pending_calendar_recovery.pop(user.id, None)
                return TelegramTransportResponse(text="Черновик изменился. Нажми «📅 Выбрать дату» ещё раз.")
            self.pending_calendar_recovery[user.id] = PendingCalendarDateRecovery(
                session_token=pending.session_token,
                draft_fingerprint=pending.draft_fingerprint,
                selected_date=selected_date,
            )
            return TelegramTransportResponse(
                text=(
                    f"Дата выбрана: {selected_date}.\n"
                    "Теперь напиши время в формате HH:MM, например: 09:30.\n"
                    "Это только обновит черновик — событие создастся после кнопки «Создать событие»."
                )
            )
        if callback_data.startswith(CALLBACK_CALENDAR_DATE_NOOP_PREFIX):
            payload = callback_data.removeprefix(CALLBACK_CALENDAR_DATE_NOOP_PREFIX)
            token, _, month_raw = payload.partition(":")
            pending = self.pending_calendar_recovery.get(user.id)
            if pending is None or not token or token != pending.session_token:
                return TelegramTransportResponse(text="Кнопка устарела. Нажми «📅 Выбрать дату» ещё раз.")
            parsed_month = _parse_year_month(month_raw)
            if parsed_month is None:
                return TelegramTransportResponse(text="Кнопка устарела. Нажми «📅 Выбрать дату» ещё раз.")
            snapshot = self.state_repo.get(user.id)
            if snapshot is None or snapshot.draft is None or not _recovery_draft_matches(snapshot.draft, pending.draft_fingerprint):
                self.pending_calendar_recovery.pop(user.id, None)
                return TelegramTransportResponse(text="Черновик изменился. Нажми «📅 Выбрать дату» ещё раз.")
            return TelegramTransportResponse(text="Выбери дату для события.", button_rows=_build_month_grid_rows(parsed_month, pending.session_token))
        if callback_data == CALLBACK_CALENDAR_DATE_CANCEL:
            self.pending_calendar_recovery.pop(user.id, None)
            return TelegramTransportResponse(text="Ок, выбор даты и времени отменён.")
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
            return TelegramTransportResponse(text=result.text, button_rows=self._build_cashback_action_button_rows(result))
        if callback_data == CALLBACK_CASHBACK_ADD_START:
            self.pending_cashback_add[user.id] = True
            self.active_feature_context[user.id] = "cashback"
            return TelegramTransportResponse(text="Одна категория: Альфа, Владимир, май, Аптеки, 5%\nНесколько категорий: Владимир, Т-Банк, май, Супермаркеты 5%, Аптеки 5%\nБыстро без запятых: Владимир Т-Банк Супермаркеты 5% Аптеки 5%")
        if callback_data == CALLBACK_CASHBACK_SEARCH_HINT:
            self.active_feature_context[user.id] = "cashback"
            return TelegramTransportResponse(text="Напиши категорию, например: Аптеки.")
        if callback_data == CALLBACK_CASHBACK_EXPORT_CURRENT and self.export_cashback_categories is not None:
            selected_month = current_year_month(date.today())
            return TelegramTransportResponse(
                text=f"Выбери месяц для экспорта XLSX. Текущий выбор: {format_month_label(selected_month)}.",
                button_rows=self._build_cashback_export_picker_rows(selected_month),
            )
        if callback_data.startswith(CALLBACK_CASHBACK_EXPORT_PICKER_PREFIX) and self.export_cashback_categories is not None:
            selected_month = callback_data.removeprefix(CALLBACK_CASHBACK_EXPORT_PICKER_PREFIX)
            if parse_year_month(selected_month) is None:
                return TelegramTransportResponse(text="Не удалось определить месяц для экспорта. Открой «📤 Экспорт XLSX» заново.")
            return TelegramTransportResponse(
                text=f"Выбери месяц для экспорта XLSX. Текущий выбор: {format_month_label(selected_month)}.",
                button_rows=self._build_cashback_export_picker_rows(selected_month),
            )
        if callback_data.startswith(CALLBACK_CASHBACK_EXPORT_SELECT_PREFIX) and self.export_cashback_categories is not None:
            selected_month = callback_data.removeprefix(CALLBACK_CASHBACK_EXPORT_SELECT_PREFIX)
            if parse_year_month(selected_month) is None:
                return TelegramTransportResponse(text="Не удалось определить месяц для экспорта. Открой «📤 Экспорт XLSX» заново.")
            result = self.export_cashback_categories.execute(selected_month)
            if result.status != "ok" or result.content is None or result.file_name is None:
                return TelegramTransportResponse(text=result.text)
            return TelegramTransportResponse(text=result.text, document_name=result.file_name, document_bytes=result.content)
        if callback_data == CALLBACK_CASHBACK_EXPORT_CANCEL:
            return TelegramTransportResponse(text="Экспорт отменён. Открой «📤 Экспорт XLSX», когда будешь готов.")
        if callback_data.startswith(CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX) and self.list_active_cashback_categories is not None:
            owner_token = callback_data.removeprefix(CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX)
            owner_name = self._decode_owner_filter(owner_token)
            if owner_name is None and owner_token != "all":
                return TelegramTransportResponse(text="Не удалось применить фильтр владельца. Открой «📋 Активные категории» заново.")
            result = self.list_active_cashback_categories.execute(owner_name=owner_name)
            return TelegramTransportResponse(text=result.text, button_rows=self._build_cashback_action_button_rows(result))
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
            return TelegramTransportResponse(text=result.text, button_rows=self._build_cashback_action_button_rows(result))
        if callback_data.startswith(CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX) and self.list_active_cashback_categories is not None:
            encoded = callback_data.removeprefix(CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX)
            if ":month:" not in encoded:
                return TelegramTransportResponse(text="Не удалось открыть месяц из кнопки.\nПопробуйте снова через «📋 Активные категории».")
            owner_token, selected_month = encoded.split(":month:", maxsplit=1)
            owner_name = self._decode_owner_filter(owner_token)
            if owner_name is None and owner_token != "all":
                return TelegramTransportResponse(text="Не удалось применить фильтр владельца. Открой «📋 Активные категории» заново.")
            if parse_year_month(selected_month) is None:
                return TelegramTransportResponse(
                    text=(
                        "Не удалось открыть месяц из кнопки.\n"
                        "Попробуйте снова через «📋 Активные категории»."
                    )
                )
            result = self.list_active_cashback_categories.execute(month=selected_month, owner_name=owner_name)
            return TelegramTransportResponse(text=result.text, button_rows=self._build_cashback_action_button_rows(result))
        if callback_data.startswith(CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX) and self.request_delete_cashback_category is not None:
            record_id = callback_data.removeprefix(CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX)
            result = self.request_delete_cashback_category.execute(record_id)
            if result.status != "delete_confirmation":
                return TelegramTransportResponse(text=result.text)
            return TelegramTransportResponse(
                text=result.text,
                buttons=(
                    ("✅ Подтвердить удаление", f"{CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX}{record_id}"),
                    ("↩️ Отмена", f"{CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX}{record_id}"),
                ),
            )
        if callback_data.startswith(CALLBACK_CASHBACK_EDIT_PERCENT_REQUEST_PREFIX) and self.request_edit_cashback_category_percent is not None:
            record_id = callback_data.removeprefix(CALLBACK_CASHBACK_EDIT_PERCENT_REQUEST_PREFIX)
            result = self.request_edit_cashback_category_percent.execute(record_id)
            if not result.records:
                return TelegramTransportResponse(text=result.text)
            record = result.records[0]
            self.pending_cashback_percent_edit[user.id] = PendingCashbackPercentEdit(record_id=record.id, target_month=record.target_month)
            return TelegramTransportResponse(text=f"Введи новый процент для этой категории.\n{record.category_raw} ({record.owner_name} — {record.bank_name})\nНапример: 7%, 7,5% или 7.5%.\n\nДля отмены отправь: cancel")
        if callback_data.startswith(CALLBACK_CASHBACK_DELETE_CANCEL_PREFIX):
            return TelegramTransportResponse(text="Ок, ничего не удалил.")
        if callback_data.startswith(CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX) and self.soft_delete_cashback_category is not None:
            record_id = callback_data.removeprefix(CALLBACK_CASHBACK_DELETE_CONFIRM_PREFIX)
            result = self.soft_delete_cashback_category.execute(record_id)
            if result.target_month and self.list_active_cashback_categories is not None:
                listing = self.list_active_cashback_categories.execute(month=result.target_month)
                return TelegramTransportResponse(text=f"Готово, убрал категорию из активных.\n\n{listing.text}", button_rows=self._build_cashback_action_button_rows(listing))
            return TelegramTransportResponse(text=result.text)
        if callback_data == CALLBACK_CASHBACK_TRANSITION_CANCEL:
            self.pending_cashback_transitions.pop(user.id, None)
            return TelegramTransportResponse(text="Добавление кэшбека отменено. Запись не изменена.")
        if callback_data.startswith(CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX) and self.complete_transition_cashback_category is not None:
            payload = callback_data.removeprefix(CALLBACK_CASHBACK_TRANSITION_SELECT_PREFIX)
            token, _, selected_month = payload.partition(":")
            pending = self.pending_cashback_transitions.get(user.id)
            if pending is None:
                return TelegramTransportResponse(text="Кнопка устарела. Отправь кэшбек заново.")
            if not token or token != pending.session_token:
                return TelegramTransportResponse(text="Кнопка устарела. Отправь кэшбек заново.")
            if selected_month not in pending.candidate_months:
                return TelegramTransportResponse(text="Некорректный месяц в кнопке. Отправь кэшбек заново.")
            self.pending_cashback_transitions.pop(user.id, None)
            result = self.complete_transition_cashback_category.execute(pending.add_input, selected_month)
            return TelegramTransportResponse(text=result.text)

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

    def _build_cashback_export_picker_rows(self, selected_month: str) -> tuple[tuple[tuple[str, str], ...], ...]:
        prev_month = shift_year_month(selected_month, delta=-1)
        next_month = shift_year_month(selected_month, delta=1)
        return (
            (("⬅️", f"{CALLBACK_CASHBACK_EXPORT_PICKER_PREFIX}{prev_month}"), (format_month_label(selected_month), f"{CALLBACK_CASHBACK_EXPORT_PICKER_PREFIX}{selected_month}"), ("➡️", f"{CALLBACK_CASHBACK_EXPORT_PICKER_PREFIX}{next_month}")),
            (("✅ Выгрузить этот месяц", f"{CALLBACK_CASHBACK_EXPORT_SELECT_PREFIX}{selected_month}"),),
            (("↩️ Назад", CALLBACK_CASHBACK_EXPORT_CANCEL),),
        )

    def _build_cashback_action_button_rows(self, result) -> tuple[tuple[tuple[str, str], ...], ...]:
        rows: list[tuple[tuple[str, str], ...]] = []
        month_buttons = self._build_cashback_month_nav_buttons(result.target_month, owner_filter=result.owner_filter)
        if month_buttons:
            rows.append(month_buttons)
        owner_buttons = self._build_cashback_owner_filter_buttons(result.target_month, result.owner_filter)
        if owner_buttons:
            for index in range(0, len(owner_buttons), 2):
                rows.append(owner_buttons[index:index + 2])
        for index, row in enumerate(result.records, start=1):
            rows.append(
                (
                    (f"✏️ Изменить % №{index}", f"{CALLBACK_CASHBACK_EDIT_PERCENT_REQUEST_PREFIX}{row.id}"),
                    (f"🗑 Удалить №{index}", f"{CALLBACK_CASHBACK_DELETE_REQUEST_PREFIX}{row.id}"),
                )
            )
        return tuple(rows)

    def _build_cashback_owner_filter_buttons(self, target_month: str | None, owner_filter: str | None) -> tuple[tuple[str, str], ...]:
        if target_month is None or parse_year_month(target_month) is None:
            return ()
        buttons: list[tuple[str, str]] = []
        for index, owner in enumerate(ALLOWED_OWNERS):
            label = f"👤 {owner}"
            if owner == owner_filter:
                label = f"✅ {owner}"
            buttons.append((label, f"{CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX}{index}:month:{target_month}"))
        all_label = "✅ Все" if owner_filter is None else "Все"
        buttons.append((all_label, f"{CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX}all:month:{target_month}"))
        return tuple(buttons)

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

    def _build_cashback_month_nav_buttons(self, target_month: str | None, owner_filter: str | None = None) -> tuple[tuple[str, str], ...]:
        if target_month is None:
            return ()
        if parse_year_month(target_month) is None:
            return ()
        prev_month = shift_year_month(target_month, delta=-1)
        next_month = shift_year_month(target_month, delta=1)
        if prev_month is None or next_month is None:
            return ()
        owner_token = self._owner_filter_index(owner_filter)
        current_cb = CALLBACK_CASHBACK_LIST_CURRENT if owner_filter is None else f"{CALLBACK_CASHBACK_LIST_OWNER_CURRENT_PREFIX}{owner_token}"
        return (
            ("⬅️ Предыдущий", f"{CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX}{owner_token}:month:{prev_month}"),
            ("Текущий", current_cb),
            ("Следующий ➡️", f"{CALLBACK_CASHBACK_LIST_OWNER_MONTH_PREFIX}{owner_token}:month:{next_month}"),
        )


def format_preview_message(draft: EventDraft) -> str:
    validation_issue = detect_draft_validation_issue(draft, require_start_at=True)
    date_time_value = draft.start_at.isoformat() if draft.start_at else "не выбраны"
    duration_value = "—"
    if draft.start_at is not None and draft.end_at is not None:
        try:
            duration_minutes = int((draft.end_at - draft.start_at).total_seconds() // 60)
        except TypeError:
            duration_minutes = 0
        if duration_minutes > 0:
            duration_value = f"{duration_minutes} мин"
    lines = [
        "Проверь черновик события:",
        f"Название: {draft.title}",
        f"Дата и время: {date_time_value}",
        f"Длительность: {duration_value}",
        f"Часовой пояс: {draft.timezone or '—'}",
    ]
    if draft.description:
        lines.append(f"Описание: {draft.description}")
    if draft.location:
        lines.append(f"Место: {draft.location}")
    if draft.reminder_minutes:
        rendered = ", ".join(f"{minutes} мин" for minutes in draft.reminder_minutes)
        lines.append(f"Уведомления: {rendered}")
    else:
        lines.append("Уведомления: по умолчанию (за 60 и 30 минут)")
    lines.extend(_format_parser_diagnostics(draft.metadata))
    if validation_issue is not None and draft.start_at is None:
        lines.append("Чтобы создать событие, сначала выбери дату и время.")
    elif validation_issue is not None:
        lines.append(validation_issue.preview_hint)
    else:
        lines.append("Событие не создастся, пока ты не нажмёшь подтверждение.")
    return "\n".join(lines)


def _build_draft_buttons(draft: EventDraft, *, supports_custom_reminders: bool = True) -> tuple[tuple[str, str], ...]:
    validation_issue = detect_draft_validation_issue(draft, require_start_at=True)
    if validation_issue is not None:
        if draft.start_at is None:
            return (
                ("📅 Выбрать дату", CALLBACK_CALENDAR_DATE_START),
                ("✏️ Edit", CALLBACK_EDIT),
                ("❌ Cancel", CALLBACK_CANCEL),
            )
        return (
            ("✏️ Edit", CALLBACK_EDIT),
            ("❌ Cancel", CALLBACK_CANCEL),
        )
    buttons = [("✅ Создать событие", CALLBACK_CONFIRM), ("⏱ Длительность", CALLBACK_DURATION)]
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


def _parse_hh_mm_to_minutes(value: str) -> int | None:
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    hour = int(parts[0])
    minute = int(parts[1])
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def _resolve_draft_timezone(timezone_name: str | None) -> ZoneInfo | None:
    if timezone_name is None:
        return None
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return None


def _combine_date_and_minutes(selected_date: str, minutes: int, tz: ZoneInfo) -> datetime | None:
    parsed = _parse_iso_date(selected_date)
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, minutes // 60, minutes % 60, tzinfo=tz)


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_year_month(value: str) -> tuple[int, int] | None:
    chunks = value.split("-")
    if len(chunks) != 2 or not chunks[0].isdigit() or not chunks[1].isdigit():
        return None
    year, month = int(chunks[0]), int(chunks[1])
    if year < 1 or month < 1 or month > 12:
        return None
    return year, month


def _resolve_month_for_picker(draft: EventDraft) -> tuple[int, int]:
    if draft.start_at is not None:
        return draft.start_at.year, draft.start_at.month
    return (datetime.now().year, datetime.now().month)


def _build_month_grid_rows(year_month: tuple[int, int], token: str) -> tuple[tuple[tuple[str, str], ...], ...]:
    import calendar
    year, month = year_month
    cal = calendar.Calendar(firstweekday=0)
    month_label = f"{year:04d}-{month:02d}"
    prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
    next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)
    rows: list[tuple[tuple[str, str], ...]] = [(
        ("⬅️", f"{CALLBACK_CALENDAR_DATE_MONTH_PREFIX}{token}:{prev_y:04d}-{prev_m:02d}"),
        (month_label, f"{CALLBACK_CALENDAR_DATE_MONTH_PREFIX}{token}:{month_label}"),
        ("➡️", f"{CALLBACK_CALENDAR_DATE_MONTH_PREFIX}{token}:{next_y:04d}-{next_m:02d}"),
    )]
    for week in cal.monthdayscalendar(year, month):
        week_row: list[tuple[str, str]] = []
        for day in week:
            if day == 0:
                week_row.append(("·", f"{CALLBACK_CALENDAR_DATE_NOOP_PREFIX}{token}:{month_label}"))
                continue
            iso = f"{year:04d}-{month:02d}-{day:02d}"
            week_row.append((str(day), f"{CALLBACK_CALENDAR_DATE_SELECT_PREFIX}{token}:{iso}"))
        rows.append(tuple(week_row))
    rows.append((("↩️ Отмена", CALLBACK_CALENDAR_DATE_CANCEL),))
    return tuple(rows)


def _draft_fingerprint(draft: EventDraft) -> str:
    payload = f"{draft.title}|{draft.start_at.isoformat() if draft.start_at else '-'}|{draft.end_at.isoformat() if draft.end_at else '-'}|{draft.timezone or '-'}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def _recovery_draft_matches(draft: EventDraft, fingerprint: str) -> bool:
    return _draft_fingerprint(draft) == fingerprint
