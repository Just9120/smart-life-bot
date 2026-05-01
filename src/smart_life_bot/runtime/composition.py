"""Explicit runtime composition for local/dev foundation wiring."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from smart_life_bot.application.cashback_use_cases import (
    AddCashbackCategoryUseCase,
    CompleteTransitionCashbackCategoryUseCase,
    ListActiveCashbackCategoriesUseCase,
    QueryCashbackCategoryUseCase,
    RequestDeleteCashbackCategoryUseCase,
    RequestEditCashbackCategoryPercentUseCase,
    SoftDeleteCashbackCategoryUseCase,
    UpdateCashbackCategoryPercentUseCase,
)
from smart_life_bot.application.use_cases import (
    CancelEventDraftUseCase,
    ConfirmEventDraftUseCase,
    EditEventDraftFieldUseCase,
    GetUserSettingsUseCase,
    ProcessIncomingMessageUseCase,
    SetParserModeUseCase,
)
from smart_life_bot.bot import TelegramBotRuntime, TelegramTransportRouter
from smart_life_bot.calendar.interfaces import CalendarService
from smart_life_bot.calendar.google_calendar import GoogleCalendarService
from smart_life_bot.config.settings import Settings
from smart_life_bot.domain.enums import GoogleAuthMode
from smart_life_bot.observability.logger import ContextLoggerAdapter, get_context_logger
from smart_life_bot.parsing.interfaces import MessageParser
from smart_life_bot.parsing.router import ParserModeRouter
from smart_life_bot.parsing.rule_based import RuleBasedMessageParser
from smart_life_bot.parsing.claude import ClaudeMessageParser
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

from .fakes import DevFakeCalendarService, DevFakeGoogleAuthProvider


@dataclass(slots=True)
class RuntimeContainer:
    settings: Settings
    connection: sqlite3.Connection
    users_repo: SQLiteUsersRepository
    user_preferences_repo: SQLiteUserPreferencesRepository
    state_repo: SQLiteConversationStateRepository
    events_log_repo: SQLiteEventsLogRepository
    runtime: TelegramBotRuntime


@dataclass(slots=True)
class _Dependencies:
    parser: MessageParser
    auth_provider: DevFakeGoogleAuthProvider
    calendar_service: CalendarService
    users_repo: SQLiteUsersRepository
    user_preferences_repo: SQLiteUserPreferencesRepository
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
    user_preferences_repo = SQLiteUserPreferencesRepository(connection)
    state_repo = SQLiteConversationStateRepository(connection)
    events_log_repo = SQLiteEventsLogRepository(connection)
    cashback_repo = SQLiteCashbackCategoriesRepository(connection)

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

    python_parser = RuleBasedMessageParser(default_timezone=settings.default_timezone)
    llm_parser: MessageParser | None = None
    if settings.llm_provider == "anthropic" and settings.anthropic_api_key and settings.llm_model:
        llm_parser = ClaudeMessageParser(
            model=settings.llm_model,
            api_key=settings.anthropic_api_key,
            default_timezone=settings.default_timezone,
            timeout_seconds=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
            max_tokens=settings.llm_max_tokens,
        )

    parser = ParserModeRouter(
        user_preferences_repo=user_preferences_repo,
        python_parser=python_parser,
        llm_parser=llm_parser,
    )

    deps = _Dependencies(
        parser=parser,
        auth_provider=DevFakeGoogleAuthProvider(auth_mode=settings.google_auth_mode),
        calendar_service=calendar_service,
        users_repo=users_repo,
        user_preferences_repo=user_preferences_repo,
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
        get_user_settings=GetUserSettingsUseCase(deps=deps),
        set_parser_mode=SetParserModeUseCase(deps=deps, llm_available=llm_parser is not None),
        default_timezone=settings.default_timezone,
        llm_available=llm_parser is not None,
        supports_custom_reminders=settings.google_auth_mode is not GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE,
        add_cashback_category=AddCashbackCategoryUseCase(cashback_repo),
        query_cashback_category=QueryCashbackCategoryUseCase(cashback_repo),
        list_active_cashback_categories=ListActiveCashbackCategoriesUseCase(cashback_repo),
        request_delete_cashback_category=RequestDeleteCashbackCategoryUseCase(cashback_repo),
        request_edit_cashback_category_percent=RequestEditCashbackCategoryPercentUseCase(cashback_repo),
        soft_delete_cashback_category=SoftDeleteCashbackCategoryUseCase(cashback_repo),
        update_cashback_category_percent=UpdateCashbackCategoryPercentUseCase(cashback_repo),
        complete_transition_cashback_category=CompleteTransitionCashbackCategoryUseCase(cashback_repo),
    )

    return RuntimeContainer(
        settings=settings,
        connection=connection,
        users_repo=users_repo,
        user_preferences_repo=user_preferences_repo,
        state_repo=state_repo,
        events_log_repo=events_log_repo,
        runtime=TelegramBotRuntime(router=router),
    )
