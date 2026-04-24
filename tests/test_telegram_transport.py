from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from smart_life_bot.application.use_cases import (
    CancelEventDraftUseCase,
    ConfirmEventDraftUseCase,
    EditEventDraftFieldUseCase,
    ProcessIncomingMessageUseCase,
)
from smart_life_bot.auth.models import AuthContext
from smart_life_bot.bot import CALLBACK_CANCEL, CALLBACK_CONFIRM, CALLBACK_EDIT, TelegramTransportRouter
from smart_life_bot.calendar.models import CalendarEventCreateRequest, CalendarEventCreateResult
from smart_life_bot.domain.enums import EventLogStatus, GoogleAuthMode
from smart_life_bot.domain.models import EventDraft
from smart_life_bot.parsing.models import ParsingResult
from smart_life_bot.storage.sqlite import (
    SQLiteConversationStateRepository,
    SQLiteEventsLogRepository,
    SQLiteProviderCredentialsRepository,
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

    assert response.text == "Event created successfully"
    user = deps.users_repo.get_by_telegram_id(90002)
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
    assert "НЕ будет создано" in response.text


def test_transport_layer_does_not_require_real_google_or_telegram_network() -> None:
    router, deps = _build_router()

    response = router.handle_callback(telegram_user_id=90006, callback_data=CALLBACK_EDIT)

    assert "/edit <field> <value>" in response.text
    assert len(deps.calendar_service.requests) == 0
