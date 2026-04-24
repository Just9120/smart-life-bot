from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from smart_life_bot.application.dto import CancelEventDraftInput, ConfirmEventDraftInput, IncomingMessageInput
from smart_life_bot.application.use_cases import (
    CancelEventDraftUseCase,
    ConfirmEventDraftUseCase,
    ProcessIncomingMessageUseCase,
)
from smart_life_bot.auth.models import AuthContext
from smart_life_bot.calendar.interfaces import CalendarService
from smart_life_bot.calendar.models import CalendarEventCreateRequest, CalendarEventCreateResult
from smart_life_bot.domain.enums import ConversationState, EventLogStatus, GoogleAuthMode
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
                start_at=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
                timezone="UTC",
                metadata={"source": "fake-parser"},
            ),
            confidence=0.99,
            is_ambiguous=False,
            issues=[],
        )


class FakeAuthProvider:
    def __init__(self) -> None:
        self.calls = 0

    def resolve_auth_context(self, user_id: int) -> AuthContext:
        self.calls += 1
        return AuthContext(
            user_id=user_id,
            auth_mode=GoogleAuthMode.OAUTH_USER_MODE,
            credentials_handle="fake-auth-context",
        )


class FakeCalendarService:
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
            provider_event_id="fake-provider-event-123",
            html_link="https://example.test/event/123",
        )


class FailingCalendarService:
    def __init__(self) -> None:
        self.calls = 0

    def create_event(
        self,
        auth_context: AuthContext,
        request: CalendarEventCreateRequest,
    ) -> CalendarEventCreateResult:
        self.calls += 1
        raise RuntimeError("calendar provider unavailable")


class MissingStartAtParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=None,
                timezone="UTC",
                metadata={"source": "missing-start-parser"},
            ),
            confidence=0.99,
            is_ambiguous=False,
            issues=[],
        )


class SilentLogger:
    def info(self, message: str, **extra: object) -> None:
        return None

    def warning(self, message: str, **extra: object) -> None:
        return None

    def error(self, message: str, **extra: object) -> None:
        return None


@dataclass
class ApplicationDependenciesFixture:
    parser: FakeParser
    auth_provider: FakeAuthProvider
    calendar_service: CalendarService
    users_repo: SQLiteUsersRepository
    credentials_repo: SQLiteProviderCredentialsRepository
    state_repo: SQLiteConversationStateRepository
    events_log_repo: SQLiteEventsLogRepository
    logger: SilentLogger


def _build_dependencies() -> tuple[ApplicationDependenciesFixture, int]:
    connection = create_sqlite_connection("sqlite:///:memory:")
    init_sqlite_schema(connection)

    users_repo = SQLiteUsersRepository(connection)
    user = users_repo.create(telegram_user_id=7001, timezone="UTC")

    deps = ApplicationDependenciesFixture(
        parser=FakeParser(),
        auth_provider=FakeAuthProvider(),
        calendar_service=FakeCalendarService(),
        users_repo=users_repo,
        credentials_repo=SQLiteProviderCredentialsRepository(connection),
        state_repo=SQLiteConversationStateRepository(connection),
        events_log_repo=SQLiteEventsLogRepository(connection),
        logger=SilentLogger(),
    )
    return deps, user.id


def test_incoming_message_creates_preview_state_and_log() -> None:
    deps, user_id = _build_dependencies()

    result = ProcessIncomingMessageUseCase(deps).execute(
        IncomingMessageInput(user_id=user_id, text="Team sync tomorrow at 9")
    )

    assert result.status == "preview_ready"
    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.state is ConversationState.WAITING_PREVIEW_CONFIRMATION
    assert state.draft is not None
    assert state.draft.title.startswith("Parsed:")

    logs = deps.events_log_repo.list_for_user(user_id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.PREVIEW_READY


def test_confirm_flow_creates_event_updates_log_and_resets_state() -> None:
    deps, user_id = _build_dependencies()

    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Doctor visit at 9"))
    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "success"
    assert result.provider_event_id == "fake-provider-event-123"
    assert deps.state_repo.get(user_id) is None

    logs = deps.events_log_repo.list_for_user(user_id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.SAVED
    assert logs[0].google_event_id == "fake-provider-event-123"

    assert len(deps.calendar_service.requests) == 1
    assert deps.calendar_service.requests[0].title.startswith("Parsed:")


def test_cancel_flow_resets_state_when_preview_is_pending() -> None:
    deps, user_id = _build_dependencies()

    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Lunch at noon"))
    preview_log = deps.events_log_repo.list_for_user(user_id)[0]
    assert preview_log.status is EventLogStatus.PREVIEW_READY

    result = CancelEventDraftUseCase(deps).execute(CancelEventDraftInput(user_id=user_id))

    assert result.status == "cancelled"
    assert deps.state_repo.get(user_id) is None
    cancelled_log = deps.events_log_repo.get_by_id(preview_log.id)
    assert cancelled_log is not None
    assert cancelled_log.status is EventLogStatus.CANCELLED


def test_confirm_failure_keeps_pending_draft_and_marks_log_failed() -> None:
    deps, user_id = _build_dependencies()
    deps.calendar_service = FailingCalendarService()

    ProcessIncomingMessageUseCase(deps).execute(
        IncomingMessageInput(user_id=user_id, text="Prepare report tomorrow at 10")
    )
    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "failed"
    logs = deps.events_log_repo.list_for_user(user_id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.FAILED

    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.state is ConversationState.WAITING_PREVIEW_CONFIRMATION
    assert state.draft is not None


def test_confirm_validation_failure_when_start_at_missing() -> None:
    deps, user_id = _build_dependencies()
    deps.parser = MissingStartAtParser()

    ProcessIncomingMessageUseCase(deps).execute(
        IncomingMessageInput(user_id=user_id, text="Event without explicit time")
    )
    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "failed"
    assert "start time is required" in result.message

    assert deps.auth_provider.calls == 0
    assert len(deps.calendar_service.requests) == 0

    logs = deps.events_log_repo.list_for_user(user_id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.FAILED
    assert logs[0].error_code == "validation_error"

    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.state is ConversationState.WAITING_PREVIEW_CONFIRMATION
    assert state.draft is not None
