"""Core domain models for event capture flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .enums import ConversationState


@dataclass(slots=True)
class EventDraft:
    title: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    description: str | None = None
    location: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationStateSnapshot:
    user_id: int
    state: ConversationState
    draft: EventDraft | None = None
    editing_field: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderCredentialsRef:
    user_id: int
    provider: str
    credentials_key: str
