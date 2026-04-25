"""Explicit runtime composition for local/dev foundation wiring."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from smart_life_bot.application.use_cases import (
    CancelEventDraftUseCase,
    ConfirmEventDraftUseCase,
    EditEventDraftFieldUseCase,
    ProcessIncomingMessageUseCase,
)
from smart_life_bot.bot import TelegramBotRuntime, TelegramTransportRouter
from smart_life_bot.calendar.interfaces import CalendarService
from smart_life_bot.calendar.google_calendar import GoogleCalendarService
from smart_life_bot.config.settings import Settings
from smart_life_bot.domain.enums import GoogleAuthMode
from smart_life_bot.observability.logger import ContextLoggerAdapter, get_context_logger
from smart_life_bot.parsing.interfaces import MessageParser
from smart_life_bot.parsing.rule_based import RuleBasedMessageParser
from smart_life_bot.storage.sqlite import (
    SQLiteConversationStateRepository,
    SQLiteEventsLogRepository,
    SQLiteProviderCredentialsRepository,
    SQLiteUsersRepository,
    create_sqlite_connection,
    init_sqlite_schema,
)

from .fakes import DevFakeCalendarService, DevFakeGoogleAuthProvider


@dataclass(slots=True)
class RuntimeContainer:
    settings: Settings
    connection: sqlite3.Connection
    users_repo: SQLiteUsersRepository
    state_repo: SQLiteConversationStateRepository
    events_log_repo: SQLiteEventsLogRepository
    runtime: TelegramBotRuntime


@dataclass(slots=True)
class _Dependencies:
    parser: MessageParser
    auth_provider: DevFakeGoogleAuthProvider
    calendar_service: CalendarService
    users_repo: SQLiteUsersRepository
    credentials_repo: SQLiteProviderCredentialsRepository
    state_repo: SQLiteConversationStateRepository
    events_log_repo: SQLiteEventsLogRepository
    logger: ContextLoggerAdapter


def build_runtime(settings: Settings) -> RuntimeContainer:
    """Build runtime graph for local/dev execution without external SDK/API calls."""
    connection = create_sqlite_connection(settings.database_url)
    init_sqlite_schema(connection)

    users_repo = SQLiteUsersRepository(connection)
    credentials_repo = SQLiteProviderCredentialsRepository(connection)
    state_repo = SQLiteConversationStateRepository(connection)
    events_log_repo = SQLiteEventsLogRepository(connection)

    calendar_service: CalendarService = DevFakeCalendarService()
    if (
        settings.google_auth_mode is GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE
        and settings.google_service_account_json
        and settings.google_shared_calendar_id
    ):
        calendar_service = GoogleCalendarService(
            calendar_id=settings.google_shared_calendar_id,
            service_account_json=settings.google_service_account_json,
        )

    deps = _Dependencies(
        parser=RuleBasedMessageParser(default_timezone=settings.default_timezone),
        auth_provider=DevFakeGoogleAuthProvider(auth_mode=settings.google_auth_mode),
        calendar_service=calendar_service,
        users_repo=users_repo,
        credentials_repo=credentials_repo,
        state_repo=state_repo,
        events_log_repo=events_log_repo,
        logger=get_context_logger(),
    )

    router = TelegramTransportRouter(
        users_repo=users_repo,
        state_repo=state_repo,
        process_incoming_message=ProcessIncomingMessageUseCase(deps=deps),
        confirm_draft=ConfirmEventDraftUseCase(deps=deps),
        cancel_draft=CancelEventDraftUseCase(deps=deps),
        edit_draft_field=EditEventDraftFieldUseCase(deps=deps),
        default_timezone=settings.default_timezone,
    )

    return RuntimeContainer(
        settings=settings,
        connection=connection,
        users_repo=users_repo,
        state_repo=state_repo,
        events_log_repo=events_log_repo,
        runtime=TelegramBotRuntime(router=router),
    )
