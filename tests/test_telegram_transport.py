from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import pytest

from smart_life_bot.application.cashback_use_cases import AddCashbackCategoryUseCase, QueryCashbackCategoryUseCase
from smart_life_bot.application.use_cases import (
    CancelEventDraftUseCase,
    ConfirmEventDraftUseCase,
    EditEventDraftFieldUseCase,
    GetUserSettingsUseCase,
    ProcessIncomingMessageUseCase,
    SetParserModeUseCase,
)
from smart_life_bot.auth.models import AuthContext
from smart_life_bot.bot import (
    CALLBACK_CANCEL,
    CALLBACK_CONFIRM,
    CALLBACK_DURATION,
    CALLBACK_EDIT,
    CALLBACK_REMINDERS,
    CALLBACK_REMINDERS_10,
    CALLBACK_REMINDERS_30,
    CALLBACK_SETTINGS_PARSER_AUTO,
    CALLBACK_SETTINGS_PARSER_LLM,
    CALLBACK_SETTINGS_PARSER_PYTHON,
    TelegramTransportRouter,
    format_preview_message,
)
from smart_life_bot.calendar.models import CalendarEventCreateRequest, CalendarEventCreateResult
from smart_life_bot.domain.enums import EventLogStatus, GoogleAuthMode
from smart_life_bot.domain.models import EventDraft
from smart_life_bot.parsing.models import ParsingResult
from smart_life_bot.cashback.sqlite import SQLiteCashbackCategoriesRepository
from smart_life_bot.storage.sqlite import (
    SQLiteConversationStateRepository,
    SQLiteEventsLogRepository,
    SQLiteProviderCredentialsRepository,
    SQLiteUserPreferencesRepository,
    SQLiteUsersRepository,
    create_sqlite_connection,
    init_sqlite_schema,
)


class FakeParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
                end_at=datetime(2026, 3, 12, 11, 0, tzinfo=UTC),
                timezone="UTC",
                description="Draft description",
                location="Room A",
            ),
            confidence=0.95,
            is_ambiguous=False,
            issues=[],
        )


class MissingStartAtParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=None,
                timezone="UTC",
                metadata={"source": "rule-based-parser"},
            ),
            confidence=0.30,
            is_ambiguous=True,
            issues=["missing_start_at"],
        )


class InvalidTimezoneParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
                end_at=datetime(2026, 3, 12, 11, 0, tzinfo=UTC),
                timezone="Not/AZone",
                metadata={"source": "rule-based-parser"},
            ),
            confidence=0.95,
            is_ambiguous=False,
            issues=[],
        )


class MalformedTimezoneParser:
    def __init__(self, timezone: str) -> None:
        self.timezone = timezone

    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
                end_at=datetime(2026, 3, 12, 11, 0, tzinfo=UTC),
                timezone=self.timezone,
                metadata={"source": "rule-based-parser"},
            ),
            confidence=0.95,
            is_ambiguous=False,
            issues=[],
        )


class NoneTimezoneParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
                end_at=datetime(2026, 3, 12, 11, 0, tzinfo=UTC),
                timezone=None,
                metadata={"source": "rule-based-parser"},
            ),
            confidence=0.95,
            is_ambiguous=False,
            issues=[],
        )


class InvalidRangeParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
                end_at=datetime(2026, 3, 12, 9, 0, tzinfo=UTC),
                timezone="UTC",
                metadata={"source": "rule-based-parser"},
            ),
            confidence=0.95,
            is_ambiguous=False,
            issues=[],
        )


class MixedAwarenessParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
                end_at=datetime(2026, 3, 12, 11, 0),
                timezone="UTC",
                metadata={"source": "rule-based-parser"},
            ),
            confidence=0.95,
            is_ambiguous=False,
            issues=[],
        )


class FakeAuthProvider:
    def resolve_auth_context(self, user_id: int) -> AuthContext:
        return AuthContext(
            user_id=user_id,
            auth_mode=GoogleAuthMode.OAUTH_USER_MODE,
            credentials_handle="fake-auth",
        )


