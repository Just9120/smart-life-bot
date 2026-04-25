from __future__ import annotations

import json

import pytest

from smart_life_bot.auth.models import AuthContext
from smart_life_bot.calendar.google_calendar import GoogleCalendarService
from smart_life_bot.calendar.models import CalendarEventCreateRequest
from smart_life_bot.domain.enums import GoogleAuthMode


class _FakeInsertCall:
    def __init__(self, response: dict[str, object]) -> None:
        self._response = response

    def execute(self) -> dict[str, object]:
        return self._response


class _FakeEventsResource:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def insert(self, calendarId: str, body: dict[str, object]) -> _FakeInsertCall:
        self.calls.append({"calendarId": calendarId, "body": body})
        return _FakeInsertCall(self.response)


class _FakeService:
    def __init__(self, response: dict[str, object]) -> None:
        self.events_resource = _FakeEventsResource(response=response)

    def events(self) -> _FakeEventsResource:
        return self.events_resource


def _service_account_context() -> AuthContext:
    return AuthContext(
        user_id=1,
        auth_mode=GoogleAuthMode.SERVICE_ACCOUNT_SHARED_CALENDAR_MODE,
        credentials_handle="dev-fake-auth:1",
    )


def test_create_event_maps_request_to_google_event_body_and_calendar_id() -> None:
    fake_service = _FakeService({"id": "google-id-1", "htmlLink": "https://calendar.google.com/event?id=1"})
    captured: dict[str, object] = {}

    def _service_builder(*args: object, **kwargs: object) -> object:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return fake_service

    service = GoogleCalendarService(
        calendar_id="shared-calendar@example.com",
        service_account_json='{"type":"service_account"}',
        service_builder=_service_builder,
        credentials_loader=lambda _: object(),
    )
    request = CalendarEventCreateRequest(
        title="Team Sync",
        description="Weekly planning",
        location="Room 101",
        start_at_iso="2026-04-28T10:00:00+00:00",
        end_at_iso="2026-04-28T11:00:00+00:00",
        timezone="UTC",
    )

    result = service.create_event(auth_context=_service_account_context(), request=request)

    assert captured["args"] == ("calendar", "v3")
    assert captured["kwargs"]["cache_discovery"] is False
    assert len(fake_service.events_resource.calls) == 1
    insert_call = fake_service.events_resource.calls[0]
    assert insert_call["calendarId"] == "shared-calendar@example.com"
    assert insert_call["body"] == {
        "summary": "Team Sync",
        "description": "Weekly planning",
        "location": "Room 101",
        "start": {"dateTime": "2026-04-28T10:00:00+00:00", "timeZone": "UTC"},
        "end": {"dateTime": "2026-04-28T11:00:00+00:00", "timeZone": "UTC"},
    }
    assert result.event_id == "google-id-1"
    assert result.provider_event_id == "google-id-1"
    assert result.html_link == "https://calendar.google.com/event?id=1"


def test_create_event_fails_for_wrong_auth_mode() -> None:
    service = GoogleCalendarService(
        calendar_id="shared-calendar@example.com",
        service_account_json='{"type":"service_account"}',
        service_builder=lambda *args, **kwargs: object(),
        credentials_loader=lambda _: object(),
    )
    request = CalendarEventCreateRequest(
        title="Event",
        start_at_iso="2026-04-28T10:00:00+00:00",
        end_at_iso="2026-04-28T11:00:00+00:00",
        timezone="UTC",
    )
    auth_context = AuthContext(
        user_id=1,
        auth_mode=GoogleAuthMode.OAUTH_USER_MODE,
        credentials_handle="oauth-user",
    )

    with pytest.raises(ValueError, match="service_account_shared_calendar_mode"):
        service.create_event(auth_context=auth_context, request=request)


def test_create_event_fails_when_end_is_missing() -> None:
    service = GoogleCalendarService(
        calendar_id="shared-calendar@example.com",
        service_account_json='{"type":"service_account"}',
        service_builder=lambda *args, **kwargs: object(),
        credentials_loader=lambda _: object(),
    )
    request = CalendarEventCreateRequest(
        title="Event",
        start_at_iso="2026-04-28T10:00:00+00:00",
        end_at_iso=None,
        timezone="UTC",
    )

    with pytest.raises(ValueError, match="end_at_iso"):
        service.create_event(auth_context=_service_account_context(), request=request)


def test_create_event_fails_for_invalid_service_account_json() -> None:
    service = GoogleCalendarService(
        calendar_id="shared-calendar@example.com",
        service_account_json="not-json-and-not-path",
        credentials_loader=lambda _: (_ for _ in ()).throw(
            ValueError("GOOGLE_SERVICE_ACCOUNT_JSON must be either a JSON string or a valid file path")
        ),
    )
    request = CalendarEventCreateRequest(
        title="Event",
        start_at_iso="2026-04-28T10:00:00+00:00",
        end_at_iso="2026-04-28T11:00:00+00:00",
        timezone="UTC",
    )

    with pytest.raises(ValueError, match="GOOGLE_SERVICE_ACCOUNT_JSON"):
        service.create_event(auth_context=_service_account_context(), request=request)


def test_create_event_supports_service_account_json_file_path(tmp_path) -> None:
    service_account_path = tmp_path / "service_account.json"
    service_account_path.write_text(json.dumps({"type": "service_account"}), encoding="utf-8")

    service = GoogleCalendarService(
        calendar_id="shared-calendar@example.com",
        service_account_json=str(service_account_path),
        service_builder=lambda *args, **kwargs: _FakeService({"id": "google-id-2"}),
        credentials_loader=lambda payload: {"loaded_from": payload},
    )
    request = CalendarEventCreateRequest(
        title="Event",
        start_at_iso="2026-04-28T10:00:00+00:00",
        end_at_iso="2026-04-28T11:00:00+00:00",
        timezone="UTC",
    )

    result = service.create_event(auth_context=_service_account_context(), request=request)

    assert result.provider_event_id == "google-id-2"
