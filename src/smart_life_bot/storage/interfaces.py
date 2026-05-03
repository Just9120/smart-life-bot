"""Storage-layer repository contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from smart_life_bot.domain.enums import EventLogErrorCategory, EventLogStatus, ParserMode
from smart_life_bot.domain.models import ConversationStateSnapshot


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: int
    telegram_user_id: int
    timezone: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProviderCredentialsRecord:
    id: int
    user_id: int
    provider: str
    auth_mode: str
    credentials_encrypted: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UserPreferencesRecord:
    user_id: int
    parser_mode: ParserMode
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class EventLogEntry:
    id: int | None
    user_id: int
    raw_text: str | None
    parsed_payload: dict[str, object] | None
    status: EventLogStatus
    google_event_id: str | None = None
    error_code: str | None = None
    error_details: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class UserOAuthConnectionStateRecord:
    user_id: int
    status: str
    state_token_hash: str | None
    error_code: str | None
    connected_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UsersRepository(Protocol):
    def get_by_telegram_id(self, telegram_user_id: int) -> UserRecord | None: ...

    def create(self, telegram_user_id: int, timezone: str | None = None) -> UserRecord: ...

    def get_or_create_by_telegram_id(
        self,
        telegram_user_id: int,
        timezone: str | None = None,
    ) -> UserRecord: ...


class ProviderCredentialsRepository(Protocol):
    def get_for_user(
        self,
        user_id: int,
        provider: str,
        auth_mode: str,
    ) -> ProviderCredentialsRecord | None: ...

    def save_for_user(
        self,
        user_id: int,
        provider: str,
        auth_mode: str,
        credentials_encrypted: str,
    ) -> ProviderCredentialsRecord: ...


class UserPreferencesRepository(Protocol):
    def get_for_user(self, user_id: int) -> UserPreferencesRecord | None: ...

    def get_or_create_for_user(
        self,
        user_id: int,
        default_parser_mode: ParserMode,
    ) -> UserPreferencesRecord: ...

    def set_parser_mode(self, user_id: int, parser_mode: ParserMode) -> UserPreferencesRecord: ...


class ConversationStateRepository(Protocol):
    def get(self, user_id: int) -> ConversationStateSnapshot | None: ...

    def set(self, snapshot: ConversationStateSnapshot) -> None: ...

    def reset(self, user_id: int) -> None: ...


class EventsLogRepository(Protocol):
    def append(self, entry: EventLogEntry) -> EventLogEntry: ...

    def update_status(
        self,
        entry_id: int,
        status: EventLogStatus,
        error_category: EventLogErrorCategory | None = None,
        google_event_id: str | None = None,
        error_code: str | None = None,
        error_details: str | None = None,
    ) -> None: ...

    def get_by_id(self, entry_id: int) -> EventLogEntry | None: ...

    def list_for_user(self, user_id: int) -> list[EventLogEntry]: ...


class UserOAuthConnectionStateRepository(Protocol):
    def get_for_user(self, user_id: int) -> UserOAuthConnectionStateRecord | None: ...

    def get_or_create_for_user(self, user_id: int) -> UserOAuthConnectionStateRecord: ...

    def mark_pending(self, user_id: int, state_token_hash: str) -> UserOAuthConnectionStateRecord: ...

    def mark_disconnected(self, user_id: int) -> UserOAuthConnectionStateRecord: ...

    def mark_error(self, user_id: int, error_code: str) -> UserOAuthConnectionStateRecord: ...

    def get_by_state_token_hash(self, state_token_hash: str) -> UserOAuthConnectionStateRecord | None: ...