class SpyCalendarService:
    def __init__(self) -> None:
        self.requests: list[CalendarEventCreateRequest] = []

    def create_event(
        self,
        auth_context: AuthContext,
        request: CalendarEventCreateRequest,
    ) -> CalendarEventCreateResult:
        self.requests.append(request)
        return CalendarEventCreateResult(
            event_id="internal-1",
            provider_event_id="provider-evt-1",
            html_link="https://example.test/e/1",
        )


class SpyCalendarServiceNoHtmlLink:
    def __init__(self) -> None:
        self.requests: list[CalendarEventCreateRequest] = []

    def create_event(
        self,
        auth_context: AuthContext,
        request: CalendarEventCreateRequest,
    ) -> CalendarEventCreateResult:
        self.requests.append(request)
        return CalendarEventCreateResult(
            event_id="internal-2",
            provider_event_id="provider-evt-2",
            html_link=None,
        )


class SilentLogger:
    def info(self, message: str, **extra: object) -> None:
        return None

    def warning(self, message: str, **extra: object) -> None:
        return None

    def error(self, message: str, **extra: object) -> None:
        return None


@dataclass
class Deps:
    parser: FakeParser
    auth_provider: FakeAuthProvider
    calendar_service: SpyCalendarService
    users_repo: SQLiteUsersRepository
    user_preferences_repo: SQLiteUserPreferencesRepository
    credentials_repo: SQLiteProviderCredentialsRepository
    state_repo: SQLiteConversationStateRepository
    events_log_repo: SQLiteEventsLogRepository
    logger: SilentLogger


def _build_router() -> tuple[TelegramTransportRouter, Deps]:
    connection = create_sqlite_connection("sqlite:///:memory:")
    init_sqlite_schema(connection)

    cashback_repo = SQLiteCashbackCategoriesRepository(connection)

    deps = Deps(
        parser=FakeParser(),
        auth_provider=FakeAuthProvider(),
        calendar_service=SpyCalendarService(),
        users_repo=SQLiteUsersRepository(connection),
        user_preferences_repo=SQLiteUserPreferencesRepository(connection),
        credentials_repo=SQLiteProviderCredentialsRepository(connection),
        state_repo=SQLiteConversationStateRepository(connection),
        events_log_repo=SQLiteEventsLogRepository(connection),
        logger=SilentLogger(),
    )

    router = TelegramTransportRouter(
        users_repo=deps.users_repo,
        state_repo=deps.state_repo,
        process_incoming_message=ProcessIncomingMessageUseCase(deps),
        confirm_draft=ConfirmEventDraftUseCase(deps),
        cancel_draft=CancelEventDraftUseCase(deps),
        edit_draft_field=EditEventDraftFieldUseCase(deps),
        get_user_settings=GetUserSettingsUseCase(deps),
        set_parser_mode=SetParserModeUseCase(deps),
        default_timezone="UTC",
        supports_custom_reminders=True,
        add_cashback_category=AddCashbackCategoryUseCase(cashback_repo, now_provider=lambda: datetime(2026, 5, 3, tzinfo=UTC).date()),
        query_cashback_category=QueryCashbackCategoryUseCase(cashback_repo, now_provider=lambda: datetime(2026, 5, 3, tzinfo=UTC).date()),
    )
    return router, deps


def _build_router_without_reminders() -> tuple[TelegramTransportRouter, Deps]:
    router, deps = _build_router()
    router = TelegramTransportRouter(
        users_repo=deps.users_repo,
        state_repo=deps.state_repo,
        process_incoming_message=ProcessIncomingMessageUseCase(deps),
        confirm_draft=ConfirmEventDraftUseCase(deps),
        cancel_draft=CancelEventDraftUseCase(deps),
        edit_draft_field=EditEventDraftFieldUseCase(deps),
        get_user_settings=GetUserSettingsUseCase(deps),
        set_parser_mode=SetParserModeUseCase(deps),
        default_timezone="UTC",
        supports_custom_reminders=False,
    )
    return router, deps


