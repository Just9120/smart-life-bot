"""Calendar integration models."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CalendarEventCreateRequest:
    title: str
    start_at_iso: str
    end_at_iso: str | None
    timezone: str
    description: str | None = None
    location: str | None = None


@dataclass(frozen=True, slots=True)
class CalendarEventCreateResult:
    event_id: str
    provider_event_id: str
    html_link: str | None = None
