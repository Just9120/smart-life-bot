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


class ValueErrorAuthProvider(FakeAuthProvider):
    def resolve_auth_context(self, user_id: int) -> AuthContext:
        self.calls += 1
        raise ValueError("provider auth bad value")


class ValueErrorCalendarService(FakeCalendarService):
    def create_event(
        self,
        auth_context: AuthContext,
        request: CalendarEventCreateRequest,
    ) -> CalendarEventCreateResult:
        self.requests.append(request)
        raise ValueError("calendar runtime bad value")


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


class InvalidTimezoneParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 1, 10, 9, 0),
                timezone="Not/AZone",
                metadata={"source": "invalid-timezone-parser"},
            ),
            confidence=0.99,
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
                start_at=datetime(2026, 1, 10, 9, 0),
                timezone=self.timezone,
                metadata={"source": "malformed-timezone-parser"},
            ),
            confidence=0.99,
            is_ambiguous=False,
            issues=[],
        )


class NoneTimezoneParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 1, 10, 9, 0),
                timezone=None,
                metadata={"source": "none-timezone-parser"},
            ),
            confidence=0.99,
            is_ambiguous=False,
            issues=[],
        )


class InvalidRangeParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 1, 10, 9, 0),
                end_at=datetime(2026, 1, 10, 8, 30),
                timezone="UTC",
                metadata={"source": "invalid-range-parser"},
            ),
            confidence=0.99,
            is_ambiguous=False,
            issues=[],
        )


class MixedAwarenessParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
                end_at=datetime(2026, 1, 10, 10, 0),
                timezone="UTC",
                metadata={"source": "mixed-awareness-parser"},
            ),
            confidence=0.99,
            is_ambiguous=False,
            issues=[],
        )


class ParserDiagnosticsParser:
    def parse(self, text: str, user_id: int) -> ParsingResult:
        return ParsingResult(
            draft=EventDraft(
                title=f"Parsed: {text}",
                start_at=datetime(2026, 1, 10, 9, 0, tzinfo=UTC),
                timezone="UTC",
                metadata={
                    "source": "rule-based-parser",
                    "raw_text": text,
                    "user_id": str(user_id),
                    "parser_mode": "auto",
                    "parser_router": "llm_fallback",
                    "llm_fallback_available": "true",
                    "llm_provider": "anthropic",
                    "llm_model": "claude-haiku-4-5-20251001",
                    "llm_parser": "claude",
                },
            ),
            confidence=0.923,
            is_ambiguous=False,
            issues=["missing_start_at", "invalid_timezone"],
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
    user_preferences_repo: SQLiteUserPreferencesRepository
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
        user_preferences_repo=SQLiteUserPreferencesRepository(connection),
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


def test_confirm_validation_failure_when_timezone_invalid() -> None:
    for timezone_value, text in (("Not/AZone", "Bad timezone"), ("/UTC", "Malformed timezone /UTC"), ("../UTC", "Malformed timezone ../UTC")):
        deps, user_id = _build_dependencies()
        deps.parser = InvalidTimezoneParser() if timezone_value == "Not/AZone" else MalformedTimezoneParser(timezone_value)

        ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text=text))
        result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

        assert result.status == "failed"
        assert "timezone must be a valid IANA timezone" in result.message
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


def test_confirm_validation_failure_when_timezone_is_none() -> None:
    deps, user_id = _build_dependencies()
    deps.parser = NoneTimezoneParser()

    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="None timezone"))
    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "failed"
    assert "timezone must be a valid IANA timezone" in result.message
    assert deps.auth_provider.calls == 0
    assert len(deps.calendar_service.requests) == 0


def test_confirm_validation_failure_when_end_at_not_after_start_at() -> None:
    deps, user_id = _build_dependencies()
    deps.parser = InvalidRangeParser()

    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Invalid range"))
    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "failed"
    assert "end_at must be later than start_at" in result.message
    assert deps.auth_provider.calls == 0
    assert len(deps.calendar_service.requests) == 0


def test_confirm_validation_failure_when_datetime_awareness_is_mixed() -> None:
    deps, user_id = _build_dependencies()
    deps.parser = MixedAwarenessParser()

    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Mixed awareness"))
    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "failed"
    assert "timezone-aware or both timezone-naive" in result.message
    assert deps.auth_provider.calls == 0
    assert len(deps.calendar_service.requests) == 0
    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.state is ConversationState.WAITING_PREVIEW_CONFIRMATION


def test_confirm_with_malformed_event_log_id_fails_safely_without_calendar_write() -> None:
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
    assert result.message == "Event creation failed"

    assert deps.auth_provider.calls == 0
    assert len(deps.calendar_service.requests) == 0

    restored_state = deps.state_repo.get(user_id)
    assert restored_state is not None
    assert restored_state.state is ConversationState.WAITING_PREVIEW_CONFIRMATION
    assert restored_state.draft is not None
    assert restored_state.draft.metadata["event_log_id"] == "bad-log-id"

    logs = deps.events_log_repo.list_for_user(user_id)
    assert len(logs) == 1
    assert logs[0].status is EventLogStatus.PREVIEW_READY