def _build_router_no_html_link() -> tuple[TelegramTransportRouter, Deps]:
    connection = create_sqlite_connection("sqlite:///:memory:")
    init_sqlite_schema(connection)

    cashback_repo = SQLiteCashbackCategoriesRepository(connection)

    deps = Deps(
        parser=FakeParser(),
        auth_provider=FakeAuthProvider(),
        calendar_service=SpyCalendarServiceNoHtmlLink(),
        users_repo=SQLiteUsersRepository(connection),
        user_preferences_repo=SQLiteUserPreferencesRepository(connection),
        credentials_repo=SQLiteProviderCredentialsRepository(connection),
        state_repo=SQLiteConversationStateRepository(connection),
        events_log_repo=SQLiteEventsLogRepository(connection),
        logger=SilentLogger(),
    )

    router = TelegramTransportRouter(
        users_repo=deps.users_repo,
        state_repo=deps.state_repo,
        process_incoming_message=ProcessIncomingMessageUseCase(deps),
        confirm_draft=ConfirmEventDraftUseCase(deps),
        cancel_draft=CancelEventDraftUseCase(deps),
        edit_draft_field=EditEventDraftFieldUseCase(deps),
        get_user_settings=GetUserSettingsUseCase(deps),
        set_parser_mode=SetParserModeUseCase(deps),
        default_timezone="UTC",
    )
    return router, deps


def test_plain_text_handler_maps_to_process_incoming_use_case() -> None:
    router, deps = _build_router()

    response = router.handle_text_message(telegram_user_id=90001, text="Team sync tomorrow at 10")

    assert "Черновик события" in response.text
    assert ("✅ Confirm", CALLBACK_CONFIRM) in response.buttons
    user = deps.users_repo.get_by_telegram_id(90001)
    assert user is not None
    logs = deps.events_log_repo.list_for_user(user.id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.PREVIEW_READY
    assert ("⏱ Длительность", CALLBACK_DURATION) in response.buttons
    assert ("🔔 Уведомления", CALLBACK_REMINDERS) in response.buttons


def test_start_includes_footer_calendar_menu() -> None:
    router, _ = _build_router()
    response = router.handle_start()
    assert ("📅 Календарь", "💳 Кэшбек") in response.reply_keyboard


def test_footer_calendar_text_returns_mode_choices() -> None:
    router, _ = _build_router()
    response = router.handle_text_message(telegram_user_id=90500, text="📅 Календарь")
    assert ("⚡ Быстрый режим", "calendar:mode:quick") in response.buttons
    assert ("🔐 Личный Google Calendar", "calendar:mode:personal") in response.buttons


def test_calendar_mode_callbacks_are_informational_only() -> None:
    router, deps = _build_router()
    quick = router.handle_callback(telegram_user_id=90501, callback_data="calendar:mode:quick")
    personal = router.handle_callback(telegram_user_id=90501, callback_data="calendar:mode:personal")
    assert "Быстрый режим" in quick.text
    assert "пока недоступен" in personal.text
    assert len(deps.calendar_service.requests) == 0


def test_reminder_callback_shows_presets() -> None:
    router, _ = _build_router()
    router.handle_text_message(telegram_user_id=90510, text="Team sync")
    response = router.handle_callback(telegram_user_id=90510, callback_data=CALLBACK_REMINDERS)
    assert response.text == "Выберите уведомления для события:"
    assert ("10 минут", CALLBACK_REMINDERS_10) in response.buttons


def test_reminder_preset_updates_draft_without_calendar_write() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90511, text="Team sync")
    response = router.handle_callback(telegram_user_id=90511, callback_data=CALLBACK_REMINDERS_10)
    assert "- reminders: popup 10 min" in response.text
    assert len(deps.calendar_service.requests) == 0


def test_service_account_mode_hides_reminders_and_keeps_duration() -> None:
    router, _ = _build_router_without_reminders()
    response = router.handle_text_message(telegram_user_id=90512, text="Team sync")
    assert ("✅ Confirm", CALLBACK_CONFIRM) in response.buttons
    assert ("⏱ Длительность", CALLBACK_DURATION) in response.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons
    assert ("🔔 Уведомления", CALLBACK_REMINDERS) not in response.buttons


def test_stale_reminder_callbacks_return_unavailable_when_capability_disabled() -> None:
    router, deps = _build_router_without_reminders()
    router.handle_text_message(telegram_user_id=90513, text="Team sync")
    response = router.handle_callback(telegram_user_id=90513, callback_data=CALLBACK_REMINDERS_30)
    assert "пока недоступна в быстром режиме календаря" in response.text
    assert len(deps.calendar_service.requests) == 0




