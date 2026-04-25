from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

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
from smart_life_bot.auth.models import AuthContext
from smart_life_bot.calendar.interfaces import CalendarService
from smart_life_bot.calendar.models import CalendarEventCreateRequest, CalendarEventCreateResult
from smart_life_bot.domain.enums import ConversationState, EventLogStatus, GoogleAuthMode
from smart_life_bot.domain.models import ConversationStateSnapshot, EventDraft
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


class NoHtmlLinkCalendarService:
    def __init__(self) -> None:
        self.requests: list[CalendarEventCreateRequest] = []

    def create_event(
        self,
        auth_context: AuthContext,
        request: CalendarEventCreateRequest,
    ) -> CalendarEventCreateResult:
        self.requests.append(request)
        return CalendarEventCreateResult(
            event_id="internal-no-link-1",
            provider_event_id="fake-provider-event-no-link-123",
            html_link=None,
        )


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
    assert result.provider_event_html_link == "https://example.test/event/123"
    assert deps.state_repo.get(user_id) is None

    logs = deps.events_log_repo.list_for_user(user_id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.SAVED
    assert logs[0].google_event_id == "fake-provider-event-123"

    assert len(deps.calendar_service.requests) == 1
    assert deps.calendar_service.requests[0].title.startswith("Parsed:")


def test_confirm_flow_success_without_html_link_remains_backward_compatible() -> None:
    deps, user_id = _build_dependencies()
    deps.calendar_service = NoHtmlLinkCalendarService()

    ProcessIncomingMessageUseCase(deps).execute(
        IncomingMessageInput(user_id=user_id, text="No link result should still succeed")
    )
    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "success"
    assert result.message == "Event created successfully"
    assert result.provider_event_id == "fake-provider-event-no-link-123"
    assert result.provider_event_html_link is None


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


def test_confirm_failure_when_event_log_id_is_malformed() -> None:
    deps, user_id = _build_dependencies()

    ProcessIncomingMessageUseCase(deps).execute(
        IncomingMessageInput(user_id=user_id, text="Malformed event log id case")
    )
    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.draft is not None
    state.draft.metadata["event_log_id"] = "bad-log-id"
    deps.state_repo.set(state)

    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "failed"

    assert deps.auth_provider.calls == 0
    assert len(deps.calendar_service.requests) == 0

    restored_state = deps.state_repo.get(user_id)
    assert restored_state is not None
    assert restored_state.state is ConversationState.WAITING_PREVIEW_CONFIRMATION
    assert restored_state.draft is not None

    logs = deps.events_log_repo.list_for_user(user_id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.PREVIEW_READY


def test_edit_title_updates_pending_draft() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Initial title"))

    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="title", field_value="Updated title")
    )

    assert result.status == "preview_ready"
    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.draft is not None
    assert state.draft.title == "Updated title"


def test_edit_start_at_is_used_by_confirm_flow() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Move meeting time"))

    edit_result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(
            user_id=user_id,
            field_name="start_at",
            field_value="2026-02-14T11:30:00+00:00",
        )
    )
    assert edit_result.status == "preview_ready"

    confirm_result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))
    assert confirm_result.status == "success"
    assert len(deps.calendar_service.requests) == 1
    assert deps.calendar_service.requests[0].start_at_iso == "2026-02-14T11:30:00+00:00"


def test_edit_description_and_location_empty_value_clears_fields() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Has optional fields"))

    EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="description", field_value="Notes")
    )
    EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="location", field_value="Office")
    )

    description_result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="description", field_value="")
    )
    location_result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="location", field_value="")
    )

    assert description_result.status == "preview_ready"
    assert location_result.status == "preview_ready"
    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.draft is not None
    assert state.draft.description is None
    assert state.draft.location is None


def test_edit_unsupported_field_fails_and_keeps_draft_unchanged() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Original draft"))
    before = deps.state_repo.get(user_id)
    assert before is not None
    assert before.draft is not None
    original_title = before.draft.title

    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="attendees", field_value="alice@example.com")
    )

    assert result.status == "failed"
    assert "Unsupported editable field" in result.message
    after = deps.state_repo.get(user_id)
    assert after is not None
    assert after.draft is not None
    assert after.draft.title == original_title


def test_edit_invalid_datetime_fails_and_keeps_draft_unchanged() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Schedule item"))
    before = deps.state_repo.get(user_id)
    assert before is not None
    assert before.draft is not None
    original_start_at = before.draft.start_at

    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="start_at", field_value="not-a-datetime")
    )

    assert result.status == "failed"
    assert "Invalid datetime format" in result.message
    after = deps.state_repo.get(user_id)
    assert after is not None
    assert after.draft is not None
    assert after.draft.start_at == original_start_at


def test_edit_without_pending_draft_fails() -> None:
    deps, user_id = _build_dependencies()
    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="title", field_value="No draft")
    )
    assert result.status == "failed"
    assert result.message == "No pending draft for editing"


def test_edit_fails_when_state_is_not_waiting_preview_confirmation() -> None:
    deps, user_id = _build_dependencies()
    deps.state_repo.set(
        ConversationStateSnapshot(
            user_id=user_id,
            state=ConversationState.SAVING,
            draft=EventDraft(title="Any"),
        )
    )

    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="title", field_value="Updated")
    )

    assert result.status == "failed"
    assert result.message == "Draft editing is unavailable in current state"


def test_edit_preserves_event_log_id_metadata() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Metadata retention"))
    state_before = deps.state_repo.get(user_id)
    assert state_before is not None
    assert state_before.draft is not None
    event_log_id = state_before.draft.metadata.get("event_log_id")
    assert event_log_id is not None

    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="timezone", field_value="Europe/Berlin")
    )

    assert result.status == "preview_ready"
    state_after = deps.state_repo.get(user_id)
    assert state_after is not None
    assert state_after.draft is not None
    assert state_after.draft.metadata.get("event_log_id") == event_log_id


def test_edit_does_not_call_auth_provider_or_calendar_service() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Edit only"))

    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="title", field_value="Updated only")
    )

    assert result.status == "preview_ready"
    assert deps.auth_provider.calls == 0
    assert len(deps.calendar_service.requests) == 0