def test_stale_confirm_callback_after_cancel_fails_without_calendar_write() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Cancelable"))

    cancel_result = CancelEventDraftUseCase(deps).execute(CancelEventDraftInput(user_id=user_id))
    assert cancel_result.status == "cancelled"

    stale_confirm_result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert stale_confirm_result.status == "failed"
    assert stale_confirm_result.message == "No pending draft for confirmation"
    assert deps.auth_provider.calls == 0
    assert len(deps.calendar_service.requests) == 0
    assert deps.state_repo.get(user_id) is None


def test_stale_confirm_callback_after_success_does_not_write_duplicate_event() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="One save only"))

    first_confirm_result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))
    assert first_confirm_result.status == "success"
    assert len(deps.calendar_service.requests) == 1

    stale_confirm_result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert stale_confirm_result.status == "failed"
    assert stale_confirm_result.message == "No pending draft for confirmation"
    assert len(deps.calendar_service.requests) == 1
    assert deps.state_repo.get(user_id) is None


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


def test_edit_rejects_invalid_timezone_without_saving() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Edit timezone"))
    state_before = deps.state_repo.get(user_id)
    assert state_before is not None
    assert state_before.draft is not None
    original_timezone = state_before.draft.timezone

    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="timezone", field_value="Not/AZone")
    )

    assert result.status == "failed"
    state_after = deps.state_repo.get(user_id)
    assert state_after is not None
    assert state_after.draft is not None
    assert state_after.draft.timezone == original_timezone
    assert deps.auth_provider.calls == 0
    assert len(deps.calendar_service.requests) == 0


def test_edit_rejects_invalid_time_range_without_saving() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Edit range"))

    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="end_at", field_value="2026-01-10T08:00:00+00:00")
    )

    assert result.status == "failed"
    assert "end_at must be later than start_at" in result.message
    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.draft is not None
    assert state.draft.end_at is None


def test_edit_rejects_mixed_awareness_without_saving() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Edit mixed awareness"))

    result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="end_at", field_value="2026-01-10T10:00:00")
    )

    assert result.status == "failed"
    assert "timezone-aware or both timezone-naive" in result.message
    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.draft is not None
    assert state.draft.end_at is None


def test_edit_allows_clearing_end_at() -> None:
    deps, user_id = _build_dependencies()
    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Edit clear end_at"))
    set_result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="end_at", field_value="2026-01-10T11:00:00+00:00")
    )
    assert set_result.status == "preview_ready"

    clear_result = EditEventDraftFieldUseCase(deps).execute(
        EditEventDraftFieldInput(user_id=user_id, field_name="end_at", field_value="")
    )
    assert clear_result.status == "preview_ready"
    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.draft is not None
    assert state.draft.end_at is None


def test_confirm_runtime_value_error_is_not_classified_as_validation_error() -> None:
    deps, user_id = _build_dependencies()
    deps.auth_provider = ValueErrorAuthProvider()

    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Runtime error"))
    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "failed"
    assert result.message == "Event creation failed"
    assert "provider auth bad value" not in result.message
    logs = deps.events_log_repo.list_for_user(user_id)
    assert logs[0].status is EventLogStatus.FAILED
    assert logs[0].error_code == "internal_error"


def test_confirm_calendar_runtime_value_error_is_not_validation_error() -> None:
    deps, user_id = _build_dependencies()
    deps.calendar_service = ValueErrorCalendarService()

    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Calendar runtime error"))
    result = ConfirmEventDraftUseCase(deps).execute(ConfirmEventDraftInput(user_id=user_id))

    assert result.status == "failed"
    assert result.message == "Event creation failed"
    assert "calendar runtime bad value" not in result.message
    logs = deps.events_log_repo.list_for_user(user_id)
    assert logs[0].status is EventLogStatus.FAILED
    assert logs[0].error_code == "internal_error"


def test_incoming_message_persists_parser_diagnostics_without_losing_router_metadata() -> None:
    deps, user_id = _build_dependencies()
    deps.parser = ParserDiagnosticsParser()

    ProcessIncomingMessageUseCase(deps).execute(IncomingMessageInput(user_id=user_id, text="Diagnostics case"))

    state = deps.state_repo.get(user_id)
    assert state is not None
    assert state.draft is not None
    metadata = state.draft.metadata
    assert metadata["source"] == "rule-based-parser"
    assert metadata["parser_mode"] == "auto"
    assert metadata["parser_router"] == "llm_fallback"
    assert metadata["llm_fallback_available"] == "true"
    assert metadata["llm_provider"] == "anthropic"
    assert metadata["llm_model"] == "claude-haiku-4-5-20251001"
    assert metadata["llm_parser"] == "claude"
    assert metadata["parser_confidence"] == "0.92"
    assert metadata["parser_is_ambiguous"] == "false"
    assert metadata["parser_issues"] == "missing_start_at,invalid_timezone"