def test_reminder_30_preset_updates_preview_and_confirm_uses_custom_reminder() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90512, text="Team sync")

    reminder_response = router.handle_callback(telegram_user_id=90512, callback_data=CALLBACK_REMINDERS_30)
    assert "- reminders: popup 30 min" in reminder_response.text
    assert len(deps.calendar_service.requests) == 0

    confirm_response = router.handle_callback(telegram_user_id=90512, callback_data=CALLBACK_CONFIRM)
    assert "Event created successfully" in confirm_response.text
    assert len(deps.calendar_service.requests) == 1
    assert tuple(deps.calendar_service.requests[0].reminder_minutes or []) == (30,)


def test_duration_callback_enters_duration_input_mode() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90501, text="Team sync")
    response = router.handle_callback(telegram_user_id=90501, callback_data=CALLBACK_DURATION)
    assert response.text == "Введите длительность в минутах, например: 20"
    user = deps.users_repo.get_by_telegram_id(90501)
    snapshot = deps.state_repo.get(user.id) if user else None
    assert snapshot is not None
    assert snapshot.editing_field == "duration_minutes"


def test_duration_input_updates_end_at_and_clears_editing_field() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90502, text="Team sync")
    router.handle_callback(telegram_user_id=90502, callback_data=CALLBACK_DURATION)
    response = router.handle_text_message(telegram_user_id=90502, text="20")
    assert "end_at: 2026-03-12T10:20:00+00:00" in response.text
    user = deps.users_repo.get_by_telegram_id(90502)
    snapshot = deps.state_repo.get(user.id) if user else None
    assert snapshot is not None
    assert snapshot.editing_field is None


@pytest.mark.parametrize("value", ["0", "-5", "1.5", "abc"])
def test_duration_input_rejects_invalid_values_and_keeps_state(value: str) -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90503, text="Team sync")
    router.handle_callback(telegram_user_id=90503, callback_data=CALLBACK_DURATION)
    response = router.handle_text_message(telegram_user_id=90503, text=value)
    assert "Введите положительное целое число минут" in response.text
    user = deps.users_repo.get_by_telegram_id(90503)
    snapshot = deps.state_repo.get(user.id) if user else None
    assert snapshot is not None
    assert snapshot.editing_field == "duration_minutes"


def test_plain_number_outside_duration_mode_uses_normal_parse_flow() -> None:
    router, _ = _build_router()
    response = router.handle_text_message(telegram_user_id=90504, text="20")
    assert "Черновик события:" in response.text


def test_stale_confirm_is_blocked_while_duration_input_active() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90505, text="Team sync")
    router.handle_callback(telegram_user_id=90505, callback_data=CALLBACK_DURATION)
    response = router.handle_callback(telegram_user_id=90505, callback_data=CALLBACK_CONFIRM)
    assert response.text == "Введите длительность в минутах, например: 20"
    assert len(deps.calendar_service.requests) == 0
    user = deps.users_repo.get_by_telegram_id(90505)
    snapshot = deps.state_repo.get(user.id) if user else None
    assert snapshot is not None
    assert snapshot.editing_field == "duration_minutes"


def test_stale_reminder_callback_fails_safely() -> None:
    router, _ = _build_router()
    response = router.handle_callback(telegram_user_id=90513, callback_data=CALLBACK_REMINDERS_10)
    assert response.text == "Черновик устарел. Отправьте событие заново."


