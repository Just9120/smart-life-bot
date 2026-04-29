"""Google Calendar service-account adapter."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from smart_life_bot.auth.models import AuthContext
from smart_life_bot.domain.enums import GoogleAuthMode

from .models import CalendarEventCreateRequest, CalendarEventCreateResult

CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"

LOGGER = logging.getLogger(__name__)


def _default_service_builder(*args: object, **kwargs: object) -> object:
    from googleapiclient.discovery import build

    return build(*args, **kwargs)


def _default_credentials_loader(service_account_json: str) -> object:
    from google.oauth2 import service_account

    raw = service_account_json.strip()
    if not raw:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON is empty")

    path = Path(raw)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(
                "GOOGLE_SERVICE_ACCOUNT_JSON must be either a JSON string or a valid file path"
            ) from error

    return service_account.Credentials.from_service_account_info(payload, scopes=[CALENDAR_EVENTS_SCOPE])


@dataclass(slots=True)
class GoogleCalendarService:
    """Create Google Calendar events via service-account shared calendar mode."""

    calendar_id: str
    service_account_json: str
    service_builder: Callable[..., object] = _default_service_builder
    credentials_loader: Callable[[str], object] = _default_credentials_loader

    def create_event(
        self,
        auth_context: AuthContext,
        request: CalendarEventCreateRequest,
    ) -> CalendarEventCreateResult:
        if auth_context.auth_mode is not GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE:
            raise ValueError(
                "GoogleCalendarService supports only service_account_shared_calendar_mode auth context"
            )
        credentials = self.credentials_loader(self.service_account_json)
        service = self.service_builder(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )
        event_body = self._build_event_body(request)
        reminders = event_body.get("reminders", {})
        overrides = reminders.get("overrides", []) if isinstance(reminders, dict) else []
        LOGGER.info(
            "Google Calendar event reminders payload prepared",
            extra={
                "reminders_use_default": reminders.get("useDefault") if isinstance(reminders, dict) else None,
                "reminders_overrides": [
                    {"method": item.get("method"), "minutes": item.get("minutes")}
                    for item in overrides
                    if isinstance(item, dict)
                ],
            },
        )
        response = self._insert_event(service=service, event_body=event_body)

        provider_event_id = str(response.get("id", ""))
        if not provider_event_id:
            raise ValueError("Google Calendar response is missing event id")

        return CalendarEventCreateResult(
            event_id=provider_event_id,
            provider_event_id=provider_event_id,
            html_link=response.get("htmlLink"),
        )

    def _build_event_body(self, request: CalendarEventCreateRequest) -> dict[str, Any]:
        event_body: dict[str, Any] = {
            "summary": request.title,
            "start": {
                "dateTime": request.start_at_iso,
                "timeZone": request.timezone,
            },
            "end": {
                "dateTime": request.end_at_iso or (datetime.fromisoformat(request.start_at_iso) + timedelta(minutes=1)).isoformat(),
                "timeZone": request.timezone,
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": minutes}
                    for minutes in (request.reminder_minutes or (60, 30))
                ],
            },
        }
        if request.description:
            event_body["description"] = request.description
        if request.location:
            event_body["location"] = request.location
        return event_body

    def _insert_event(self, service: object, event_body: dict[str, Any]) -> dict[str, Any]:
        events_resource = getattr(service, "events")()
        insert_call = events_resource.insert(calendarId=self.calendar_id, body=event_body)
        return dict(insert_call.execute())
