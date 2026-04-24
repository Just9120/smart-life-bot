import sqlite3

import pytest

from smart_life_bot.domain.enums import ConversationState, EventLogErrorCategory, EventLogStatus
from smart_life_bot.domain.models import ConversationStateSnapshot, EventDraft
from smart_life_bot.storage.sqlite import (
    SQLiteConversationStateRepository,
    SQLiteEventsLogRepository,
    SQLiteProviderCredentialsRepository,
    SQLiteUsersRepository,
    create_sqlite_connection,
    init_sqlite_schema,
)
from smart_life_bot.storage.interfaces import EventLogEntry


def _create_initialized_memory_connection() -> sqlite3.Connection:
    connection = create_sqlite_connection("sqlite:///:memory:")
    init_sqlite_schema(connection)
    return connection


def test_schema_init_creates_expected_tables() -> None:
    connection = _create_initialized_memory_connection()

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    assert {"users", "provider_credentials", "conversation_state", "events_log"} <= tables


def test_users_repository_create_get_and_get_or_create() -> None:
    connection = _create_initialized_memory_connection()
    repo = SQLiteUsersRepository(connection)

    created = repo.create(telegram_user_id=1001, timezone="UTC")
    loaded = repo.get_by_telegram_id(telegram_user_id=1001)

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.telegram_user_id == 1001
    assert loaded.timezone == "UTC"

    existing = repo.get_or_create_by_telegram_id(telegram_user_id=1001, timezone="Europe/Berlin")
    assert existing.id == created.id

    row_count = connection.execute("SELECT COUNT(*) AS count FROM users WHERE telegram_user_id = 1001").fetchone()
    assert row_count["count"] == 1


def test_provider_credentials_repository_save_update_and_get() -> None:
    connection = _create_initialized_memory_connection()
    user = SQLiteUsersRepository(connection).create(telegram_user_id=1002)
    repo = SQLiteProviderCredentialsRepository(connection)

    created = repo.save_for_user(
        user_id=user.id,
        provider="google_calendar",
        auth_mode="oauth_user_mode",
        credentials_encrypted="placeholder-token-v1",
    )
    assert created.credentials_encrypted == "placeholder-token-v1"

    updated = repo.save_for_user(
        user_id=user.id,
        provider="google_calendar",
        auth_mode="oauth_user_mode",
        credentials_encrypted="placeholder-token-v2",
    )
    fetched = repo.get_for_user(
        user_id=user.id,
        provider="google_calendar",
        auth_mode="oauth_user_mode",
    )

    assert fetched is not None
    assert updated.id == created.id
    assert fetched.credentials_encrypted == "placeholder-token-v2"


def test_conversation_state_repository_set_get_and_reset() -> None:
    connection = _create_initialized_memory_connection()
    user = SQLiteUsersRepository(connection).create(telegram_user_id=1003)
    repo = SQLiteConversationStateRepository(connection)

    snapshot = ConversationStateSnapshot(
        user_id=user.id,
        state=ConversationState.WAITING_PREVIEW_CONFIRMATION,
        draft=EventDraft(
            title="Doctor appointment",
            timezone="UTC",
            metadata={"source": "test"},
        ),
        editing_field="title",
    )
    repo.set(snapshot)
    loaded = repo.get(user_id=user.id)

    assert loaded is not None
    assert loaded.state is ConversationState.WAITING_PREVIEW_CONFIRMATION
    assert loaded.draft is not None
    assert loaded.draft.title == "Doctor appointment"
    assert loaded.draft.metadata == {"source": "test"}
    assert loaded.editing_field == "title"

    repo.reset(user_id=user.id)
    assert repo.get(user_id=user.id) is None


def test_events_log_repository_append_update_and_get() -> None:
    connection = _create_initialized_memory_connection()
    user = SQLiteUsersRepository(connection).create(telegram_user_id=1004)
    repo = SQLiteEventsLogRepository(connection)

    inserted = repo.append(
        EventLogEntry(
            id=None,
            user_id=user.id,
            raw_text="Напомни о созвоне завтра в 10:00",
            parsed_payload={"title": "Созвон", "time": "10:00"},
            status=EventLogStatus.RECEIVED,
        )
    )
    assert inserted.id is not None

    repo.update_status(
        entry_id=inserted.id,
        status=EventLogStatus.FAILED,
        error_category=EventLogErrorCategory.CALENDAR_WRITE_FAILURE,
        error_details="API timeout",
    )
    updated = repo.get_by_id(inserted.id)
    assert updated is not None
    assert updated.status is EventLogStatus.FAILED
    assert updated.error_code == "calendar_write_failure"
    assert updated.error_details == "API timeout"

    for_user = repo.list_for_user(user_id=user.id)
    assert len(for_user) == 1
    assert for_user[0].id == inserted.id


def test_events_log_update_status_keeps_existing_optional_fields_when_not_passed() -> None:
    connection = _create_initialized_memory_connection()
    user = SQLiteUsersRepository(connection).create(telegram_user_id=1005)
    repo = SQLiteEventsLogRepository(connection)

    inserted = repo.append(
        EventLogEntry(
            id=None,
            user_id=user.id,
            raw_text="Создай событие",
            parsed_payload={"title": "Событие"},
            status=EventLogStatus.CONFIRMED,
        )
    )
    assert inserted.id is not None

    repo.update_status(
        entry_id=inserted.id,
        status=EventLogStatus.SAVED,
        google_event_id="provider-id-1",
    )
    repo.update_status(
        entry_id=inserted.id,
        status=EventLogStatus.CONFIRMED,
    )

    updated = repo.get_by_id(inserted.id)
    assert updated is not None
    assert updated.google_event_id == "provider-id-1"


def test_foreign_keys_are_enabled_and_enforced() -> None:
    connection = _create_initialized_memory_connection()
    credentials_repo = SQLiteProviderCredentialsRepository(connection)

    with pytest.raises(sqlite3.IntegrityError):
        credentials_repo.save_for_user(
            user_id=99999,
            provider="google_calendar",
            auth_mode="oauth_user_mode",
            credentials_encrypted="placeholder",
        )


def test_create_sqlite_connection_supports_memory_url() -> None:
    connection = create_sqlite_connection("sqlite:///:memory:")
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
