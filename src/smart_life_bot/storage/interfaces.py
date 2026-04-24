"""Storage-layer repository contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from smart_life_bot.domain.enums import EventLogErrorCategory, EventLogStatus
from smart_life_bot.domain.models import ConversationStateSnapshot, ProviderCredentialsRef


@dataclass(frozen=True, slots=True)
class UserRecord:
    user_id: int
    telegram_id: int


@dataclass(frozen=True, slots=True)
class EventLogEntry:
    event_id: str
    user_id: int
    status: EventLogStatus
    error_category: EventLogErrorCategory | None = None
    message: str | None = None


class UsersRepository(Protocol):
    def get_by_telegram_id(self, telegram_id: int) -> UserRecord | None: ...

    def create(self, telegram_id: int) -> UserRecord: ...


class ProviderCredentialsRepository(Protocol):
    def get_for_user(self, user_id: int) -> ProviderCredentialsRef | None: ...

    def save_for_user(self, value: ProviderCredentialsRef) -> None: ...


class ConversationStateRepository(Protocol):
    def get(self, user_id: int) -> ConversationStateSnapshot | None: ...

    def set(self, snapshot: ConversationStateSnapshot) -> None: ...

    def reset(self, user_id: int) -> None: ...


class EventsLogRepository(Protocol):
    def append(self, entry: EventLogEntry) -> None: ...

    def update_status(
        self,
        event_id: str,
        status: EventLogStatus,
        error_category: EventLogErrorCategory | None = None,
    ) -> None: ...
