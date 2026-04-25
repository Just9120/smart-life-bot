"""Storage contracts."""

from .interfaces import (
    ConversationStateRepository,
    EventLogEntry,
    EventsLogRepository,
    ProviderCredentialsRecord,
    ProviderCredentialsRepository,
    UserRecord,
    UserPreferencesRecord,
    UserPreferencesRepository,
    UsersRepository,
)
from .sqlite import (
    SQLiteConversationStateRepository,
    SQLiteEventsLogRepository,
    SQLiteProviderCredentialsRepository,
    SQLiteUserPreferencesRepository,
    SQLiteUsersRepository,
    create_sqlite_connection,
    init_sqlite_schema,
)

__all__ = [
    "ConversationStateRepository",
    "EventLogEntry",
    "EventsLogRepository",
    "ProviderCredentialsRecord",
    "ProviderCredentialsRepository",
    "SQLiteConversationStateRepository",
    "SQLiteEventsLogRepository",
    "SQLiteProviderCredentialsRepository",
    "SQLiteUserPreferencesRepository",
    "SQLiteUsersRepository",
    "UserRecord",
    "UserPreferencesRecord",
    "UserPreferencesRepository",
    "UsersRepository",
    "create_sqlite_connection",
    "init_sqlite_schema",
]