def test_confirm_callback_maps_to_confirm_use_case() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90002, text="Confirm me")

    response = router.handle_callback(telegram_user_id=90002, callback_data=CALLBACK_CONFIRM)

    assert "Event created successfully" in response.text
    assert "Google Calendar: https://example.test/e/1" in response.text
    user = deps.users_repo.get_by_telegram_id(90002)
    assert user is not None
    logs = deps.events_log_repo.list_for_user(user.id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.SAVED
    assert len(deps.calendar_service.requests) == 1


def test_confirm_callback_without_html_link_keeps_backward_compatible_text() -> None:
    router, deps = _build_router_no_html_link()
    router.handle_text_message(telegram_user_id=90009, text="Confirm me no link")

    response = router.handle_callback(telegram_user_id=90009, callback_data=CALLBACK_CONFIRM)

    assert response.text == "Event created successfully"
    user = deps.users_repo.get_by_telegram_id(90009)
    assert user is not None
    logs = deps.events_log_repo.list_for_user(user.id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.SAVED
    assert len(deps.calendar_service.requests) == 1


def test_cancel_callback_maps_to_cancel_use_case() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90003, text="Cancel me")

    response = router.handle_callback(telegram_user_id=90003, callback_data=CALLBACK_CANCEL)

    assert response.text == "Draft cancelled and state reset to IDLE"
    user = deps.users_repo.get_by_telegram_id(90003)
    assert user is not None
    logs = deps.events_log_repo.list_for_user(user.id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.CANCELLED


def test_edit_command_maps_to_edit_use_case() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90004, text="Original title")

    response = router.handle_text_message(telegram_user_id=90004, text="/edit title Updated title")

    assert "Updated title" in response.text
    user = deps.users_repo.get_by_telegram_id(90004)
    assert user is not None
    state = deps.state_repo.get(user.id)
    assert state is not None
    assert state.draft is not None
    assert state.draft.title == "Updated title"


def test_preview_buttons_hide_confirm_when_start_at_missing() -> None:
    router, deps = _build_router()
    deps.parser = MissingStartAtParser()

    response = router.handle_text_message(telegram_user_id=90010, text="Missing start_at")

    assert ("✅ Confirm", CALLBACK_CONFIRM) not in response.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons
    assert "Нужно указать start_at перед созданием события." in response.text


def test_preview_buttons_hide_confirm_when_timezone_invalid() -> None:
    parser_cases = (
        (InvalidTimezoneParser(), "Invalid timezone"),
        (MalformedTimezoneParser("/UTC"), "Malformed timezone /UTC"),
        (MalformedTimezoneParser("../UTC"), "Malformed timezone ../UTC"),
    )
    for parser, text in parser_cases:
        router, deps = _build_router()
        deps.parser = parser

        response = router.handle_text_message(telegram_user_id=90013, text=text)

        assert ("✅ Confirm", CALLBACK_CONFIRM) not in response.buttons
        assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
        assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons
        assert "Используйте /edit timezone Europe/Amsterdam." in response.text


def test_preview_buttons_hide_confirm_when_timezone_is_none() -> None:
    router, deps = _build_router()
    deps.parser = NoneTimezoneParser()

    response = router.handle_text_message(telegram_user_id=90014, text="None timezone")

    assert ("✅ Confirm", CALLBACK_CONFIRM) not in response.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons
    assert "Используйте /edit timezone Europe/Amsterdam." in response.text


def test_preview_buttons_hide_confirm_when_time_range_invalid() -> None:
    router, deps = _build_router()
    deps.parser = InvalidRangeParser()

    response = router.handle_text_message(telegram_user_id=90015, text="Invalid range")

    assert ("✅ Confirm", CALLBACK_CONFIRM) not in response.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons
    assert "end_at должен быть позже start_at." in response.text


def test_preview_buttons_hide_confirm_when_datetime_awareness_mixed() -> None:
    router, deps = _build_router()
    deps.parser = MixedAwarenessParser()

    response = router.handle_text_message(telegram_user_id=90016, text="Mixed awareness")

    assert ("✅ Confirm", CALLBACK_CONFIRM) not in response.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons
    assert "в одном формате timezone-awareness" in response.text


def test_edit_start_at_restores_confirm_button() -> None:
    router, deps = _build_router()
    deps.parser = MissingStartAtParser()
    router.handle_text_message(telegram_user_id=90011, text="Missing start_at")

    response = router.handle_text_message(telegram_user_id=90011, text="/edit start_at 2026-02-14T11:30:00+00:00")

    assert ("✅ Confirm", CALLBACK_CONFIRM) in response.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons


def test_edit_invalid_start_at_keeps_confirm_hidden() -> None:
    router, deps = _build_router()
    deps.parser = MissingStartAtParser()
    router.handle_text_message(telegram_user_id=90012, text="Missing start_at")

    response = router.handle_text_message(telegram_user_id=90012, text="/edit start_at not-a-datetime")

    assert response.text == "Invalid datetime format for 'start_at'"
    user = deps.users_repo.get_by_telegram_id(90012)
    assert user is not None
    state = deps.state_repo.get(user.id)
    assert state is not None
    assert state.draft is not None
    assert state.draft.start_at is None


def test_edit_description_clear_flag_clears_optional_field() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90007, text="Draft for description clear")
    router.handle_text_message(telegram_user_id=90007, text="/edit description New description")

    response = router.handle_text_message(telegram_user_id=90007, text="/edit description --clear")

    assert "description:" not in response.text
    user = deps.users_repo.get_by_telegram_id(90007)
    assert user is not None
    state = deps.state_repo.get(user.id)
    assert state is not None
    assert state.draft is not None
    assert state.draft.description is None


