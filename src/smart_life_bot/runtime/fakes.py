"""Deterministic fake adapters for local/dev runtime composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from smart_life_bot.auth.models import AuthContext
from smart_life_bot.calendar.models import CalendarEventCreateRequest, CalendarEventCreateResult
from smart_life_bot.domain.enums import GoogleAuthMode
from smart_life_bot.domain.models import EventDraft
from smart_life_bot.parsing.models import ParsingResult


@dataclass(slots=True)
class DevFakeMessageParser:
    """Dev-only parser that deterministically builds an EventDraft from text."""

    default_timezone: str

    def parse(self, text: str, user_id: int) -> ParsingResult:
        normalized = text.strip() or "Untitled event"
        draft = EventDraft(
            title=f"Parsed: {normalized}",
            start_at=datetime(2026, 1, 1, 9, 0, tzinfo=UTC),
            end_at=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            timezone=self.default_timezone,
            metadata={"source": "dev-fake-parser", "user_id": str(user_id)},
        )
        return ParsingResult(draft=draft, confidence=1.0, is_ambiguous=False, issues=[])


@dataclass(slots=True)
class DevFakeGoogleAuthProvider:
    """Dev-only auth provider that returns deterministic fake auth context."""

    auth_mode: GoogleAuthMode

    def resolve_auth_context(self, user_id: int) -> AuthContext:
        return AuthContext(
            user_id=user_id,
            auth_mode=self.auth_mode,
            credentials_handle=f"dev-fake-auth:{user_id}",
        )


@dataclass(slots=True)
class DevFakeCalendarService:
    """Dev-only calendar adapter that never performs network calls."""

    def create_event(
        self,
        auth_context: AuthContext,
        request: CalendarEventCreateRequest,
    ) -> CalendarEventCreateResult:
        provider_event_id = (
            f"dev-fake-event:{auth_context.user_id}:"
            f"{request.start_at_iso}:{request.title.replace(' ', '_')}"
        )
        return CalendarEventCreateResult(
            event_id=provider_event_id,
            provider_event_id=provider_event_id,
            html_link=None,
        )
