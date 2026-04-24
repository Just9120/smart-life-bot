"""Calendar service abstraction."""

from typing import Protocol

from smart_life_bot.auth.models import AuthContext

from .models import CalendarEventCreateRequest, CalendarEventCreateResult


class CalendarService(Protocol):
    def create_event(
        self,
        auth_context: AuthContext,
        request: CalendarEventCreateRequest,
    ) -> CalendarEventCreateResult: ...