def test_edit_location_clear_flag_clears_optional_field() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90008, text="Draft for location clear")
    router.handle_text_message(telegram_user_id=90008, text="/edit location HQ")

    response = router.handle_text_message(telegram_user_id=90008, text="/edit location --clear")

    assert "location:" not in response.text
    user = deps.users_repo.get_by_telegram_id(90008)
    assert user is not None
    state = deps.state_repo.get(user.id)
    assert state is not None
    assert state.draft is not None
    assert state.draft.location is None


def test_preview_formatting_contains_required_fields_and_disclaimer() -> None:
    router, _ = _build_router()

    response = router.handle_text_message(telegram_user_id=90005, text="Preview formatting")

    assert "title:" in response.text
    assert "start_at:" in response.text
    assert "end_at:" in response.text
    assert "timezone:" in response.text
    assert "description:" in response.text
    assert "location:" in response.text
    assert "Парсинг:" in response.text
    assert "НЕ будет создано" in response.text


def test_format_preview_message_shows_python_parser_diagnostics() -> None:
    draft = EventDraft(
        title="Parsed title",
        start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        timezone="UTC",
        metadata={
            "parser_mode": "python",
            "parser_router": "python",
            "source": "rule-based-parser",
            "parser_confidence": "0.95",
        },
    )

    preview = format_preview_message(draft)

    assert "Парсинг:" in preview
    assert "- mode: python" in preview
    assert "- route: Python" in preview
    assert "- source: Python" in preview
    assert "- confidence: 0.95" in preview


def test_format_preview_message_shows_custom_reminder_when_present() -> None:
    draft = EventDraft(
        title="Parsed title",
        start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        timezone="UTC",
        reminder_minutes=(10,),
        metadata={},
    )
    preview = format_preview_message(draft)
    assert "- reminders: popup 10 min" in preview


def test_format_preview_message_shows_claude_diagnostics_and_issues() -> None:
    draft = EventDraft(
        title="Parsed title",
        start_at=None,
        timezone="UTC",
        metadata={
            "parser_mode": "auto",
            "parser_router": "llm_fallback",
            "source": "claude-parser",
            "parser_confidence": "0.00",
            "parser_issues": "missing_start_at,invalid_timezone",
        },
    )

    preview = format_preview_message(draft)

    assert "- mode: auto" in preview
    assert "- route: Claude fallback" in preview
    assert "- source: Claude" in preview
    assert "- confidence: 0.00" in preview
    assert "- issues: missing_start_at,invalid_timezone" in preview


def test_format_preview_message_is_safe_when_parser_metadata_missing() -> None:
    draft = EventDraft(title="Parsed title")

    preview = format_preview_message(draft)

    assert "- mode: —" in preview
    assert "- route: —" in preview
    assert "- source: —" in preview
    assert "- confidence: —" in preview


def test_format_preview_message_is_safe_for_invalid_timezone() -> None:
    draft = EventDraft(
        title="Parsed title",
        start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        timezone="Not/AZone",
    )

    preview = format_preview_message(draft)

    assert "Используйте /edit timezone Europe/Amsterdam." in preview


def test_format_preview_message_is_safe_for_malformed_timezone_key() -> None:
    for timezone_value in ("/UTC", "../UTC"):
        draft = EventDraft(
            title="Parsed title",
            start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
            timezone=timezone_value,
        )

        preview = format_preview_message(draft)

        assert "Используйте /edit timezone Europe/Amsterdam." in preview


def test_format_preview_message_is_safe_for_mixed_awareness_range() -> None:
    draft = EventDraft(
        title="Parsed title",
        start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 12, 11, 0),
        timezone="UTC",
    )

    preview = format_preview_message(draft)

    assert "в одном формате timezone-awareness" in preview


