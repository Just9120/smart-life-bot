"""Application-facing interfaces."""

from typing import Protocol

from smart_life_bot.auth.interfaces import GoogleAuthProvider
from smart_life_bot.calendar.interfaces import CalendarService
from smart_life_bot.parsing.interfaces import MessageParser
from smart_life_bot.storage.interfaces import (
    ConversationStateRepository,
    EventsLogRepository,
    ProviderCredentialsRepository,
    UserOAuthConnectionStateRepository,
    UserPreferencesRepository,
    UsersRepository,
)


class ObservabilityLogger(Protocol):
    def info(self, message: str, **extra: object) -> None: ...

    def warning(self, message: str, **extra: object) -> None: ...

    def error(self, message: str, **extra: object) -> None: ...


class ApplicationDependencies(Protocol):
    parser: MessageParser
    auth_provider: GoogleAuthProvider
    calendar_service: CalendarService
    users_repo: UsersRepository
    user_preferences_repo: UserPreferencesRepository
    credentials_repo: ProviderCredentialsRepository
    oauth_state_repo: UserOAuthConnectionStateRepository
    state_repo: ConversationStateRepository
    events_log_repo: EventsLogRepository
    logger: ObservabilityLogger
