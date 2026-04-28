from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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
    CALLBACK_EDIT,
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
                timezone="Mars/Olympus",
            ),
            confidence=0.60,
            is_ambiguous=True,
            issues=["invalid_timezone"],
        )


class InvalidTimeRangeParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
                end_at=datetime(2026, 3, 12, 9, 0, tzinfo=UTC),
                timezone="UTC",
            ),
            confidence=0.60,
            is_ambiguous=True,
            issues=["invalid_time_range"],
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
    )
    return router, deps


def _build_router_no_html_link() -> tuple[TelegramTransportRouter, Deps]:
    connection = create_sqlite_connection("sqlite:///:memory:")
    init_sqlite_schema(connection)

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


def test_edit_start_at_restores_confirm_button() -> None:
    router, deps = _build_router()
    deps.parser = MissingStartAtParser()
    router.handle_text_message(telegram_user_id=90011, text="Missing start_at")

    response = router.handle_text_message(telegram_user_id=90011, text="/edit start_at 2026-02-14T11:30:00+00:00")

    assert ("✅ Confirm", CALLBACK_CONFIRM) in response.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons


def test_preview_buttons_hide_confirm_when_timezone_invalid() -> None:
    router, deps = _build_router()
    deps.parser = InvalidTimezoneParser()

    response = router.handle_text_message(telegram_user_id=90013, text="Invalid timezone")

    assert ("✅ Confirm", CALLBACK_CONFIRM) not in response.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons
    assert "Нужно исправить timezone перед созданием события." in response.text


def test_preview_buttons_hide_confirm_when_time_range_invalid() -> None:
    router, deps = _build_router()
    deps.parser = InvalidTimeRangeParser()

    response = router.handle_text_message(telegram_user_id=90014, text="Invalid time range")

    assert ("✅ Confirm", CALLBACK_CONFIRM) not in response.buttons
    assert ("✏️ Edit", CALLBACK_EDIT) in response.buttons
    assert ("❌ Cancel", CALLBACK_CANCEL) in response.buttons
    assert "Нужно исправить время: end_at должен быть позже start_at." in response.text


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


def test_format_preview_message_shows_invalid_timezone_hint() -> None:
    draft = EventDraft(
        title="Parsed title",
        start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        timezone="Mars/Olympus",
    )

    preview = format_preview_message(draft)

    assert "Нужно исправить timezone перед созданием события." in preview


def test_format_preview_message_shows_invalid_time_range_hint() -> None:
    draft = EventDraft(
        title="Parsed title",
        start_at=datetime(2026, 3, 12, 10, 0, tzinfo=UTC),
        end_at=datetime(2026, 3, 12, 9, 0, tzinfo=UTC),
        timezone="UTC",
    )

    preview = format_preview_message(draft)

    assert "Нужно исправить время: end_at должен быть позже start_at." in preview


def test_format_preview_message_is_safe_when_parser_metadata_missing() -> None:
    draft = EventDraft(title="Parsed title")

    preview = format_preview_message(draft)

    assert "- mode: —" in preview
    assert "- route: —" in preview
    assert "- source: —" in preview
    assert "- confidence: —" in preview


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