def test_transport_layer_does_not_require_real_google_or_telegram_network() -> None:
    router, deps = _build_router()

    response = router.handle_callback(telegram_user_id=90006, callback_data=CALLBACK_EDIT)

    assert "/edit <field> <value>" in response.text
    assert len(deps.calendar_service.requests) == 0


def test_settings_command_creates_user_and_shows_parser_modes() -> None:
    router, deps = _build_router()

    response = router.handle_text_message(telegram_user_id=90100, text="/settings")

    assert "Settings" in response.text
    assert "Current: Python / rule-based" in response.text
    assert "🤖 LLM — not available" in response.text
    assert ("🐍 Python", CALLBACK_SETTINGS_PARSER_PYTHON) in response.buttons
    assert ("⚡ Auto", CALLBACK_SETTINGS_PARSER_AUTO) in response.buttons
    assert ("🤖 LLM", CALLBACK_SETTINGS_PARSER_LLM) in response.buttons
    user = deps.users_repo.get_by_telegram_id(90100)
    assert user is not None
    preferences = deps.user_preferences_repo.get_for_user(user.id)
    assert preferences is not None
    assert preferences.parser_mode.value == "python"


def test_settings_python_selection_persists_python_mode() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90101, text="/settings")

    response = router.handle_callback(telegram_user_id=90101, callback_data=CALLBACK_SETTINGS_PARSER_PYTHON)

    assert "Python/rule-based parser is active." in response.text
    user = deps.users_repo.get_by_telegram_id(90101)
    assert user is not None
    preferences = deps.user_preferences_repo.get_for_user(user.id)
    assert preferences is not None
    assert preferences.parser_mode.value == "python"


def test_settings_auto_selection_persists_auto_mode_with_fallback_message() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90102, text="/settings")

    response = router.handle_callback(telegram_user_id=90102, callback_data=CALLBACK_SETTINGS_PARSER_AUTO)

    assert "Parser mode updated to Auto." in response.text
    assert "because LLM is not configured" in response.text
    user = deps.users_repo.get_by_telegram_id(90102)
    assert user is not None
    preferences = deps.user_preferences_repo.get_for_user(user.id)
    assert preferences is not None
    assert preferences.parser_mode.value == "auto"


def test_settings_llm_selection_keeps_current_mode_unchanged() -> None:
    router, deps = _build_router()
    router.handle_text_message(telegram_user_id=90103, text="/settings")
    router.handle_callback(telegram_user_id=90103, callback_data=CALLBACK_SETTINGS_PARSER_AUTO)

    response = router.handle_callback(telegram_user_id=90103, callback_data=CALLBACK_SETTINGS_PARSER_LLM)

    assert "LLM parser is not available in current runtime configuration." in response.text
    assert "Current parser mode remains auto." in response.text
    user = deps.users_repo.get_by_telegram_id(90103)
    assert user is not None
    preferences = deps.user_preferences_repo.get_for_user(user.id)
    assert preferences is not None
    assert preferences.parser_mode.value == "auto"


def test_cashback_menu_message_does_not_create_calendar_event() -> None:
    router, deps = _build_router()
    response = router.handle_text_message(telegram_user_id=99001, text="💳 Кэшбек")
    assert "кэшбека" in response.text.lower()
    assert len(deps.calendar_service.requests) == 0


def test_cashback_structured_add_and_query_via_transport() -> None:
    router, deps = _build_router()
    response_add = router.handle_text_message(telegram_user_id=99002, text="Альфа, Владимир, Супермаркеты, 5%")
    assert "Добавил кэшбек" in response_add.text

    response_query = router.handle_text_message(telegram_user_id=99002, text="супермаркеты")
    assert "🏆 Кэшбек" in response_query.text
    assert "Владимир — Альфа — 5%" in response_query.text


def test_calendar_text_still_routes_to_calendar_preview_not_cashback() -> None:
    router, _ = _build_router()
    response = router.handle_text_message(telegram_user_id=99003, text="Тест завтра в 15:00")
    assert "Черновик события" in response.text


def test_conflict_message_returns_clarification() -> None:
    router, _ = _build_router()
    response = router.handle_text_message(telegram_user_id=99004, text="Напомни завтра выбрать кэшбек на супермаркеты")
    assert "несколько вариантов" in response.text
