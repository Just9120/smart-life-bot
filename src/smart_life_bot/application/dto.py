"""DTOs for application use-case boundaries."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IncomingMessageInput:
    user_id: int
    text: str


@dataclass(frozen=True, slots=True)
class ConfirmEventDraftInput:
    user_id: int


@dataclass(frozen=True, slots=True)
class EditEventDraftFieldInput:
    user_id: int
    field_name: str
    field_value: str


@dataclass(frozen=True, slots=True)
class CancelEventDraftInput:
    user_id: int


@dataclass(frozen=True, slots=True)
class UseCaseResult:
    status: str
    message: str
    provider_event_id: str | None = None
    provider_event_html_link: str | None = None
